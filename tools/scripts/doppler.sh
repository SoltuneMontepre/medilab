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
      doppler configure set token "$token"
      ;;
    2)
      doppler login
      ;;
    *)
      log_error "Invalid choice." && exit 1
      ;;
  esac
  doppler whoami >/dev/null 2>&1 || { log_error "Doppler authentication failed."; exit 1; }
}

doppler_user_token() {
  token=$(doppler configs tokens create "mcp-$COMPUTERNAME" --project "$1" --config "$2" --plain)
  if [ -z "$token" ]; then
    log_error "Could not create a Doppler service token."
    exit 1
  fi
  setx DOPPLER_TOKEN "$token" >/dev/null
}
