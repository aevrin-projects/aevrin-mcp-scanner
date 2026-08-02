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
      "https://github.com/aquasecurity/trivy/releases/download/v0.72.0/trivy_0.72.0_Linux-${TRIVY_ARCH}.tar.gz" \
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
# setuptools >=81 dropped the bundled pkg_resources module; semgrep's
# opentelemetry dependency still imports it at load time, so pin below that.
RUN pip install --no-cache-dir \
      "setuptools<81" \
      semgrep==1.85.0 \
      bandit==1.8.0 \
      snyk-agent-scan==0.5.15

COPY packages/scanner-core /repo/packages/scanner-core
COPY apps/api /repo/apps/api

RUN uv sync --frozen --no-dev

ENV AEVRIN_EXECUTOR=subprocess
ENV PATH="/repo/apps/api/.venv/bin:${PATH}"

EXPOSE 8000
# Call the venv's uvicorn directly — `uv run` re-syncs against pyproject.toml
# (including the dev dependency group) on every container start, which is
# both slow and pointless when `uv sync --frozen --no-dev` already ran once
# at build time.
CMD ["sh", "-c", "uvicorn aevrin_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
