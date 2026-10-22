set -euo pipefail
. "$(dirname "$0")/cd_core_argocd.sh"

short=${RELEASE:0:7}
branch="fix/redeploy-$short"
read -ra paths <<< "$IMAGE_PATHS"
mapfile -t commits < <(git log --reverse --format=%H "$PREVIOUS..$RELEASE" -- "${paths[@]}")

conflict=false
for (( i = ${#commits[@]} - 1; i >= 0; i-- )); do
  if ! git revert --no-commit "${commits[i]}" > /dev/null 2>&1; then
    conflict=true
    git revert --abort 2> /dev/null || true
    git reset -q --hard origin/main
    break
  fi
done
sed -i -E "s/^( *newTag: ).*/\1sha-$PREVIOUS/" "$KUSTOMIZATION"
git add -A
{
  echo "[fix] Roll back release $short"
  echo
  if [[ "$conflict" == true ]]; then
    echo "Sets the image back to sha-$PREVIOUS. Reverting the release conflicted with a later commit, so its commits stay on main."
  elif (( ${#commits[@]} == 0 )); then
    echo "Sets the image back to sha-$PREVIOUS."
  else
    echo "Sets the image back to sha-$PREVIOUS and reverts:"
    git log --no-walk --format='- %h %s' "${commits[@]}"
  fi
} > /tmp/rollback-message
git commit -q -F /tmp/rollback-message
for attempt in 1 2 3; do
  git push -q origin HEAD:main && break
  (( attempt < 3 )) || { echo "Main kept moving; the rollback was not pushed." >&2; exit 1; }
  git pull -q --rebase origin main
done

git switch -q -c "$branch"
if [[ "$conflict" == true ]] || (( ${#commits[@]} == 0 )); then
  git commit -q --allow-empty -m "[fix] Redeploy release $short"
else
  git cherry-pick "${commits[@]}" > /dev/null
fi
git push -q --force-with-lease origin "$branch"

labels=failed-release
gh label create failed-release --color B60205 --description "A cd-core release that was rolled back" --force > /dev/null
if [[ "$conflict" == true ]]; then
  labels="$labels,release-blocked"
  gh label create release-blocked --color D93F0B --description "cd-core releases wait until this pull request is merged or closed" --force > /dev/null
fi

assignees=$(for commit in "${commits[@]}"; do
  gh api "repos/{owner}/{repo}/commits/$commit" --jq '.author.login // empty'
done | sort -u | paste -sd, -)

{
  echo "Release \`sha-$RELEASE\` did not become healthy, so cd-core rolled \`main\` back to \`sha-$PREVIOUS\`: $RUN_URL"
  echo
  if [[ "$conflict" == true ]]; then
    echo "Reverting the release conflicted with a later commit, so its commits are still on \`main\` and only the image was set back. Releases wait until this pull request is merged or closed."
  else
    echo "This branch puts back the release's commits. Push a fix to it, then mark it ready."
  fi
  echo
  if (( ${#commits[@]} > 0 )); then
    echo "## Commits"
    echo
    git log --no-walk --format='- %h %s (%an)' "${commits[@]}"
    echo
  fi
  echo "## Argo CD"
  echo
  echo '```text'
  argo app get odoo 2>&1 | head -n 80 || true
  echo '```'
  echo
  echo "## Logs"
  echo
  echo '```text'
  argo app logs odoo --tail 200 2>&1 | tail -n 200 || true
  echo '```'
} > /tmp/redeploy-body

gh pr create --draft --base main --head "$branch" \
  --title "[fix] Redeploy release $short" \
  --body-file /tmp/redeploy-body \
  --label "$labels" \
  ${assignees:+--assignee "$assignees"}

echo "Rolled back to sha-$PREVIOUS; the release is kept on $branch." >&2
exit 1
