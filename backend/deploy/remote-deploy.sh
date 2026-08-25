#!/usr/bin/env bash
# Runs on the EC2 instance, piped in over SSH by .github/workflows/deploy-backend.yml.
# Kept as a file rather than an inline heredoc so it can be shell-checked, and
# because an indented heredoc terminator inside a YAML block silently swallows
# the rest of the script.
set -euo pipefail

SRC=/home/ec2-user/aevrin
ENV_FILE=/opt/aevrin/api.env

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
sudo docker build -f backend/api/Dockerfile -t aevrin-api:new .

# Keep the outgoing image addressable so the rollback below has a target.
sudo docker tag aevrin-api:latest aevrin-api:previous 2>/dev/null || true
sudo docker tag aevrin-api:new aevrin-api:latest

start_api() {
  sudo docker rm -f api >/dev/null 2>&1 || true
  sudo docker run -d --name api --network aevrin \
    --env-file "$ENV_FILE" --restart unless-stopped \
    aevrin-api:latest >/dev/null
}

health() {
  sudo docker inspect -f '{{.State.Health.Status}}' api 2>/dev/null || echo starting
}

start_api

# Wait on the image's own HEALTHCHECK rather than a fixed sleep: the API opens
# its port well before Trivy's database and the Go scanners have initialised.
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

# Recreating the container can hand it a new address on the docker network,
# and Caddy may still be holding the previous one. A reload costs nothing and
# forces the upstream to be resolved again, so the first request after a
# deploy cannot land on a dead address.
sudo docker exec caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null ||   echo "caddy reload failed; continuing since the container is healthy"

# Each build leaves its predecessor's layers behind and the root volume is
# 30 GB; two or three deploys would fill it otherwise.
sudo docker image prune -f >/dev/null
echo "deployed, container is $(health)"
