"""Turning an upstream server.json into an Aevrin marketplace listing.

Everything here is deterministic and evidence-based. Categories come from
words the publisher actually wrote; install targets come from the transports
the publisher actually declared; pricing comes from the licence and package
type, and is left as "unknown" rather than guessed when neither says anything.

The rule that shapes this whole module: never invent a fact about someone
else's software. A listing that says "Free" because the code felt optimistic
is a lie with a security consequence, since "free and open source" is exactly
the phrase that makes a developer skip the diligence step.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from aevrin_api.integrations.mcp_registry import RegistryServer

# --------------------------------------------------------------------------
# Slugs

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(*parts: str) -> str:
    """A stable, readable URL segment.

    Built from the registry name rather than the title, because the title is
    free text a publisher can change at will and the URL should not move when
    they do.
    """
    joined = "-".join(p for p in parts if p)
    slug = _SLUG_STRIP.sub("-", joined.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug or not slug[0].isalnum():
        slug = f"mcp-{slug}".strip("-")
    return slug[:80] or "mcp-server"


def slug_for(server: RegistryServer) -> str:
    """`io.github.acme/postgres` becomes `acme-postgres`.

    The reverse-DNS prefix carries the verified namespace, which is worth
    keeping for disambiguation, but `io-github-acme-postgres` reads like a
    machine identifier. The last meaningful namespace segment is enough.
    """
    namespace, _, name = server.name.partition("/")
    segments = [s for s in namespace.split(".") if s not in ("io", "com", "net", "org", "dev", "app")]
    owner = segments[-1] if segments else ""
    # A GitHub-namespaced server is `io.github.<owner>/<name>`, so the owner
    # is already the last segment; anything else keeps its own last segment.
    return slugify(owner, name)


# --------------------------------------------------------------------------
# Categories
#
# A keyword table, not a classifier. It is inspectable, it is stable across
# runs, and when it is wrong an admin can override it -- which is exactly the
# curation layer the registry expects an aggregator to add.

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "databases": ("database", "postgres", "postgresql", "mysql", "sqlite", "mongodb", "redis",
                  "clickhouse", "snowflake", "bigquery", "duckdb", "supabase", "sql", "neo4j"),
    "developer-tools": ("git", "github", "gitlab", "code", "ide", "editor", "debug", "lint",
                        "compiler", "repository", "pull request", "issue tracker", "jira"),
    "cloud": ("aws", "azure", "gcp", "google cloud", "cloudflare", "kubernetes", "terraform",
              "s3", "lambda", "ec2", "cloud"),
    "search": ("search", "brave", "google search", "perplexity", "elasticsearch", "index",
               "retrieval", "web search", "tavily"),
    "productivity": ("notion", "calendar", "todo", "task", "note", "obsidian", "reminder",
                     "productivity", "asana", "trello"),
    "communication": ("slack", "discord", "email", "gmail", "telegram", "sms", "chat",
                      "messaging", "teams", "whatsapp"),
    "business": ("crm", "salesforce", "hubspot", "invoice", "erp", "customer"),
    "finance": ("payment", "stripe", "finance", "accounting", "banking", "trading", "stock",
                "crypto", "ledger", "razorpay"),
    "analytics": ("analytics", "metrics", "dashboard", "reporting", "telemetry", "posthog",
                  "amplitude", "mixpanel"),
    "devops": ("ci", "cd", "pipeline", "deploy", "docker", "monitoring", "observability",
               "prometheus", "grafana", "incident", "pagerduty", "sentry"),
    "security": ("security", "vulnerability", "scanner", "secrets", "audit", "compliance",
                 "pentest", "cve", "threat"),
    "browser-web": ("browser", "playwright", "puppeteer", "scrape", "crawl", "selenium",
                    "web page", "html", "fetch url"),
    "files-storage": ("filesystem", "file system", "storage", "s3 bucket", "dropbox",
                      "google drive", "file", "directory", "blob"),
    "marketing": ("marketing", "seo", "campaign", "mailchimp", "advertis", "social media"),
    "ai-ml": ("llm", "embedding", "vector", "openai", "anthropic", "model", "inference",
              "machine learning", "rag", "pinecone", "chroma", "huggingface"),
    "research": ("research", "arxiv", "paper", "academic", "scholar", "wikipedia", "pubmed"),
}

# Tag vocabulary. Only terms that appear verbatim become tags, so a tag is
# always something the publisher's own text supports.
_TAG_TERMS: tuple[str, ...] = (
    "github", "gitlab", "postgres", "mysql", "sqlite", "mongodb", "redis", "aws", "azure",
    "gcp", "kubernetes", "docker", "slack", "discord", "notion", "jira", "stripe", "search",
    "browser", "security", "database", "filesystem", "api", "cli", "oauth", "graphql",
    "openai", "anthropic", "llm", "vector", "analytics", "monitoring", "email", "calendar",
)


def infer_categories(title: str, description: str, extra: str = "") -> list[str]:
    """Every category whose vocabulary the text actually supports.

    Multiple categories are expected and allowed. "Other" is the answer when
    nothing matches, which is honest: an uncategorised listing is still
    findable by search, and a wrong category is worse than none.
    """
    haystack = f"{title} {description} {extra}".lower()
    matched = [
        slug
        for slug, keywords in _CATEGORY_KEYWORDS.items()
        if any(keyword in haystack for keyword in keywords)
    ]
    # Cap it. A description that trips eight categories is describing a suite,
    # and eight badges on a card is not information.
    return sorted(matched)[:4] or ["other"]


def infer_tags(title: str, description: str) -> list[str]:
    haystack = f"{title} {description}".lower()
    return sorted({term for term in _TAG_TERMS if term in haystack})[:12]


# --------------------------------------------------------------------------
# Installation
#
# Compatibility is read off the declared transports, never assumed. "It speaks
# MCP so it works everywhere" is the claim this deliberately refuses to make.

# Which hosts can consume which transport, as of the clients Aevrin already
# has adapters for. Kept as data so adding a client is a line, not a rewrite.
_TRANSPORT_SUPPORT: dict[str, tuple[str, ...]] = {
    "stdio": ("claude-code", "codex", "cursor", "generic"),
    "streamable-http": ("claude-code", "cursor", "generic"),
    "sse": ("claude-code", "cursor", "generic"),
}


def _transport_types(server: RegistryServer) -> set[str]:
    types: set[str] = set()
    for package in server.packages:
        transport = package.get("transport")
        if isinstance(transport, dict) and isinstance(transport.get("type"), str):
            types.add(transport["type"])
    for remote in server.remotes:
        if isinstance(remote.get("type"), str):
            types.add(remote["type"])
    return types


def infer_install_targets(server: RegistryServer) -> list[str]:
    """The clients this can actually be installed into.

    Empty when the server declares no transport at all, which is a real
    answer: without one there is nothing to configure, and pretending
    otherwise would produce an Install button that cannot work.
    """
    targets: set[str] = set()
    for transport_type in _transport_types(server):
        targets.update(_TRANSPORT_SUPPORT.get(transport_type, ()))
    return sorted(targets)


def build_installation(server: RegistryServer) -> dict[str, Any]:
    """The normalised install recipe handed to the client.

    Environment variables are reduced to name/required/secret. Their *values*
    are never carried: server.json can declare a variable as secret, and a
    marketplace that echoed a default secret back to every browser would be
    distributing credentials.
    """
    packages = []
    for package in server.packages[:10]:
        maybe_transport = package.get("transport")
        transport = maybe_transport if isinstance(maybe_transport, dict) else {}
        environment = []
        for variable in (package.get("environmentVariables") or [])[:40]:
            if not isinstance(variable, dict) or not isinstance(variable.get("name"), str):
                continue
            environment.append({
                "name": variable["name"][:120],
                "required": bool(variable.get("isRequired")),
                "secret": bool(variable.get("isSecret")),
                "description": (variable.get("description") or "")[:300],
            })
        packages.append({
            "registry_type": str(package.get("registryType") or "")[:40],
            "identifier": str(package.get("identifier") or "")[:300],
            "version": str(package.get("version") or "")[:255],
            "runtime_hint": str(package.get("runtimeHint") or "")[:40],
            "transport": str(transport.get("type") or "")[:40],
            "file_sha256": str(package.get("fileSha256") or "")[:64] or None,
            "environment": environment,
        })

    remotes = []
    for remote in server.remotes[:10]:
        url = remote.get("url")
        remotes.append({
            "type": str(remote.get("type") or "")[:40],
            "url": str(url)[:500] if isinstance(url, str) else None,
        })

    return {"packages": packages, "remotes": remotes}


# --------------------------------------------------------------------------
# Pricing and licence

# SPDX identifiers that mean the source is open. Used only to set
# price_type='open_source'; it says nothing about whether the *service* behind
# a remote server charges money, which is why a remote-only server never gets
# this treatment.
_OPEN_SOURCE_LICENSES = frozenset({
    "mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "mpl-2.0",
    "gpl-2.0", "gpl-3.0", "agpl-3.0", "lgpl-3.0", "unlicense", "0bsd",
})


def infer_price_type(*, license_id: str | None, has_packages: bool, has_remotes: bool) -> str:
    """What we can honestly say about cost.

    An open licence on a package you run yourself is genuinely free to use, so
    that much is safe. Everything else is 'unknown', and the UI says "not
    stated" rather than "Free". Guessing here would be the single most
    damaging inaccuracy in the marketplace.
    """
    normalised = (license_id or "").strip().lower()
    if normalised in _OPEN_SOURCE_LICENSES and has_packages and not has_remotes:
        return "open_source"
    return "unknown"


# --------------------------------------------------------------------------
# Assembly


def _safe_public_url(raw: str | None) -> str | None:
    """Only absolute http(s) URLs survive.

    These are rendered as links on a public page. A `javascript:` or `data:`
    URL from a publisher's metadata would be stored XSS delivered by us on
    their behalf, so the scheme allowlist is applied at ingestion rather than
    trusted to the renderer.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = urlsplit(raw.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None
    return raw.strip()[:500]


def registry_server_to_listing(server: RegistryServer) -> dict[str, Any]:
    """The listing row for one registry entry.

    Deliberately returns a plain dict rather than writing anything: the caller
    decides whether this is an insert or an update, and the sync job needs to
    diff it against what is already stored before it touches the database.
    """
    title = server.title or server.name.split("/", 1)[-1].replace("-", " ").replace("_", " ").title()
    repository_url = _safe_public_url(server.repository_url)
    has_packages = bool(server.packages)
    has_remotes = bool(server.remotes)

    return {
        "registry_name": server.name,
        "source": "registry",
        "slug": slug_for(server),
        "title": title[:120],
        "description": server.description[:4000],
        "repository_url": repository_url,
        "homepage_url": _safe_public_url(server.website_url),
        "registry_url": f"https://registry.modelcontextprotocol.io/v0.1/servers/{server.name}",
        # The verified namespace, which is the closest the registry gets to an
        # authenticated publisher identity.
        "publisher": server.namespace or None,
        "categories": infer_categories(title, server.description),
        "tags": infer_tags(title, server.description),
        "price_type": infer_price_type(
            license_id=None, has_packages=has_packages, has_remotes=has_remotes
        ),
        "install_targets": infer_install_targets(server),
        "installation": build_installation(server),
        "latest_version": server.version,
        "registry_updated_at": server.updated_at,
        "visibility": "public",
    }


def primary_package(server: RegistryServer) -> dict[str, Any] | None:
    """The package a version's identity should be pinned to.

    First declared wins. A server publishing both npm and PyPI builds of the
    same version is one release, and picking one consistently is what stops
    the version table gaining a duplicate row on every sync.
    """
    return server.packages[0] if server.packages else None
