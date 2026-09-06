# The API image. It serves requests; it does not scan.
#
# Scanning starts an MCP server, which executes code published by someone
# else, and this image's environment holds the Supabase service-role key -
# which bypasses RLS and is therefore the whole tenancy boundary. So the
# engine and the target run in a separate throwaway container built from
# backend/scanner-image/Dockerfile, launched per scan. This image needs a
# Docker socket to launch it, and no scanner binaries of its own.
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

# The Docker *client*, and only the client. `execution/runner.py` shells out to
# `docker run` to start the sandbox container, so without this every scan fails
# with "docker CLI not found on host" - an honest failure, but one that means
# the product never scans anything. Installed from Docker's own apt repository
# so the download is signature-verified by apt rather than trusted from a URL,
# and so both amd64 and arm64 resolve without hardcoding an architecture.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
      -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=${TARGETARCH} signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# No scanner binaries are installed here any more.
#
# The API does not scan. It resolves a target, starts a one-shot container
# holding the engine and the runtimes an MCP server needs, and reads the
# result. That container is built from backend/scanner-image/Dockerfile and is
# the only place untrusted code runs, which is the whole point: this image
# carries the Supabase service-role key in its environment, and the service
# role bypasses RLS.
#
# Removed with the engine replacement (DECISIONS.md ADR-034): TruffleHog,
# OSV-Scanner and Semgrep, and before them Gitleaks, Trivy, OpenSSF Scorecard
# and MCP-Shield. `git` remains because resolving a GitHub target still means
# cloning it to read its manifests.

# backend/api/pyproject.toml points at its sibling package as
# "../scanner-core", mirror that same one-level relationship inside the
# image (/repo/backend/api and /repo/backend/scanner-core) so the relative
# path resolves the same way it does in the real repo, instead of trying to
# climb above the container's filesystem root.
WORKDIR /repo/backend/api

# --- The application itself, via uv ---
COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /usr/local/bin/uv
ENV UV_PYTHON=3.11
ENV UV_PYTHON_DOWNLOADS=never
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

# Copying the frozen environment into the system interpreter's standard
# import location makes startup independent of both PYTHONPATH and of
# whether /repo is executable. Editable package links still point at the
# read-only application sources under /repo.

# The API runs without root privileges; repository clones live under /tmp.
#
# `docker` is a group here rather than a package: reaching the daemon means
# reaching a unix socket owned by root and group-owned by the host's docker
# group, so the deploy passes that host gid with `--group-add` (see
# backend/deploy/remote-deploy.sh). The group exists in the image only so the
# name resolves; the gid that matters is supplied at run time.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin aevrin \
    && groupadd -f docker \
    && usermod -aG docker aevrin
USER aevrin

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent "http://127.0.0.1:${PORT:-8000}/health" >/dev/null || exit 1
# Launch through the executable system interpreter while importing the exact
# locked environment above. No dependency resolution happens at runtime.
CMD ["sh", "-c", "/usr/local/bin/python -m uvicorn aevrin_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
