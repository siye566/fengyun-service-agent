#!/usr/bin/env bash
# Local-only initial deployment. Existing .env and database volumes are kept.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
umask 077
if ! docker info >/dev/null 2>&1; then
  printf '请使用 sudo bash scripts/deploy-web.sh，或使用已有 Docker 权限的账号。\n' >&2
  exit 1
fi
docker compose version >/dev/null
if [[ ! -f .env ]]; then
  password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
  printf 'ACS_POSTGRES_PASSWORD=%s\nACS_WEB_ORIGIN=http://127.0.0.1:8080\nACS_WEB_BIND=127.0.0.1:8080\n' "$password" > .env
fi
docker compose --env-file .env -f deploy/compose.yaml up -d --build --wait --wait-timeout 180
printf '\n服务启动成功。服务器内验证：curl -f http://127.0.0.1:8080/healthz\n'
printf '本机预览端口为 8080，公开入口配置见 docs/deployment.md。\n'
