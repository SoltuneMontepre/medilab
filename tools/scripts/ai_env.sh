# Writes the variables of a Claude Code cloud environment to an env file, filling each empty one from Doppler.
# Sourced by task ai:env. Usage: . tools/scripts/ai_env.sh <template> <output file> <Doppler project> <Doppler config>
set -e
. tools/scripts/log.sh

TEMPLATE="$1"
OUT="$2"
cr=$(printf '\r')
log_step "Cloud environment variables"
mkdir -p "${OUT%/*}"
: > "$OUT"
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%"$cr"}"
  case "$line" in
    '' | '#'*) ;;
    *=)
      name="${line%=}"
      if ! value=$(doppler secrets get "$name" --plain --project "$3" --config "$4"); then
        rm -f "$OUT"
        log_error "Could not read $name from Doppler $3 $4. Check that it exists and that your login can read it."
        exit 1
      fi
      if [[ "$value" == *$'\n'* ]]; then
        rm -f "$OUT"
        log_error "$name spans several lines, which an env file cannot hold. Add it to the environment by hand."
        exit 1
      fi
      printf '%s=%s\n' "$name" "$value" >> "$OUT"
      ;;
    *) printf '%s\n' "$line" >> "$OUT" ;;
  esac
done < "$TEMPLATE"
log_ok "Wrote $OUT. Paste its contents into the cloud environment's settings under Environment variables, then delete it."
