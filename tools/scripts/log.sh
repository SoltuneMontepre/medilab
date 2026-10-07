if [ -z "${NO_COLOR:-}" ]; then
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

log_step() {
  printf '\n%s==>%s %s%s%s\n' "$C_CYAN" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"
}

log_info() {
  printf '    %s%s%s\n' "$C_DIM" "$*" "$C_RESET"
}

log_ok() {
  printf '%s[COMPLETED]%s %s\n' "$C_GREEN" "$C_RESET" "$*"
}

log_error() {
  printf '%s[ERROR]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2
}

log_option() {
  printf '    %s%s)%s %s\n' "$C_CYAN" "$1" "$C_RESET" "$2"
}

log_prompt() {
  printf '%s?%s %s ' "$C_YELLOW" "$C_RESET" "$*"
}

log_link() {
  printf '    %-12s %s%s%s\n' "$1" "$C_LINK" "$2" "$C_RESET"
}
