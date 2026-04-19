#!/usr/bin/env bash
# Start Qdrant, the FastAPI backend, and the Vite UI. Frees the configured ports first
# (terminates listeners). Logs and PID files go to .astra-logs/ under the repo root.
#
# Optional environment overrides: QDRANT_HTTP_PORT, QDRANT_GRPC_PORT, BACKEND_PORT, UI_PORT
# Docker socket permission: USE_SUDO_DOCKER=1 ./startastra.sh
#   or: sudo usermod -aG docker "$USER"  (then log out and back in)
# If Qdrant, backend, and UI are already up, frees those ports and starts fresh (full restart).
# Otherwise only starts what is down; does not kill components that are still healthy.
# Full teardown + start everything even when only some are up: FORCE_RESTART=1 ./startastra.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  echo "[startastra] Loading configuration from .env"
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | xargs)
fi

QDRANT_HTTP_PORT="${QDRANT_HTTP_PORT:-6333}"
QDRANT_GRPC_PORT="${QDRANT_GRPC_PORT:-6334}"
BACKEND_PORT="${BACKEND_PORT:-${PORT:-8005}}"
UI_PORT="${UI_PORT:-8082}"

LOG_DIR="${LOG_DIR:-$ROOT/.astra-logs}"
mkdir -p "$LOG_DIR"

# Prefer backend/.venv; else system python3 if FastAPI is importable; else create venv + pip install.
resolve_backend_python() {
  local venv_py="$ROOT/backend/.venv/bin/python"
  if [[ -x "$venv_py" ]]; then
    printf '%s\n' "$venv_py"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1 && python3 -c "import fastapi" 2>/dev/null; then
    printf '%s\n' "python3"
    return 0
  fi
  echo "[startastra] Creating backend/.venv and installing Python deps (first run only; may take a few minutes)." >&2
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -q -U pip wheel
  "$ROOT/backend/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
  printf '%s\n' "$ROOT/backend/.venv/bin/python"
}

# Populated when Docker is usable: (docker) or (sudo docker)
DOCKER=()
docker_ok=false

resolve_docker() {
  DOCKER=()
  case "${USE_SUDO_DOCKER:-}" in
    1|true|yes)
      DOCKER=(sudo docker)
      return 0
      ;;
  esac
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
    return 0
  fi
  if sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo docker)
    echo "[startastra] Using sudo for Docker (passwordless sudo for docker is configured)."
    return 0
  fi
  return 1
}

# Stop/remove any container publishing the given host ports (fixes "port is already allocated").
docker_release_host_ports() {
  [[ "$docker_ok" == true ]] || return 0
  local port
  for port in "$@"; do
    local -a cids=()
    mapfile -t cids < <("${DOCKER[@]}" ps -q --filter "publish=$port" 2>/dev/null || true)
    [[ ${#cids[@]} -eq 0 ]] && continue
    echo "[startastra] Stopping Docker container(s) bound to host port ${port} (${cids[*]})"
    local cid
    for cid in "${cids[@]}"; do
      [[ -n "$cid" ]] || continue
      "${DOCKER[@]}" stop "$cid" >/dev/null 2>&1 || true
      "${DOCKER[@]}" rm -f "$cid" >/dev/null 2>&1 || true
    done
  done
}

free_port() {
  local port="$1"
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" >/dev/null 2>&1 || true
  fi
  local pids
  pids="$(lsof -ti:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "[startastra] Freeing port ${port} (PIDs: ${pids//$'\n'/ })"
    # shellcheck disable=SC2086
    kill -TERM ${pids} 2>/dev/null || true
    sleep 0.5
    pids="$(lsof -ti:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -KILL ${pids} 2>/dev/null || true
    fi
  fi
  # Root-owned docker-proxy (or similar) often survives without sudo
  case "${USE_SUDO_DOCKER:-}" in
    1|true|yes)
      if command -v sudo >/dev/null 2>&1 && command -v fuser >/dev/null 2>&1; then
        sudo fuser -k "${port}/tcp" >/dev/null 2>&1 || true
      fi
      ;;
  esac
}

# True if something is accepting TCP on 127.0.0.1:port (bash built-in; no lsof required).
tcp_listening() {
  local port="$1"
  (echo >/dev/tcp/127.0.0.1/"$port") &>/dev/null
}

if command -v docker >/dev/null 2>&1 && resolve_docker; then
  docker_ok=true
fi

force_restart=0
case "${FORCE_RESTART:-0}" in
  1|true|yes) force_restart=1 ;;
esac

q_up=0
b_up=0
u_up=0
if tcp_listening "$QDRANT_HTTP_PORT"; then q_up=1; fi
if curl -sf --max-time 2 "http://127.0.0.1:${BACKEND_PORT}/" >/dev/null 2>&1; then b_up=1; fi
if tcp_listening "$UI_PORT"; then u_up=1; fi

# If all three are already healthy, restart everything (free ports, then start) instead of exiting.
if [[ "$force_restart" != 1 ]] && [[ "$q_up" == 1 && "$b_up" == 1 && "$u_up" == 1 ]]; then
  echo "[startastra] All services already running; freeing ports and restarting."
  force_restart=1
fi

if [[ "$force_restart" == 1 ]]; then
  need_q=1
  need_b=1
  need_u=1
else
  need_q=$((1 - q_up))
  need_b=$((1 - b_up))
  need_u=$((1 - u_up))
fi

if [[ "$need_q" == 1 ]]; then
  docker_release_host_ports "$QDRANT_HTTP_PORT" "$QDRANT_GRPC_PORT"
  free_port "$QDRANT_HTTP_PORT"
  free_port "$QDRANT_GRPC_PORT"
fi
if [[ "$need_b" == 1 ]]; then
  docker_release_host_ports "$BACKEND_PORT"
  free_port "$BACKEND_PORT"
fi
if [[ "$need_u" == 1 ]]; then
  docker_release_host_ports "$UI_PORT"
  free_port "$UI_PORT"
fi

# --- Qdrant ---
if [[ "$need_q" == 1 ]]; then
  if [[ "$docker_ok" == true ]]; then
    echo "[startastra] Starting Qdrant (Docker) - HTTP :${QDRANT_HTTP_PORT}, gRPC :${QDRANT_GRPC_PORT}"
    "${DOCKER[@]}" rm -f astra-qdrant >/dev/null 2>&1 || true
    "${DOCKER[@]}" run -d --name astra-qdrant \
      -p "${QDRANT_HTTP_PORT}:6333" \
      -p "${QDRANT_GRPC_PORT}:6334" \
      qdrant/qdrant:latest
  elif command -v qdrant >/dev/null 2>&1; then
    echo "[startastra] Starting Qdrant (binary) - Docker not usable or not selected"
    nohup qdrant >"$LOG_DIR/qdrant.log" 2>&1 &
    echo $! >"$LOG_DIR/qdrant.pid"
  else
    echo "[startastra] ERROR: Cannot start Qdrant." >&2
    if command -v docker >/dev/null 2>&1; then
      echo "  Docker is installed but denied access to the daemon (e.g. permission denied on /var/run/docker.sock)." >&2
      echo "  Fix one of:" >&2
      echo "    sudo usermod -aG docker \"\$USER\"   # then log out and back in" >&2
      echo "    USE_SUDO_DOCKER=1 $0   # use sudo for docker commands" >&2
    else
      echo "  Install Docker, or install a qdrant binary on PATH." >&2
    fi
    exit 1
  fi
fi

# --- Backend ---
if [[ "$need_b" == 1 ]]; then
  echo "[startastra] Starting backend on :${BACKEND_PORT}"
  BACKEND_PYTHON="$(resolve_backend_python)"
  (
    cd "$ROOT/backend"
    export PORT="$BACKEND_PORT"
    nohup "$BACKEND_PYTHON" main.py >>"$LOG_DIR/backend.log" 2>&1 &
    echo $! >"$LOG_DIR/backend.pid"
  )
fi

# --- UI (Vite) ---
if [[ "$need_u" == 1 ]]; then
  echo "[startastra] Starting UI on :${UI_PORT}"
  (
    cd "$ROOT/MainUI"
    # Vite proxies /api, /chat, etc. to this URL (must match backend port).
    export BACKEND_PROXY_TARGET="${BACKEND_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
    nohup npm run dev -- --host :: --port "$UI_PORT" >>"$LOG_DIR/ui.log" 2>&1 &
    echo $! >"$LOG_DIR/ui.pid"
  )
fi

echo ""
echo "[startastra] Logs: $LOG_DIR"
echo "  Qdrant:  http://127.0.0.1:${QDRANT_HTTP_PORT}/dashboard"
echo "  Backend: http://127.0.0.1:${BACKEND_PORT}/"
echo "  UI:      http://127.0.0.1:${UI_PORT}/"
echo ""
if [[ "$docker_ok" == true ]]; then
  echo "Stop Qdrant: ${DOCKER[*]} rm -f astra-qdrant"
else
  echo "Stop Qdrant: kill \$(cat $LOG_DIR/qdrant.pid)  # if using binary"
fi
echo "Stop backend/UI: kill \$(cat $LOG_DIR/backend.pid)  and  kill \$(cat $LOG_DIR/ui.pid)"
