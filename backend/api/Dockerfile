# Managed container runtimes (AWS Fargate, Azure Container Apps, and PaaS
# hosts generally) run non-privileged containers with no Docker-in-Docker
# support, so `docker run` per scanner (the local/self-hosted path; see
# backend/scanner-core/aevrin_scanner_core/execution/runner.py) isn't
# available here. Every
# scanner binary this image needs is installed directly instead, and
# AEVRIN_EXECUTOR=subprocess tells the adapters to invoke them directly
# rather than through Docker. Versions are pinned to match what was
# empirically verified in Docker mode (see backend/scanner-core adapter
# docstrings), bump deliberately, not via floating "latest" tags.
#
# Build context MUST be the repo root, since this needs to COPY the sibling
# backend/scanner-core package rather than backend/api in isolation:
#   docker build -f backend/api/Dockerfile .
FROM python:3.11-slim

# Set automatically by BuildKit to the target platform's arch (amd64/arm64);
# don't hardcode one: CodeBuild and Fargate can be either amd64 or arm64,
# and this same Dockerfile is also used for local verification on Apple
# Silicon.
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates gnupg xz-utils \
    && rm -rf /var/lib/apt/lists/*

# --- Go-binary scanners: prebuilt release binaries, no Go toolchain needed ---
#
# Two, down from five, and Node is gone with them. Removed alongside the
# code-security product (DECISIONS.md ADR-027): Gitleaks duplicated
# TruffleHog without its live credential verification; Trivy duplicated
# OSV-Scanner and additionally emitted Dockerfile misconfiguration findings,
# which are not MCP security and were the loudest single source of noise in
# an MCP report; OpenSSF Scorecard produced only repository-practice findings
# (badges, fuzzing status, branch protection); and MCP-Shield, the sole
# reason Node was installed here at all, is superseded by Aevrin's own rule
# engine, which needs no binary and no network.
WORKDIR /tmp/install

RUN curl -sSL -o trufflehog.tar.gz \
      "https://github.com/trufflesecurity/trufflehog/releases/download/v3.96.0/trufflehog_3.96.0_linux_${TARGETARCH}.tar.gz" \
    && tar -xzf trufflehog.tar.gz trufflehog \
    && install -m 0755 trufflehog /usr/local/bin/trufflehog \
    && rm -rf /tmp/install/*

RUN curl -sSL -o osv-scanner \
      "https://github.com/google/osv-scanner/releases/download/v2.4.0/osv-scanner_linux_${TARGETARCH}" \
    && install -m 0755 osv-scanner /usr/local/bin/osv-scanner \
    && rm -rf /tmp/install/*

# backend/api/pyproject.toml points at its sibling package as
# "../scanner-core", mirror that same one-level relationship inside the
# image (/repo/backend/api and /repo/backend/scanner-core) so the relative
# path resolves the same way it does in the real repo, instead of trying to
# climb above the container's filesystem root.
WORKDIR /repo/backend/api

# --- Python scanners + the app itself, via uv ---
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
ENV UV_PYTHON=3.11
ENV UV_PYTHON_DOWNLOADS=never
ENV UV_TOOL_BIN_DIR=/usr/local/bin
ENV UV_TOOL_DIR=/opt/uv-tools
# Semgrep the *engine* stays; Semgrep the generic ruleset is gone. It now
# runs only Aevrin's own MCP taint pack (scanner-core/rules/mcp/*.yaml),
# which traces an MCP tool argument to a dangerous sink rather than auditing
# source code at large, and needs no network because those rules are local
# files. Bandit was removed outright: it had no MCP-specific rules at all.
#
# Kept in its own tool environment: current Semgrep declares an older MCP SDK
# solely for its optional MCP surface. The scanner command has been exercised
# with the patched SDK and setuptools versions below; keeping them current
# removes known vulnerabilities from the image.
RUN uv tool install semgrep==1.172.0 \
    && uv pip install --python /opt/uv-tools/semgrep/bin/python \
      mcp==1.28.1 setuptools==83.0.0

COPY backend/scanner-core /repo/backend/scanner-core
COPY backend/api /repo/backend/api

# Keep the application environment out of /repo so neither Python nor the
# generated console scripts need to execute from the source tree after
# deployment. Some runtimes mount it non-executable; none mind this.
ENV UV_PROJECT_ENVIRONMENT=/opt/aevrin-venv
RUN uv sync --frozen --no-dev \
    && cp -a /opt/aevrin-venv/lib/python3.11/site-packages/. \
      /usr/local/lib/python3.11/site-packages/ \
    && rm -rf /opt/aevrin-venv

ENV AEVRIN_EXECUTOR=subprocess
# Copying the frozen environment into the system interpreter's standard
# import location makes startup independent of both PYTHONPATH and of
# whether /repo is executable. Editable package links still point at the
# read-only application sources under /repo.

# uv's Python-tool launcher points into /opt, so expose a small launcher from
# /usr/local/bin that runs the same pinned module through the system Python.
# The Go scanners are already installed directly under /usr/local.
RUN install -m 0755 docker-bin/semgrep /usr/local/bin/semgrep

# The API and every scanner run without root privileges. Scanner workspaces
# live under /tmp and Semgrep's cache lives in this user's writable home.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin aevrin
RUN chown -R aevrin:aevrin /opt/uv-tools \
    && chmod -R a+rX /opt/uv-tools
USER aevrin

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent "http://127.0.0.1:${PORT:-8000}/health" >/dev/null || exit 1
# Launch through the executable system interpreter while importing the exact
# locked environment above. No dependency resolution happens at runtime.
CMD ["sh", "-c", "/usr/local/bin/python -m uvicorn aevrin_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
