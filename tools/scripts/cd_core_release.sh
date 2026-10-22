set -euo pipefail

skip() {
  echo "$1"
  echo "released=false" >> "$GITHUB_OUTPUT"
  exit 0
}

day_in() {
  local today=$1 list=$2 part from to
  local -A index=([Mon]=1 [Tue]=2 [Wed]=3 [Thu]=4 [Fri]=5 [Sat]=6 [Sun]=7)
  for part in ${list//,/ }; do
    from=${index[${part%-*}]}
    to=${index[${part#*-}]}
    if (( from <= to )); then
      (( today >= from && today <= to )) && return 0
    else
      (( today >= from || today <= to )) && return 0
    fi
  done
  return 1
}

hour_in() {
  local hour=$((10#$1)) start=${2%-*} end=${2#*-}
  if (( start <= end )); then
    (( hour >= start && hour < end ))
  else
    (( hour >= start || hour < end ))
  fi
}

if [[ "$FORCE" != true ]]; then
  if [[ "$RELEASE_MODE" == window ]]; then
    [[ "$EVENT" == schedule ]] || skip "Window mode releases only on the hourly schedule."
    day_in "$(TZ=Asia/Ho_Chi_Minh date +%u)" "$RELEASE_DAYS" || skip "Today is outside $RELEASE_DAYS."
    hour_in "$(TZ=Asia/Ho_Chi_Minh date +%H)" "$RELEASE_HOURS" || skip "The hour is outside $RELEASE_HOURS."
  else
    [[ "$EVENT" != schedule ]] || skip "Continuous mode releases after publish, not on the schedule."
  fi
fi

blocked=$(gh pr list --state open --label release-blocked --json url --jq '.[0].url')
[[ -z "$blocked" ]] || skip "Releases wait until $blocked is merged or closed."

previous=$(sed -nE 's/^ *newTag: sha-([0-9a-f]{40})$/\1/p' "$KUSTOMIZATION")
release=""
for commit in $(git log -n 50 --format=%H origin/main); do
  if docker buildx imagetools inspect "$IMAGE:sha-$commit" > /dev/null 2>&1; then
    release=$commit
    break
  fi
done
[[ -n "$release" ]] || skip "No commit among the newest 50 on main has an image."
[[ "$release" != "$previous" ]] || skip "sha-$release is already released."

sed -i -E "s/^( *newTag: ).*/\1sha-$release/" "$KUSTOMIZATION"
git add "$KUSTOMIZATION"
git commit -q -m "[chore] Release ${release:0:7}"
for attempt in 1 2 3; do
  git push -q origin HEAD:main && break
  (( attempt < 3 )) || { echo "Main kept moving; the release was not pushed." >&2; exit 1; }
  git pull -q --rebase origin main
done

{
  echo "released=true"
  echo "release=$release"
  echo "previous=$previous"
  echo "commit=$(git rev-parse HEAD)"
} >> "$GITHUB_OUTPUT"
echo "Released sha-$release over sha-$previous."
