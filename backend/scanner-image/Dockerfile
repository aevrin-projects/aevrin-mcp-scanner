# The sandbox an untrusted MCP server is scanned inside.
#
# This image exists because scanning an MCP server means *running* it, and
# running it means executing code chosen by whoever published the package.
# `npx -y <package>` downloads that code and runs its npm lifecycle scripts
# before a single tool has been enumerated. The container is therefore
# treated as compromised from the moment it starts, and everything below is
# about limiting what a compromise is worth.
#
# What it deliberately does NOT contain:
#   - any Aevrin credential, config file, or environment variable
#   - the API source, the Supabase service-role key, or provider keys
#   - a shell history, an SSH key, or a cloud credential file
#
# The container is started with --read-only, --cap-drop ALL,
# --security-opt no-new-privileges, memory/CPU/pid ceilings and a hard
# timeout by `mcp/tooltrust.py`; those are runtime flags rather than image
# properties, so they live there and are documented in
# docs/security/SECURITY.md.
#
# Network access cannot be removed - the package has to be downloaded - so it
# is the residual exposure. On the deployed host, EC2 IMDSv2 with a hop limit
# of 1 refuses requests from behind Docker's NAT, which is what stops this
# container reaching instance credentials. That is a deployment precondition;
# see docs/architecture/DEPLOYMENT.md.

FROM node:22-bookworm-slim

# uv provides `uvx`, which launches Python-published MCP servers the same way
# npx launches npm-published ones.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uvx /usr/local/bin/uvx

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# The engine, pinned to an exact release and verified against the checksum
# published with it.
#
# The upstream project offers `curl -sfL .../install.sh | bash`. That is not
# used here: it resolves "latest" at build time, so two builds of the same
# Dockerfile could ship different security engines, and it executes a remote
# script unverified. A security scanner that cannot say which version
# produced a finding cannot support a result, so the version is pinned and
# the download is checksummed.
ARG SCANNER_VERSION=0.3.19
ARG SCANNER_SHA256=a0b397d125a98080a39c05c1156f54b79e57234477b08205e7d84053f7f6e3c9
RUN curl -sSfL -o /usr/local/bin/mcp-scanner \
      "https://github.com/AgentSafe-AI/tooltrust-scanner/releases/download/v${SCANNER_VERSION}/tooltrust-scanner_linux_amd64" \
    && echo "${SCANNER_SHA256}  /usr/local/bin/mcp-scanner" | sha256sum -c - \
    && chmod 0755 /usr/local/bin/mcp-scanner

# Matches the uid the runtime flags pin, so the tmpfs mounts are writable by
# the process that needs them. Untrusted code does not run as root even
# inside a disposable container.
RUN useradd --create-home --uid 10002 --shell /usr/sbin/nologin scanner
USER 10002:10002
WORKDIR /tmp

ENTRYPOINT ["/usr/local/bin/mcp-scanner"]
