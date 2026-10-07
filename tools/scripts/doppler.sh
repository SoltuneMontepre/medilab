doppler_login() {
  if ! command -v doppler >/dev/null 2>&1; then
    log_error "doppler not found. Install: winget install Doppler.doppler"
    exit 1
  fi
  if doppler whoami >/dev/null 2>&1; then
    return
  fi
  printf 'How would you like to authenticate?\n'
  log_option 1 "Paste an existing service token"
  log_option 2 "Authenticate with browser"
  cr=$(printf '\r')
  log_prompt "Choose [1/2]:"
  read -r choice
  choice="${choice%"$cr"}"
  case "$choice" in
    1)
      log_prompt "Doppler token:"
      read -r token
      token="${token%"$cr"}"
      MSYS_NO_PATHCONV=1 doppler configure set token "$token" --scope /
      ;;
    2)
      MSYS_NO_PATHCONV=1 doppler login --scope /
      ;;
    *)
      log_error "Invalid choice." && exit 1
      ;;
  esac
  doppler whoami >/dev/null 2>&1 || { log_error "Doppler authentication failed."; exit 1; }
}
