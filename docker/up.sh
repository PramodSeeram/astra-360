#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# auto = pick next free port; kill = free target ports first (default)
CONFLICT_MODE="${PORT_CONFLICT_MODE:-kill}"
BACKEND_PORT="${BACKEND_PORT:-8005}"
UI_PORT="${UI_PORT:-8082}"
INTERNAL_QDRANT_PORT="${INTERNAL_QDRANT_PORT:-6333}"

DOCKER_PREFIX=()
COMPOSE_CMD=()

resolve_compose() {
  if docker info >/dev/null 2>&1; then
    DOCKER_PREFIX=()
  elif sudo -n docker info >/dev/null 2>&1; then
    DOCKER_PREFIX=(sudo -E)
  else
    echo "Docker daemon is not accessible. Use sudo or fix docker permissions." >&2
    exit 1
  fi

  if "${DOCKER_PREFIX[@]}" docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=("${DOCKER_PREFIX[@]}" docker compose)
    return
  fi
  if command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=("${DOCKER_PREFIX[@]}" docker-compose)
    return
  fi

  echo "No compose command found (docker compose or docker-compose)." >&2
  exit 1
}

port_in_use() {
  local port="$1"
  ss -ltn "( sport = :${port} )" | awk 'NR>1 {exit 0} END {exit 1}'
}

docker_containers_on_port() {
  local port="$1"
  local ids
  ids="$("${DOCKER_PREFIX[@]}" docker ps -q --filter "publish=${port}" 2>/dev/null || true)"
  if [[ -z "$ids" ]]; then
    local cid
    for cid in $("${DOCKER_PREFIX[@]}" docker ps -q 2>/dev/null); do
      local mapped
      mapped="$("${DOCKER_PREFIX[@]}" docker port "$cid" 2>/dev/null || true)"
      if echo "$mapped" | grep -qE ":${port}$|:${port}->"; then
        ids="${ids}${ids:+ }${cid}"
      fi
    done
  fi
  printf "%s\n" "$ids"
}

kill_port_owners() {
  local port="$1"
  local ids
  ids="$(docker_containers_on_port "$port" || true)"
  if [[ -n "$ids" ]]; then
    echo "Stopping Docker container(s) on port ${port}: ${ids}"
    # shellcheck disable=SC2086
    "${DOCKER_PREFIX[@]}" docker rm -f $ids >/dev/null
  fi

  if port_in_use "$port"; then
    echo "Killing local process(es) on port ${port}"
    if command -v fuser >/dev/null 2>&1; then
      "${DOCKER_PREFIX[@]}" fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    fi
  fi
}

next_free_port() {
  local port="$1"
  while port_in_use "$port"; do
    port=$((port + 1))
  done
  printf '%s\n' "$port"
}

resolve_compose

if [[ "$CONFLICT_MODE" != "auto" && "$CONFLICT_MODE" != "kill" ]]; then
  echo "Invalid PORT_CONFLICT_MODE=$CONFLICT_MODE (use auto or kill)." >&2
  exit 1
fi

if [[ "$CONFLICT_MODE" == "kill" ]]; then
  # Always attempt cleanup so our app gets the requested ports.
  kill_port_owners "$BACKEND_PORT"
  kill_port_owners "$UI_PORT"
else
  if port_in_use "$BACKEND_PORT"; then
    new_backend_port="$(next_free_port "$BACKEND_PORT")"
    echo "Backend port ${BACKEND_PORT} busy, using ${new_backend_port}"
    BACKEND_PORT="$new_backend_port"
  fi
  if port_in_use "$UI_PORT"; then
    new_ui_port="$(next_free_port "$UI_PORT")"
    echo "UI port ${UI_PORT} busy, using ${new_ui_port}"
    UI_PORT="$new_ui_port"
  fi
fi

if [[ "$BACKEND_PORT" == "$UI_PORT" ]]; then
  UI_PORT="$((UI_PORT + 1))"
  while port_in_use "$UI_PORT"; do
    UI_PORT="$((UI_PORT + 1))"
  done
fi

export BACKEND_PORT
export UI_PORT
export QDRANT_PORT="$INTERNAL_QDRANT_PORT"
export VITE_API_BASE="${VITE_API_BASE:-/}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-astraauto-${BACKEND_PORT}-${UI_PORT}}"
export COMPOSE_PROJECT_NAME="$PROJECT_NAME"

# Compose runs from docker/; load repo-root .env so LLM_URL / GPU_EMBED_URL match what you edited.
REPO_ENV_FILE="$(cd "$ROOT_DIR/.." && pwd)/.env"
COMPOSE_ENV_FILE=()
if [[ -f "$REPO_ENV_FILE" ]]; then
  COMPOSE_ENV_FILE=(--env-file "$REPO_ENV_FILE")
fi

echo "Starting compose project ${PROJECT_NAME} with BACKEND_PORT=${BACKEND_PORT}, UI_PORT=${UI_PORT}"
"${COMPOSE_CMD[@]}" "${COMPOSE_ENV_FILE[@]}" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE_CMD[@]}" "${COMPOSE_ENV_FILE[@]}" -p "$PROJECT_NAME" up -d --build

echo
echo "Astra is up:"
echo "  UI:      http://127.0.0.1:${UI_PORT}/"
echo "  Backend: http://127.0.0.1:${BACKEND_PORT}/"
echo
echo "Follow logs:"
echo "  ${COMPOSE_CMD[*]} -p ${PROJECT_NAME} logs -f backend ui"
