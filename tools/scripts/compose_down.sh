# Stops this checkout's stack. Sourced by task stop and task reset.
# Exited containers from an older stack sit on the same network and make compose down fail to
# delete it. Those containers are removed first.
# Usage: . tools/scripts/compose_down.sh [arguments for docker compose down...]
set -e
. tools/scripts/log.sh

compose_down_project() {
  printf '%s\n' "${COMPOSE_PROJECT_NAME:-medilab}"
  return 0
}

compose_down_belongs() {
  id="$1"
  project="$2"
  docker_project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$id")"
  podman_project="$(docker inspect -f '{{index .Config.Labels "io.podman.compose.project"}}' "$id")"
  if [[ "$docker_project" == "$project" || "$podman_project" == "$project" ]]; then
    return 0
  fi
  return 1
}

compose_down_strays() {
  project="$(compose_down_project)"
  network="${project}_default"
  ids="$(docker ps -aq --filter "network=${network}" || true)"
  while IFS= read -r id; do
    id="${id%$'\r'}"
    if [[ -z "$id" ]] || compose_down_belongs "$id" "$project"; then
      continue
    fi
    state="$(docker inspect -f '{{.State.Status}}' "$id")"
    name="$(docker inspect -f '{{.Name}}' "$id")"
    name="${name#/}"
    if [[ "$state" != "exited" && "$state" != "created" && "$state" != "dead" ]]; then
      log_error "${name} is ${state} on ${network}. Stop that container, then run this again."
      exit 1
    fi
    log_info "Removing ${name}. It is not part of this stack and it holds ${network}."
    docker rm "$id" >/dev/null
  done <<END
$ids
END
  return 0
}

compose_down_missing() {
  # podman-compose stops every service by name. A service that was never started has no container,
  # and podman prints that as an error even though compose down still removes the stack.
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    if [[ "$line" == 'Error: no container with name or ID "'*'" found: no such container' ]]; then
      continue
    fi
    if [[ "$line" == 'Error: no container with ID or name "'*'" found: no such container' ]]; then
      continue
    fi
    printf '%s\n' "$line"
  done
  return 0
}

compose_down_run() {
  set +e
  set -o pipefail
  docker compose down "$@" 2>&1 | compose_down_missing
  status="$?"
  set -e
  if [[ "$status" -ne 0 ]]; then
    exit "$status"
  fi
  return 0
}

compose_down_strays
compose_down_run "$@"
