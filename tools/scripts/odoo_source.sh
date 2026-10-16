# Fetches the pinned Odoo source with a sparse checkout of odoo and the given addons. Sourced by task dev:odoo-source.
# Usage: . tools/scripts/odoo_source.sh <dir> <revision> <addon>...
set -e
. tools/scripts/log.sh

DIR="$1"
REV="$2"
shift 2
log_step "Odoo source"
if [[ ! -d "$DIR" ]]; then
  log_info "Downloading Odoo 20.0 at ${REV:0:7}. This takes a minute."
  git clone --quiet --depth 1 --filter=blob:none --sparse --branch 20.0 https://github.com/odoo/odoo.git "$DIR"
  git -C "$DIR" fetch --quiet --depth 1 origin "$REV"
  git -C "$DIR" -c advice.detachedHead=false checkout --quiet --detach "$REV"
elif [[ "$(git -C "$DIR" rev-parse HEAD)" != "$REV" ]]; then
  log_info "Updating the Odoo source to ${REV:0:7}."
  git -C "$DIR" fetch --quiet --depth 1 origin "$REV"
  git -C "$DIR" -c advice.detachedHead=false checkout --quiet --detach "$REV"
fi
addons=""
for addon in "$@"; do
  addons="$addons${addons:+, }$addon"
done
log_info "Checking out odoo and addons: $addons"
git -C "$DIR" sparse-checkout set odoo $(for addon in "$@"; do printf 'addons/%s ' "$addon"; done)
if [[ "$(git -C "$DIR" rev-parse HEAD)" != "$REV" ]] || [[ ! -f "$DIR/odoo/fields/__init__.py" ]]; then
  log_error "$DIR is not at $REV; delete it and run again."
  exit 1
fi
log_info "Linking the addons and the modules into $DIR/odoo/addons."
