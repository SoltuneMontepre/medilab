#!/usr/bin/env bash
# Loads the Ansible SSH key into an agent, then runs the given command.
# The entrypoint of the Ansible image. Needs ANSIBLE_SSH_PRIVATE_KEY for commands that reach the nodes.
set -e

if [[ -n "${ANSIBLE_SSH_PRIVATE_KEY:-}" ]]; then
  eval "$(ssh-agent -s)" >/dev/null
  printf '%s\n' "$ANSIBLE_SSH_PRIVATE_KEY" | tr -d '\r' | ssh-add -q -
  unset ANSIBLE_SSH_PRIVATE_KEY
fi

exec "$@"
