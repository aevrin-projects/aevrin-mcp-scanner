# Railway (and similar PaaS runtimes) run non-privileged containers with no
# Docker-in-Docker support, so `docker run` per scanner (the local/self-hosted
# path — see packages/scanner-core/runner.py) isn't available here. Every
# scanner binary this image needs is installed directly instead, and
# AEVRIN_EXECUTOR=subprocess tells the adapters to invoke them directly
# rather than through Docker. Versions are pinned to match what was
# empirically verified in Docker mode (see packages/scanner-core adapter
# docstrings) — bump deliberately, not via floating "latest" tags.
#
# Build context MUST be the repo root (Railway service Root Directory = "."
# with Dockerfile Path = "apps/api/Dockerfile"), since this needs to COPY
# the sibling packages/scanner-core package — not apps/api in isolation.
FROM python:3.12-slim

# Set automatically by BuildKit to the target platform's arch (amd64/arm64) —
# don't hardcode one, since Railway's builder architecture isn't guaranteed
# and this same Dockerfile is also used for local verification on Apple
# Silicon.
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates gnupg xz-utils \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Go-binary scanners: prebuilt release binaries, no Go toolchain needed ---
WORKDIR /tmp/install

RUN GL_ARCH=$(if [ "$TARGETARCH" = "arm64" ]; then echo arm64; else echo x64; fi) \
    && curl -sSL -o gitleaks.tar.gz \
      "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/gitleaks_8.30.1_linux_${GL_ARCH}.tar.gz" \
    && tar -xzf gitleaks.tar.gz gitleaks \
    && install -m 0755 gitleaks /usr/local/bin/gitleaks \
    && rm -rf /tmp/install/*

RUN curl -sSL -o trufflehog.tar.gz \
      "https://github.com/trufflesecurity/trufflehog/releases/download/v3.96.0/trufflehog_3.96.0_linux_${TARGETARCH}.tar.gz" \
    && tar -xzf trufflehog.tar.gz trufflehog \
    && install -m 0755 trufflehog /usr/local/bin/trufflehog \
    && rm -rf /tmp/install/*

RUN curl -sSL -o osv-scanner \
      "https://github.com/google/osv-scanner/releases/download/v2.4.0/osv-scanner_linux_${TARGETARCH}" \
    && install -m 0755 osv-scanner /usr/local/bin/osv-scanner \
    && rm -rf /tmp/install/*

RUN TRIVY_ARCH=$(if [ "$TARGETARCH" = "arm64" ]; then echo ARM64; else echo 64bit; fi) \
    && curl -sSL -o trivy.tar.gz \
      "https://github.com/aquasecurity/trivy/releases/download/v0.73.0/trivy_0.73.0_Linux-${TRIVY_ARCH}.tar.gz" \
    && tar -xzf trivy.tar.gz trivy \
    && install -m 0755 trivy /usr/local/bin/trivy \
    && rm -rf /tmp/install/*

RUN curl -sSL -o scorecard.tar.gz \
      "https://github.com/ossf/scorecard/releases/download/v5.5.0/scorecard_5.5.0_linux_${TARGETARCH}.tar.gz" \
    && tar -xzf scorecard.tar.gz \
    && install -m 0755 scorecard /usr/local/bin/scorecard \
    && rm -rf /tmp/install/*

# --- npm-based scanner ---
RUN npm install -g mcp-shield@1.0.4

# apps/api/pyproject.toml points at its sibling package as
# "../../packages/scanner-core" — mirror that same two-level relationship
# inside the image (/repo/apps/api and /repo/packages/scanner-core) so the
# relative path resolves the same way it does in the real repo, instead of
# trying to climb above the container's filesystem root.
WORKDIR /repo/apps/api

# --- Python scanners + the app itself, via uv ---
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
ENV UV_TOOL_BIN_DIR=/usr/local/bin
ENV UV_TOOL_DIR=/opt/uv-tools
# Keep scanner applications in separate tool environments: current Semgrep
# declares an older MCP SDK solely for its optional MCP surface. The scanner
# command has been exercised with the patched SDK and setuptools versions
# below; keeping them current removes known vulnerabilities from the image.
RUN uv tool install semgrep==1.172.0 \
    && uv pip install --python /opt/uv-tools/semgrep/bin/python \
      mcp==1.28.1 setuptools==83.0.0 \
    && uv tool install bandit==1.9.4

COPY packages/scanner-core /repo/packages/scanner-core
COPY apps/api /repo/apps/api

RUN uv sync --frozen --no-dev

ENV AEVRIN_EXECUTOR=subprocess
ENV PATH="/repo/apps/api/.venv/bin:${PATH}"

# The API and every scanner run without root privileges. Scanner workspaces
# live under /tmp and Semgrep's cache lives in this user's writable home.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin aevrin
RUN chown -R aevrin:aevrin /repo/apps/api/.venv /opt/uv-tools \
    && chmod -R a+rX /repo/apps/api/.venv /opt/uv-tools
USER aevrin

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent "http://127.0.0.1:${PORT:-8000}/health" >/dev/null || exit 1
# Launch through the venv interpreter rather than uvicorn's generated console
# script. Railway's runtime can reject that launcher as non-executable after
# its image snapshot step; `python -m uvicorn` reaches the same pinned module
# without re-syncing dependencies at startup.
CMD ["sh", "-c", "/repo/apps/api/.venv/bin/python -m uvicorn aevrin_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
