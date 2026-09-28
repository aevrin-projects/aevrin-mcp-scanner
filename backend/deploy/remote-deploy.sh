#!/usr/bin/env bash
# Runs on the EC2 instance, piped in over SSH by .github/workflows/deploy-backend.yml.
# Kept as a file rather than an inline heredoc so it can be shell-checked, and
# because an indented heredoc terminator inside a YAML block silently swallows
# the rest of the script.
set -euo pipefail

SRC=/home/ec2-user/aevrin
ENV_FILE=/opt/aevrin/api.env

# `tee -a` appends bytes after whatever is already in the file, with no
# newline of its own. If ENV_FILE's last byte isn't already a newline, the
# next append lands on the end of the previous line instead of starting a
# new one -- silently merging two variables into one unrecognisable key and
# losing the appended one entirely, with no error anywhere. Both append
# sites below (overrides, and the encryption-key mint) depend on this.
if [ -s "$ENV_FILE" ] && [ "$(sudo tail -c1 "$ENV_FILE" | wc -l)" -eq 0 ]; then
  printf '\n' | sudo tee -a "$ENV_FILE" >/dev/null
fi

# Environment values shipped by the deploy, one KEY=VALUE per line, written
# by the workflow from a repository secret. Applied before anything reads the
# file so the container below starts with them.
#
# This exists because editing /opt/aevrin/api.env over SSH and restarting is
# how values have gone missing and gone stale: `docker restart` does not
# re-read --env-file, so a hand-edited value can sit in the file for days
# while the running container still has the old one. Going through the
# deploy makes the change and the container recreation the same action.
#
# Only ever adds or replaces the keys it is given; nothing is removed, so a
# value set by hand and not present here survives untouched.
OVERRIDES=/home/ec2-user/env-overrides
if [ -f "$OVERRIDES" ]; then
  applied=0
  while IFS= read -r line || [ -n "$line" ]; do
    # Shape check, not a value check: a stray blank or comment line must not
    # become a key, and the values themselves are never echoed anywhere.
    case "$line" in
      [A-Z]*=*)
        key="${line%%=*}"
        echo "override line matched, key=${key}, line length=${#line}"
        sudo sed -i "/^${key}=/d" "$ENV_FILE"
        echo "$line" | sudo tee -a "$ENV_FILE" >/dev/null
        applied=$((applied + 1))
        ;;
    esac
  done < "$OVERRIDES"
  shred -u "$OVERRIDES" 2>/dev/null || rm -f "$OVERRIDES"
  sudo chmod 600 "$ENV_FILE"
  echo "env overrides applied: ${applied} key(s)"
fi

# Key names only, never values -- visibility into what's actually configured
# without risking a value in the deploy log.
echo "env file now defines: $(sudo grep -oE '^[A-Z_]+=' "$ENV_FILE" | sed 's/=$//' | tr '\n' ' ')"

# The API stores two things encrypted with one Fernet key: customer BYOK
# provider keys, and admin TOTP secrets. It was documented under the BYOK
# feature and never set here, so /admin could not enrol an authenticator at
# all -- it answered "Encryption isn't configured on the API" and locked the
# panel out for everyone. Mint one if the env file has none, so a fresh
# instance cannot come up missing it again.
#
# Only ever fills a blank. An existing key is left exactly as it is: every
# secret already stored is unreadable under a different one, and silently
# rotating it on deploy would lock out the admins it just let in.
if sudo grep -q '^BYOK_ENCRYPTION_KEY=.\+' "$ENV_FILE"; then
  echo "encryption key: present"
else
  # openssl rather than python: this runs before any image is built, and a
  # url-safe base64 32-byte value is exactly what Fernet accepts.
  sudo sed -i '/^BYOK_ENCRYPTION_KEY=/d' "$ENV_FILE"
  echo "BYOK_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')" |
    sudo tee -a "$ENV_FILE" >/dev/null
  sudo chmod 600 "$ENV_FILE"
  echo "encryption key: generated a new one (back up $ENV_FILE)"
fi

# Unpack beside the live tree and swap, so a failed extraction never leaves a
# half-written source directory behind.
rm -rf "${SRC}.new"
mkdir -p "${SRC}.new"
tar xzf /home/ec2-user/src.tgz -C "${SRC}.new"
rm -f /home/ec2-user/src.tgz
rm -rf "$SRC"
mv "${SRC}.new" "$SRC"

cd "$SRC"

# The sandbox image every scan runs inside. Built here because the API starts
# it by name (AEVRIN_SCANNER_IMAGE, default aevrin/mcp-scanner:<version>) and
# never pulls it: an image that is missing at scan time fails the scan, and a
# `docker run` that silently pulled from a public registry would be a supply
# chain nobody reviewed. The tag carries the engine version, so a version bump
# builds a new image rather than mutating the old one.
SCANNER_TAG="aevrin/mcp-scanner:$(sed -n 's/^ARG SCANNER_VERSION=//p' backend/scanner-image/Dockerfile | head -1)"
sudo docker build -t "$SCANNER_TAG" -f backend/scanner-image/Dockerfile backend/scanner-image

sudo docker build -f backend/api/Dockerfile -t aevrin-api:new .

# Ask the database whether it has what the new image needs, from a throwaway
# container, before the live one is touched. `/health` would catch drift too,
# but only after the swap: the new container takes live traffic while it waits
# to be judged, so a missing migration meant three minutes of 500s followed by
# a rollback. This way that deploy stops here with the live API untouched.
if ! sudo docker run --rm --env-file "$ENV_FILE" aevrin-api:new \
    python -m aevrin_api.services.schema_check; then
  echo "the database is behind this build; the live API was not touched."
  echo "apply the migration named above, then re-run the deploy."
  exit 1
fi

# Keep the outgoing image addressable so the rollback below has a target.
sudo docker tag aevrin-api:latest aevrin-api:previous 2>/dev/null || true
sudo docker tag aevrin-api:new aevrin-api:latest

# The API starts a sibling container per scan (DECISIONS.md ADR-034), which
# means reaching this host's Docker daemon. Two things are needed and both were
# missing: the socket itself, and membership of the group that owns it - the
# API runs as uid 10001, and the socket is root:docker 0660, so without the gid
# every scan fails on a permission error.
#
# Read from the host rather than hardcoded: the docker group's gid differs
# between Amazon Linux, Debian and Ubuntu, and a wrong constant fails the same
# way as no group at all.
DOCKER_GID="$(getent group docker | cut -d: -f3)"
if [ -z "$DOCKER_GID" ]; then
  echo "no docker group on this host; the API could not start scan containers" >&2
  exit 1
fi

start_api() {
  sudo docker rm -f api >/dev/null 2>&1 || true
  sudo docker run -d --name api --network aevrin \
    --env-file "$ENV_FILE" --restart unless-stopped \
    -v /var/run/docker.sock:/var/run/docker.sock \
    --group-add "$DOCKER_GID" \
    aevrin-api:latest >/dev/null
}

health() {
  sudo docker inspect -f '{{.State.Health.Status}}' api 2>/dev/null || echo starting
}

start_api

# Wait on the image's own HEALTHCHECK rather than a fixed sleep: the API opens
# its port well before the API has finished its own start-up work.
for _ in $(seq 1 36); do
  [ "$(health)" = "healthy" ] && break
  sleep 5
done

if [ "$(health)" != "healthy" ]; then
  echo "new image never became healthy after 3 minutes; rolling back"
  sudo docker logs api --tail 40 || true
  if sudo docker image inspect aevrin-api:previous >/dev/null 2>&1; then
    sudo docker tag aevrin-api:previous aevrin-api:latest
    start_api
    echo "rolled back to the previous image"
  else
    echo "no previous image to roll back to"
  fi
  exit 1
fi

# ------------------------------------------------------------------
# The hosted Aevrin Registry MCP endpoint (https://api.mcp.aevrin.net/mcp).
#
# Its own container: it speaks MCP and nothing else, holds no database
# credential and no env file, and reads the registry through the API's public
# endpoints over the private network - so it is started only once the API it
# depends on is healthy. It serves the registry tools only; the scan tool is
# not registered in it in any configuration (registry_mcp.py).
REGISTRY_FAILED=0
sudo docker build -f backend/cli/Dockerfile.registry-mcp -t aevrin-registry-mcp:new .
sudo docker tag aevrin-registry-mcp:latest aevrin-registry-mcp:previous 2>/dev/null || true
sudo docker tag aevrin-registry-mcp:new aevrin-registry-mcp:latest

start_registry() {
  sudo docker rm -f registry-mcp >/dev/null 2>&1 || true
  sudo docker run -d --name registry-mcp --network aevrin --restart unless-stopped \
    -e AEVRIN_API_URL=http://api:8000 \
    -e AEVRIN_MCP_ALLOWED_HOSTS=api.mcp.aevrin.net \
    -e AEVRIN_WEB_URL=https://app.mcp.aevrin.net \
    aevrin-registry-mcp:latest >/dev/null
}

registry_health() {
  sudo docker inspect -f '{{.State.Health.Status}}' registry-mcp 2>/dev/null || echo starting
}

start_registry
for _ in $(seq 1 24); do
  [ "$(registry_health)" = "healthy" ] && break
  sleep 5
done
if [ "$(registry_health)" != "healthy" ]; then
  echo "registry-mcp never became healthy after 2 minutes; rolling it back"
  sudo docker logs registry-mcp --tail 40 || true
  if sudo docker image inspect aevrin-registry-mcp:previous >/dev/null 2>&1; then
    sudo docker tag aevrin-registry-mcp:previous aevrin-registry-mcp:latest
    start_registry
  fi
  # The API is deployed and healthy either way. The failure is still reported
  # at the end, so the run goes red rather than looking like a clean deploy.
  REGISTRY_FAILED=1
fi

# ------------------------------------------------------------------
# Caddy.
#
# The repository's Caddyfile is installed into the running Caddy, which is
# what makes a new route - like /mcp above - take effect at all. Until this,
# the deploy only reloaded whatever Caddy already had, so a routing change in
# the repository never reached production.
#
# The live file is not something this repository can see, so installing over
# it is guarded three ways: the new file must validate inside Caddy; it must
# not drop any site the live config serves (a site defined only on the host
# would otherwise vanish silently, and a reload would not fail to warn us);
# and the live file is kept, and restored if the reload fails. Any refusal
# leaves the running config exactly as it was.
sites() {
  # Site addresses: top-level lines that open a block, other than the global
  # options block. Enough to tell whether one config serves a site the other
  # does not.
  grep -E '^[^[:space:]#{][^{]*\{[[:space:]]*$' | sed -E 's/[[:space:]]*\{[[:space:]]*$//' | sort -u
}

install_caddyfile() {
  local live missing
  if ! sudo docker exec caddy test -f /etc/caddy/Caddyfile; then
    echo "caddy: no /etc/caddy/Caddyfile in the container; not installing"
    return 1
  fi
  sudo docker cp backend/deploy/Caddyfile caddy:/etc/caddy/Caddyfile.new
  if ! sudo docker exec caddy caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile >/dev/null 2>&1; then
    echo "caddy: the repository Caddyfile does not validate; keeping the live one"
    sudo docker exec caddy caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile 2>&1 | tail -5 || true
    return 1
  fi
  live="$(sudo docker exec caddy cat /etc/caddy/Caddyfile | sites)"
  missing="$(comm -23 <(printf '%s\n' "$live") <(sites < backend/deploy/Caddyfile))"
  if [ -n "$missing" ]; then
    echo "caddy: the live config serves sites the repository Caddyfile does not: ${missing//$'\n'/, }"
    echo "caddy: keeping the live config. Add those sites to backend/deploy/Caddyfile to install it."
    return 1
  fi
  sudo docker exec caddy cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.prev
  # `cat >` rather than `mv`: if the file is a bind mount, it cannot be
  # replaced by a rename, only written through.
  sudo docker exec caddy sh -c 'cat /etc/caddy/Caddyfile.new > /etc/caddy/Caddyfile'
  if ! sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    echo "caddy: reload failed with the new Caddyfile; restoring the previous one"
    sudo docker exec caddy sh -c 'cat /etc/caddy/Caddyfile.prev > /etc/caddy/Caddyfile'
    sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1 || true
    return 1
  fi
  echo "caddy: repository Caddyfile installed and reloaded"
}

CADDY_FAILED=0
if ! install_caddyfile; then
  CADDY_FAILED=1
  # Recreating the containers can hand them new addresses on the docker
  # network, and Caddy may still be holding the previous ones. A reload of the
  # config it already has forces the upstreams to be resolved again.
  sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null ||
    echo "caddy reload failed; continuing since the containers are healthy"
fi

# Each build leaves its predecessor's layers behind and the root volume is
# 30 GB; two or three deploys would fill it otherwise.
sudo docker image prune -f >/dev/null
echo "deployed, api is $(health), registry-mcp is $(registry_health)"

if [ "$REGISTRY_FAILED" -ne 0 ] || [ "$CADDY_FAILED" -ne 0 ]; then
  echo "the API is live, but the registry MCP endpoint is not (registry=${REGISTRY_FAILED}, caddy=${CADDY_FAILED})" >&2
  exit 1
fi
