"""Deciding whether a repository *is* an MCP server, and what it exposes.

Before this existed, a GitHub target got the generic source-security treatment
-- Semgrep, Bandit, secrets, dependencies -- and the MCP-specific stage only
had something to work with if the repo happened to have a client config
committed in it. A server's own repository has no reason to contain a client
config pointing at itself, so the most important case in the product, "someone
scanned an actual MCP server", was the case that got the least MCP analysis.

Two jobs live here, and they are separate on purpose.

`detect_mcp_server` answers "is this an MCP server", and answers it with
*evidence* rather than a bare boolean. Several weak signals agreeing is a
different claim from one strong one, and the caller (and the user reading a
report) deserves to see which it was. A repository named `mcp-something` scores
nothing on its name alone: naming is not evidence, and treating it as such
would flag every tutorial, wrapper and blog-post repo in the ecosystem.

`discover_tools` answers "what does it expose", by reading the registration
sites in source. This is static analysis of declarations, not execution: the
scanner never imports, runs, or connects to the code it is reading. That
restraint is the whole reason this is safe to point at an untrusted
repository.

Both are best-effort by construction. A tool registered through a layer of
indirection this cannot see is a tool this will miss, which is exactly why a
repository whose MCP surface could not be read is reported as incompletely
covered rather than as clean.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

# Depth and file-count ceilings. A monorepo can be enormous, and this walk
# happens inside a scan that already has a time budget; the limits are
# generous enough for a real server and bounded enough that a pathological
# repository cannot stall the pipeline.
_MAX_DEPTH = 4
_MAX_SOURCE_FILES = 400
_MAX_FILE_BYTES = 512_000

_DIR_EXCLUDES = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".tox", "target", "vendor", ".mypy_cache", ".pytest_cache",
})

_SOURCE_EXTENSIONS = (".py", ".js", ".ts", ".mjs", ".cjs", ".tsx", ".go", ".rs", ".rb", ".java", ".cs")

_MANIFEST_FILENAMES = frozenset({
    "package.json", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
    "setup.py", "setup.cfg", "Pipfile", "go.mod", "Cargo.toml", "server.json",
})


# --------------------------------------------------------------------------
# Evidence
#
# Weights are deliberately modest and additive. No single heuristic below is
# allowed to be decisive on its own except a declared dependency on an actual
# MCP SDK, which is as close to a statement of intent as a repository makes.


@dataclass(frozen=True)
class DetectionSignal:
    """One reason to believe this is an MCP server."""

    kind: str
    detail: str
    weight: int
    file_path: str | None = None


@dataclass(frozen=True)
class McpComponent:
    """One MCP server living inside this repository, at `root`.

    A monorepo's frontend, backend, and MCP server are three different
    things sharing one clone; scoring the whole tree as one target meant a
    repo with an MCP server in `mcp-server/` and nothing MCP-related in
    `frontend/`/`backend/` was already correctly detected overall, but
    nothing said *where* - which mattered once tool discovery needed to
    stop merging two separately-rooted servers' tools into one flat list.
    Only emitted for a root that independently reaches at least `low`
    confidence on its own files; a directory with no MCP signal of its own
    is not a component just because it shares a repository with one that is.
    """

    root: str  # relative path, "." for the repository root itself
    confidence: str  # "high" | "medium" | "low" (never "none" - not emitted)
    signals: tuple[DetectionSignal, ...] = ()


@dataclass
class McpDetection:
    """The verdict, with the evidence that produced it."""

    is_mcp_server: bool
    confidence: str  # "high" | "medium" | "low" | "none"
    signals: list[DetectionSignal] = field(default_factory=list)
    # Deliberately NOT a roll-up of this list: computed once, globally, over
    # every manifest/source file in the repository, exactly as before
    # components existed. A monorepo's evidence often splits across
    # directories (an SDK dependency in one package, its registration
    # decorator in another via a shared internal library), and scoping this
    # verdict to "the strongest single component" would under-detect real
    # servers whose evidence is real but spread out. components (below) is
    # the answer to "where", not a replacement for this answer to "whether".
    components: list[McpComponent] = field(default_factory=list)

    @property
    def score(self) -> int:
        return sum(s.weight for s in self.signals)

    def summary(self) -> str:
        if not self.signals:
            return "No MCP server evidence found."
        return "; ".join(f"{s.kind}: {s.detail}" for s in self.signals[:6])


# An SDK dependency by name. These are the packages a server actually builds
# on, so a declared dependency on one is the strongest signal available short
# of running the thing.
_SDK_DEPENDENCIES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"@modelcontextprotocol/sdk"), "@modelcontextprotocol/sdk (TypeScript SDK)"),
    (re.compile(r"\bmodelcontextprotocol\b", re.IGNORECASE), "modelcontextprotocol"),
    (re.compile(r"\bfastmcp\b", re.IGNORECASE), "fastmcp"),
    (re.compile(r"\bmcp\.server\b", re.IGNORECASE), "mcp.server"),
    # The official Python SDK is published as the bare name `mcp`, so it can
    # only be matched where a dependency line's shape makes it unambiguous.
    # The quote immediately before `mcp` is what keeps this off `fastmcp` and
    # `mcp-server-git`: the name has to start and end exactly there.
    (re.compile(r"[\"']mcp\s*[><=~^!]"), "mcp (Python SDK)"),
    (re.compile(r"^\s*mcp\s*[><=~^!]", re.MULTILINE), "mcp (Python SDK)"),
    (re.compile(r"^\s*[\"']mcp[\"']\s*[:=]", re.MULTILINE), "mcp (Python SDK)"),
    (re.compile(r"\bmcp-go\b|github\.com/mark3labs/mcp-go"), "mcp-go"),
    (re.compile(r"\brmcp\b|\bmcp-sdk\b"), "Rust/other MCP SDK"),
)

# Imports of the SDK in source. Weaker than a manifest dependency (a file can
# import something the project does not declare) but stronger than a mention.
_SDK_IMPORTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"from\s+mcp(?:\.\w+)*\s+import\b"), "from mcp import ..."),
    (re.compile(r"^\s*import\s+mcp\b", re.MULTILINE), "import mcp"),
    (re.compile(r"from\s+[\"']@modelcontextprotocol/sdk[^\"']*[\"']"), "@modelcontextprotocol/sdk import"),
    (re.compile(r"require\([\"']@modelcontextprotocol/sdk[^\"']*[\"']\)"), "@modelcontextprotocol/sdk require"),
    (re.compile(r"from\s+fastmcp\s+import\b|\bimport\s+fastmcp\b"), "fastmcp import"),
    (re.compile(r"mark3labs/mcp-go/(?:mcp|server)"), "mcp-go import"),
)

# Constructing a server. This is the initialisation pattern the SDKs document.
_SERVER_INIT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bnew\s+Server\s*\(", ), "new Server(...)"),
    (re.compile(r"\bnew\s+McpServer\s*\("), "new McpServer(...)"),
    (re.compile(r"\bServer\s*\(\s*[\"'{]"), "Server(...)"),
    (re.compile(r"\bFastMCP\s*\("), "FastMCP(...)"),
    (re.compile(r"\bMcpServer\s*\("), "McpServer(...)"),
    (re.compile(r"server\.NewMCPServer\s*\("), "NewMCPServer(...)"),
)

# Registering capability. A server that registers no tools, resources or
# prompts is not offering anything, so these are what make it a *server*
# rather than a client or a library.
_REGISTRATION: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"@\w+\.tool\s*\("), "@tool decorator"),
    (re.compile(r"@\w+\.resource\s*\("), "@resource decorator"),
    (re.compile(r"@\w+\.prompt\s*\("), "@prompt decorator"),
    (re.compile(r"\bListToolsRequestSchema\b"), "ListToolsRequestSchema handler"),
    (re.compile(r"\bCallToolRequestSchema\b"), "CallToolRequestSchema handler"),
    (re.compile(r"\bListResourcesRequestSchema\b"), "ListResourcesRequestSchema handler"),
    (re.compile(r"\.registerTool\s*\(|\.setRequestHandler\s*\("), "registerTool/setRequestHandler"),
    (re.compile(r"\bAddTool\s*\(|\bNewTool\s*\("), "AddTool(...)"),
    (re.compile(r"\blist_tools\b|\bcall_tool\b"), "list_tools/call_tool handler"),
)

# Transport wiring: how the server is actually served.
_TRANSPORT: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bStdioServerTransport\b|\bstdio_server\b"), "stdio transport"),
    (re.compile(r"\bSSEServerTransport\b|\bsse_server\b"), "SSE transport"),
    (re.compile(r"\bStreamableHTTPServerTransport\b|\bstreamable_http\b"), "streamable-http transport"),
    (re.compile(r"\bServeStdio\b"), "stdio transport (Go)"),
)


def _read(path: str) -> str | None:
    try:
        if os.path.getsize(path) > _MAX_FILE_BYTES:
            return None
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return handle.read()
    except OSError:
        return None


def _walk(repo_dir: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (manifests, sources) as (relative_path, content) pairs.

    One walk feeds both detection and tool discovery: the pipeline is already
    slow, and reading the tree twice to answer two questions about the same
    files would be pure waste.
    """
    manifests: list[tuple[str, str]] = []
    sources: list[tuple[str, str]] = []
    root_depth = repo_dir.rstrip("/\\").replace("\\", "/").count("/")

    for dirpath, dirnames, filenames in os.walk(repo_dir):
        normalised = dirpath.rstrip("/\\").replace("\\", "/")
        if normalised.count("/") - root_depth > _MAX_DEPTH:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in _DIR_EXCLUDES and not d.startswith(".")]

        for filename in filenames:
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, repo_dir).replace("\\", "/")
            if filename in _MANIFEST_FILENAMES:
                content = _read(full)
                if content is not None:
                    manifests.append((relative, content))
            elif filename.endswith(_SOURCE_EXTENSIONS) and len(sources) < _MAX_SOURCE_FILES:
                content = _read(full)
                if content is not None:
                    sources.append((relative, content))
    return manifests, sources


def _evidence_signals(
    manifests: list[tuple[str, str]], sources: list[tuple[str, str]]
) -> list[DetectionSignal]:
    """Every detection signal found in this manifest/source set.

    Pulled out of detect_mcp_server so component detection (below) can run
    the identical pattern-matching against a narrower, per-directory subset
    without duplicating a single regex.
    """
    signals: list[DetectionSignal] = []
    seen: set[str] = set()

    def add(kind: str, detail: str, weight: int, path: str | None) -> None:
        key = f"{kind}:{detail}"
        if key in seen:
            return
        seen.add(key)
        signals.append(DetectionSignal(kind=kind, detail=detail, weight=weight, file_path=path))

    for path, content in manifests:
        # server.json is the registry's own manifest. Its presence, with the
        # shape the schema requires, is a declaration by the author.
        if os.path.basename(path) == "server.json":
            try:
                parsed = json.loads(content)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict) and "name" in parsed and ("packages" in parsed or "remotes" in parsed):
                add("registry_manifest", "server.json declares an MCP server", 40, path)
        for pattern, label in _SDK_DEPENDENCIES:
            if pattern.search(content):
                add("sdk_dependency", f"depends on {label}", 40, path)

    for path, content in sources:
        for pattern, label in _SDK_IMPORTS:
            if pattern.search(content):
                add("sdk_import", label, 25, path)
        for pattern, label in _SERVER_INIT:
            if pattern.search(content):
                add("server_init", label, 12, path)
        for pattern, label in _REGISTRATION:
            if pattern.search(content):
                add("registration", label, 18, path)
        for pattern, label in _TRANSPORT:
            if pattern.search(content):
                add("transport", label, 15, path)

    return signals


def _confidence_from_signals(signals: list[DetectionSignal]) -> str:
    score = sum(s.weight for s in signals)
    kinds = {s.kind for s in signals}

    # A declared SDK dependency or a registry manifest, together with anything
    # at all that looks like serving, is as certain as static analysis gets.
    strong = bool(kinds & {"sdk_dependency", "registry_manifest"})
    serving = bool(kinds & {"registration", "transport", "server_init"})

    if strong and serving:
        return "high"
    if strong or (serving and "sdk_import" in kinds):
        return "medium"
    if score >= 30:
        return "low"
    return "none"


def _component_candidate_roots(manifests: list[tuple[str, str]]) -> list[str]:
    """Every directory a component could be rooted at: the repository root,
    plus every directory that owns a manifest of its own. A directory with
    no manifest is never a candidate root on its own - it has nothing that
    plausibly makes it a separate package rather than just more files
    belonging to whichever manifest-owning directory encloses it."""
    roots = {"."}
    for path, _content in manifests:
        directory = os.path.dirname(path)
        roots.add(directory if directory else ".")
    return sorted(roots)


def _owning_root(path: str, roots: list[str]) -> str:
    """The most specific candidate root that encloses `path`, so a file two
    levels under `mcp-server/` is attributed to `mcp-server/`, not to the
    repository root just because "." technically encloses everything too."""
    best = "."
    best_len = -1
    for root in roots:
        if root == ".":
            continue
        if (path == root or path.startswith(root + "/")) and len(root) > best_len:
            best = root
            best_len = len(root)
    return best


def _detect_components(
    manifests: list[tuple[str, str]], sources: list[tuple[str, str]]
) -> list[McpComponent]:
    roots = _component_candidate_roots(manifests)
    grouped_manifests: dict[str, list[tuple[str, str]]] = {root: [] for root in roots}
    grouped_sources: dict[str, list[tuple[str, str]]] = {root: [] for root in roots}
    for path, content in manifests:
        grouped_manifests[_owning_root(path, roots)].append((path, content))
    for path, content in sources:
        grouped_sources[_owning_root(path, roots)].append((path, content))

    components: list[McpComponent] = []
    for root in roots:
        signals = _evidence_signals(grouped_manifests[root], grouped_sources[root])
        confidence = _confidence_from_signals(signals)
        if confidence == "none":
            continue
        components.append(
            McpComponent(
                root=root,
                confidence=confidence,
                signals=tuple(sorted(signals, key=lambda s: -s.weight)),
            )
        )
    # Repository root first when it is itself a component (the common case:
    # a single-package repo has exactly one component, rooted "."), then the
    # rest alphabetically.
    return sorted(components, key=lambda c: (c.root != ".", c.root))


def detect_mcp_server(repo_dir: str) -> McpDetection:
    """Is this repository an MCP server, and on what evidence?

    Scoring, rather than any single test, because every individual signal has
    a plausible innocent explanation. A dependency could be a client's. An
    import could be in an example. A `new Server(` could be Express. Requiring
    agreement between independent signals is what keeps this from firing on
    every repository that has heard of MCP.

    This verdict is computed globally, over every manifest and source file in
    the repository - it is not derived from `components` below, and scoping
    it to components would under-detect a real server whose evidence happens
    to be split across directories (a shared internal library declaring the
    SDK dependency, a separate directory registering the tools). `components`
    answers a different, narrower question: which specific directories, each
    judged independently on their own files, look like a self-contained MCP
    server. A monorepo can correctly score "high" here while contributing
    zero or several entries there.
    """
    manifests, sources = _walk(repo_dir)
    signals = _evidence_signals(manifests, sources)
    confidence = _confidence_from_signals(signals)

    return McpDetection(
        is_mcp_server=confidence in ("high", "medium", "low"),
        confidence=confidence,
        signals=sorted(signals, key=lambda s: -s.weight),
        components=_detect_components(manifests, sources),
    )




def walk_sources(repo_dir: str) -> list[tuple[str, str]]:
    """Just the source files, for `analysis/discovery.py`.

    A thin wrapper rather than exporting `_walk` itself: discovery has no
    use for the manifest half, and a caller that has to unpack and discard
    one of two return values is a caller reading the wrong function.
    """
    _, sources = _walk(repo_dir)
    return sources
