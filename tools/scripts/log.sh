log__color_enabled() {
  if [[ -n "${NO_COLOR:-}" ]]; then
    return 1
  fi
  case "${FORCE_COLOR:-}" in
    0) return 1 ;;
    1|2|3) return 0 ;;
  esac
  if [[ ! -t "$1" ]]; then
    return 1
  fi
  if [[ -n "${TERM:-}" ]]; then
    [[ "$TERM" != dumb ]]
    return $?
  fi
  [[ -n "${WT_SESSION:-}" || -n "${ANSICON:-}" || "${ConEmuANSI:-}" == ON || -n "${COLORTERM:-}" ]]
  return $?
}

log__set_colors() {
  if log__color_enabled "$1"; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_DIM=$'\033[2m'
    C_RED=$'\033[1;31m'
    C_GREEN=$'\033[1;32m'
    C_YELLOW=$'\033[1;33m'
    C_CYAN=$'\033[1;36m'
    C_LINK=$'\033[4;36m'
  else
    C_RESET="" C_BOLD="" C_DIM="" C_RED="" C_GREEN="" C_YELLOW="" C_CYAN="" C_LINK=""
  fi
  return 0
}

log_step() {
  log__set_colors 1
  printf '\n%s%s==> %s%s\n' "$C_CYAN" "$C_BOLD" "$*" "$C_RESET"
  return 0
}

log_info() {
  log__set_colors 1
  printf '    %s[INFO]%s %s\n' "$C_CYAN" "$C_RESET" "$*"
  return 0
}

log_ok() {
  log__set_colors 1
  printf '%s[COMPLETED]%s %s\n' "$C_GREEN" "$C_RESET" "$*"
  return 0
}

log_warn() {
  log__set_colors 1
  printf '%s[WARNING]%s %s\n' "$C_YELLOW" "$C_RESET" "$*"
  return 0
}

log_error() {
  log__set_colors 2
  printf '%s[ERROR]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
  return 0
}

log_debug() {
  log__set_colors 1
  printf '%s[DEBUG]%s %s\n' "$C_DIM" "$C_RESET" "$*"
  return 0
}

log_option() {
  log__set_colors 1
  printf '    %s%s)%s %s\n' "$C_CYAN" "$1" "$C_RESET" "$2"
  return 0
}

log_prompt() {
  log__set_colors 1
  printf '%s?%s %s ' "$C_YELLOW" "$C_RESET" "$*"
  return 0
}

log_link() {
  log__set_colors 1
  printf '    %-12s %s%s%s\n' "$1" "$C_LINK" "$2" "$C_RESET"
  return 0
}
