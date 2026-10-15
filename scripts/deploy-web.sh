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
if (( $# > 1 )); then
  printf '用法：sudo bash scripts/deploy-web.sh [离线镜像包.tar.gz]\n' >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  password=$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')
  printf 'ACS_POSTGRES_PASSWORD=%s\nACS_WEB_ORIGIN=http://127.0.0.1:8080\nACS_WEB_BIND=127.0.0.1:8080\n' "$password" > .env
fi
# Add missing settings when upgrading, keeping existing database credentials.
if ! grep -q '^ACS_ADMIN_PASSWORD=.' .env; then
  printf '\nACS_ADMIN_PASSWORD=%s\n' "$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')" >> .env
fi
if ! grep -q '^ACS_CHANNEL_KEY=.' .env; then
  printf '\nACS_CHANNEL_KEY=%s\n' "$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')" >> .env
fi
chmod 600 .env
if (( $# == 1 )); then
  if [[ $(uname -m) != x86_64 || ! -f $1 ]]; then
    printf '离线包需要 Linux x86_64 和有效的镜像包文件。\n' >&2
    exit 1
  fi
  case $(basename "$1") in
    acs-web-linux-amd64.tar.gz) checksum=SHA256SUMS ;;
    acs-web-update-linux-amd64.tar.gz)
      checksum=SHA256SUMS-update
      if ! docker image inspect postgres:17 >/dev/null 2>&1; then
        printf '升级包需要服务器已有 postgres:17 镜像；首次安装请使用完整包。\n' >&2
        exit 1
      fi
      ;;
    *) printf '请保留离线完整包或升级包的原始文件名。\n' >&2; exit 1 ;;
  esac
  (cd "$(dirname "$1")" && sha256sum --check "$checksum")
  docker load --input "$1"
  for image in compressor-service-web:local postgres:17; do
    if [[ $(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$image") != linux/amd64 ]]; then
      printf '镜像架构不匹配：%s\n' "$image" >&2
      exit 1
    fi
  done
  docker compose --env-file .env -f deploy/compose.yaml up -d --no-build --pull never --wait --wait-timeout 180
else
  docker compose --env-file .env -f deploy/compose.yaml up -d --build --wait --wait-timeout 180
fi
printf '\n服务启动成功。服务器内验证：curl -f http://127.0.0.1:8080/healthz\n'
printf '本机预览端口为 8080，公开入口配置见 docs/deployment.md。\n'
printf '首页为管理员工作台；在服务器用 sudo grep ^ACS_ADMIN_PASSWORD= .env 查看登录密码，请勿公开。\n'
