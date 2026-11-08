#!/bin/bash
# Runs a step of the release's module upgrade with the modules in MEDILAB_MODULES. medilab records the fingerprint of
# the image it was last upgraded with, so a sync of that image changes nothing.
#   check     touches SKIP_FILE when medilab is empty, with nothing to protect, or already has this image's fingerprint
#   rehearse  upgrades medilab_rehearsal, unless SKIP_FILE exists
#   release   upgrades medilab and records the fingerprint, unless medilab already has it
set -euo pipefail

here=$(dirname "$0")
step="$1"

fingerprint() {
  python3 "$here/fingerprint.py" compute "$MEDILAB_MODULES"
}

# Reads fail the step rather than pass for an empty or never-upgraded database.
recorded=""
read_recorded() {
  recorded=$(python3 "$here/fingerprint.py" read medilab)
}

upgrade() {
  /entrypoint.sh odoo --database="$1" --init="$MEDILAB_MODULES" --update=all --max-cron-threads=0 --stop-after-init
}

case "$step" in
  check)
    installed=$(python3 "$here/fingerprint.py" installed medilab)
    if [[ "$installed" == no ]]; then
      echo "medilab is empty; the rehearsal is skipped."
      touch "$SKIP_FILE"
      exit 0
    fi
    current=$(fingerprint)
    read_recorded
    if [[ "$recorded" == "$current" ]]; then
      echo "medilab was already upgraded with this image; the rehearsal is skipped."
      touch "$SKIP_FILE"
    fi
    ;;
  rehearse)
    if [[ -f "$SKIP_FILE" ]]; then
      exit 0
    fi
    upgrade medilab_rehearsal
    ;;
  release)
    current=$(fingerprint)
    read_recorded
    if [[ "$recorded" == "$current" ]]; then
      echo "medilab was already upgraded with this image; the upgrade is skipped."
      exit 0
    fi
    upgrade medilab
    python3 "$here/fingerprint.py" record medilab "$current"
    ;;
  *)
    echo "Unknown step: $step" >&2
    exit 2
    ;;
esac
