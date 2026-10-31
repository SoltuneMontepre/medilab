# Makes the Odoo image of a Claude Code cloud session available: pulls it, and when the session's proxy refuses the
# pull, builds it from the cloud Dockerfile on the base image of the production Dockerfile, through the proxy.
# Sourced by task ai:image. Usage: . tools/scripts/ai_image.sh <image> <production Dockerfile> <cloud Dockerfile> <core project dir> <proxy CA file>
set -e
. tools/scripts/log.sh

IMAGE="$1"
PROD_DOCKERFILE="$2"
CLOUD_DOCKERFILE="$3"
PROJECT_DIR="$4"
PROXY_CA="$5"
log_step "Odoo image"
if docker image inspect "$IMAGE" > /dev/null 2>&1; then
  log_ok "$IMAGE is present."
elif docker pull --quiet "$IMAGE" > /dev/null 2>&1; then
  log_ok "Pulled $IMAGE."
else
  if [[ ! -f "$PROXY_CA" ]]; then
    log_error "Could not pull $IMAGE, and $PROXY_CA is missing to build it through the proxy."
    exit 1
  fi
  log_info "Could not pull $IMAGE. Building it through the proxy; this takes a few minutes."
  base=$(sed -n 's/^ARG ODOO_IMAGE=//p' "$PROD_DOCKERFILE")
  context=$(mktemp -d)
  cp "$PROJECT_DIR/pyproject.toml" "$PROJECT_DIR/uv.lock" "$context/"
  cp "$(command -v uv)" "$context/uv"
  if docker build --quiet --network host --secret id=proxy_ca,src="$PROXY_CA" \
    --build-arg ODOO_IMAGE="$base" --build-arg HTTPS_PROXY="$HTTPS_PROXY" --build-arg HTTP_PROXY="${HTTP_PROXY:-$HTTPS_PROXY}" \
    -f "$CLOUD_DOCKERFILE" -t "$IMAGE" "$context" > /dev/null; then
    rm -rf "$context"
    log_ok "Built $IMAGE."
  else
    rm -rf "$context"
    log_error "Could not build $IMAGE."
    exit 1
  fi
fi
