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
# Keep scanner applications in separate tool environments: current Semgrep
# declares an older MCP SDK solely for its optional MCP surface. The scanner
# command has been exercised with the patched SDK and setuptools versions
# below; keeping them current removes known vulnerabilities from the image.
RUN uv tool install semgrep==1.172.0 \
    && uv pip install --python /opt/uv-tools/semgrep/bin/python \
      mcp==1.28.1 setuptools==83.0.0 \
    && uv tool install bandit==1.9.4

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

# uv's Python-tool launchers point into /opt, so expose small launchers from
# /usr/local/bin that run the same pinned modules through the system Python.
# Go and Node scanners are already installed directly under /usr/local.
RUN install -m 0755 docker-bin/semgrep /usr/local/bin/semgrep \
    && install -m 0755 docker-bin/bandit /usr/local/bin/bandit

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
