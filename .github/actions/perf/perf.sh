#!/bin/bash
# The Bridge's performance file for one run, and what is done with it. Called by action.yml, one
# command at a time: package, same, packages, run, summary, publish, export, comment. Reads only the environment it is given.
#
#   REPOSITORY_PATH      the repository under test, a directory named as its repository; its counterparts are beside it
#   WHICH                pull-requests | all: the inputs of each adapter's bench/manifest.json to measure
#   SAMPLES              how many fresh processes time each input
#   REFERENCE            true: in place of the timing, one convert of each input under the default executor and one under
#                        the reference executor, for their output digests; on a scheduled run, not at all where every
#                        commit is that of the last verdict, which is under 7 days old and has a row for every input
#                        fed, and without an input that timed out at it
#   REFERENCE_MAX_BYTES  with REFERENCE true: an input of more bytes than this is left out of both
#   OUT                  where the files go
#   SPECIFICATION        a checkout of the specification: bench/compare.mjs is run from it
#   GH_TOKEN             the token every call of gh and every push is made with; only package, publish and comment read it
set -euo pipefail

: "${REPOSITORY_PATH:?}" "${OUT:?}" "${SPECIFICATION:?}"
WHICH="${WHICH:-pull-requests}"
SAMPLES="${SAMPLES:-3}"
REFERENCE="${REFERENCE:-false}"
REFERENCE_MAX_BYTES="${REFERENCE_MAX_BYTES:-5000000}"
repository=$(basename "$(cd "$REPOSITORY_PATH" && pwd)")
workspace=$(dirname "$(cd "$REPOSITORY_PATH" && pwd)")
engine="$workspace/cascade-bridge-rs"
owner="${GITHUB_REPOSITORY%%/*}"
compare="node $SPECIFICATION/bench/compare.mjs"
mkdir -p "$OUT"

adapters() {
  if [ "$repository" = cascade-bridge-rs ]; then
    for directory in "$workspace"/cascade-bridge-adapter-*; do
      [ -f "$directory/bench/manifest.json" ] && echo "$directory"
    done
  else
    echo "$workspace/$repository"
  fi
}

vocabulary_of() {
  local name
  name=$(jq -r '."@graph"[] | ."bridge:cascadeVocabularyRepository"."@id" // empty' "$1/ro-crate-metadata.json" | head -1)
  echo "$workspace/${name##*/}"
}

measured_inputs() {
  # measured_inputs <adapter> <bytes> <test on $most>: "<id> <bytes>" of the manifest's inputs this run measures that the test accepts.
  local not_fed='[]'
  [ -s "$OUT/not-fed.txt" ] && not_fed=$(cut -d' ' -f1 "$OUT/not-fed.txt" | jq -R . | jq -s .)
  jq -r --argjson most "$2" --argjson not_fed "$not_fed" --argjson pull_requests "$([ "$WHICH" = pull-requests ] && echo true || echo false)" \
    ".inputs[] | select(.onPullRequests or (\$pull_requests | not)) | select(.id as \$id | \$not_fed | index(\$id) | not) | select($3) | \"\(.id) \(.bytes)\"" "$1/bench/manifest.json"
}

nightly() {
  [ "$REFERENCE" = true ] && [ "${GITHUB_EVENT_NAME:-}" = schedule ]
}

used_repositories() {
  local adapter
  echo cascade-bridge-rs
  for adapter in $(adapters); do
    basename "$adapter"
    basename "$(vocabulary_of "$adapter")"
  done
}

at_the_last_verdict() {
  # at_the_last_verdict <repository>...: each is at the commit the last verdict recorded; the engine's is the build timed.
  local name now
  for name in "$@"; do
    if [ "$name" = cascade-bridge-rs ]; then now=$(cat "$OUT/engine-commit"); else now=$(git -C "$workspace/$name" rev-parse HEAD); fi
    [ "$(jq -r --arg name "$name" '.commit[$name] // empty' "$OUT/last/$(cat "$OUT/last.stem").json" | tr -d '\r')" = "$now" ] || return 1
  done
}

last_verdict() {
  # Keeps the newest reference verdict of perf-data, with its file, in $OUT/last, and its name in $OUT/last.stem; nothing where there is none.
  local md
  rm -rf "$OUT/last" "$OUT/last.stem"
  authenticated clone --quiet --branch perf-data --depth 1 "$(remote)" "$OUT/last" 2>/dev/null || return 0
  md=$(newest "$OUT/last" 'bridge-reference/*.md')
  if [ -n "$md" ] && [ -f "$OUT/last/${md%.md}.json" ]; then echo "${md%.md}" > "$OUT/last.stem"; fi
  return 0
}

last_verdict_is_a_week_old() {
  # True where the last verdict's day is 7 or more days ago, or cannot be read.
  local day then
  day=$(cut -d/ -f2-4 "$OUT/last.stem" | tr / -)
  then=$(date -u -d "$day" +%s 2>/dev/null) || return 0
  [ $(($(date -u +%s) - then)) -ge $((7 * 86400)) ]
}

last_verdict_covers_every_input() {
  # Every input this run would feed has a row, an output or a timeout, in the last verdict.
  local adapter id bytes
  for adapter in $(adapters); do
    while read -r id bytes; do
      jq -e --arg id "$id" '[.results[] | select(.name | startswith($id + "/output/") or startswith($id + "/timeout/"))] | length > 0' \
        "$OUT/last/$(cat "$OUT/last.stem").json" > /dev/null 2>&1 || return 1
    done < <(measured_inputs "$adapter" "$REFERENCE_MAX_BYTES" '.bytes <= $most')
  done
}

same() {
  # Writes skip=true to the step's output, and $OUT/skipped.md, where a scheduled run has every commit of the last verdict.
  local skip=false stem day recorded
  if nightly; then
    last_verdict
    if [ -f "$OUT/last.stem" ] && ! last_verdict_is_a_week_old; then
      stem=$(cat "$OUT/last.stem")
      recorded=$(jq -r '.commit | keys[]' "$OUT/last/$stem.json" 2>/dev/null | tr -d '\r' | sort) || recorded=
      if [ -n "$recorded" ] && [ "$recorded" = "$(used_repositories | sort -u)" ] && at_the_last_verdict $recorded && last_verdict_covers_every_input; then
        skip=true
        day=$(echo "$stem" | cut -d/ -f2-4 | tr / -)
        echo "::notice::skipped: same commits as $day"
        {
          echo "**Skipped: same commits as $day.** The repository and everything it runs with are at the commits of the last verdict, \`$stem\` on \`perf-data\`, so no reference run was made. This is not a verdict, and nothing was checked. What that run said:"
          echo
          sed '/^$/q' "$OUT/last/$stem.md"
          grep -E '^(EQUIVALENT|UNVERIFIED|NOT EQUIVALENT)' "$OUT/last/$stem.md" | sed 's/^/- /' || true
        } > "$OUT/skipped.md"
      fi
    fi
  fi
  echo "skip=$skip" >> "${GITHUB_OUTPUT:-/dev/null}"
}

not_fed() {
  # "<id> <bytes>" of each input of an adapter this scheduled run feeds that timed out at the last verdict, the engine and the adapter being at its commits; none when that verdict is a week old.
  local adapter id bytes
  nightly && [ -f "$OUT/last.stem" ] && ! last_verdict_is_a_week_old || return 0
  for adapter in $(adapters); do
    at_the_last_verdict cascade-bridge-rs "$(basename "$adapter")" || continue
    while read -r id bytes; do
      if jq -e --arg id "$id" '.results[] | select(.name | startswith($id + "/timeout/"))' "$OUT/last/$(cat "$OUT/last.stem").json" > /dev/null 2>&1; then
        echo "$id $bytes"
      fi
    done < <(measured_inputs "$adapter" "$REFERENCE_MAX_BYTES" '.bytes <= $most')
  done
}

release_commit() {
  # The engine checkout's head where it has a build, else the newest of the last 30 commits of the engine's default branch that has one.
  local sha
  for sha in "$1" $(gh api "repos/$owner/cascade-bridge-rs/commits?sha=main&per_page=30" --jq '.[].sha' 2>/dev/null || true); do
    if gh release view "build-$sha" -R "$owner/cascade-bridge-rs" >/dev/null 2>&1; then echo "$sha"; return 0; fi
  done
  return 1
}

package() {
  local wanted waited=0 found
  if [ "$repository" = cascade-bridge-rs ]; then
    wanted="${PULL_REQUEST_HEAD:-${GITHUB_SHA:?}}"
    # The engine's publish workflow builds this commit; it is waited for, up to 15 minutes.
    until gh release view "build-$wanted" -R "$owner/cascade-bridge-rs" >/dev/null 2>&1; do
      if [ "$waited" -ge 900 ]; then
        echo "::error::no build-$wanted release of $owner/cascade-bridge-rs after 15 minutes"
        exit 1
      fi
      sleep 20
      waited=$((waited + 20))
    done
    found="$wanted"
  else
    wanted=$(git -C "$engine" rev-parse HEAD)
    found=$(release_commit "$wanted") || { echo "::error::none of the last 30 commits of $owner/cascade-bridge-rs has a build release"; exit 1; }
  fi
  echo "the package is the build of $owner/cascade-bridge-rs $found (wanted $wanted)"
  echo "$found" > "$OUT/engine-commit"
  if [ "$found" = "$wanted" ]; then
    echo "The Bridge build timed is \`${found:0:7}\` of \`$owner/cascade-bridge-rs\`." > "$OUT/package.md"
  else
    echo "::warning::wanted the build of $wanted, timed the build of $found"
    echo "**Wanted \`${wanted:0:7}\`, timed \`${found:0:7}\`:** \`$owner/cascade-bridge-rs\` at \`${wanted:0:7}\` has no build release, so the newest of the last 30 commits of its \`main\` that has one was timed." > "$OUT/package.md"
  fi
  local temp
  temp=$(mktemp -d)
  gh release download "build-$found" -R "$owner/cascade-bridge-rs" -p cascade-bridge.tgz -D "$temp"
  local digest expected
  digest=$(sha256sum "$temp/cascade-bridge.tgz" | cut -d' ' -f1)
  expected=$(gh release view "build-$found" -R "$owner/cascade-bridge-rs" --json assets --jq '[.assets[] | select(.name == "cascade-bridge.tgz") | .digest][0]')
  if [ -n "$expected" ] && [ "$expected" != null ] && [ "$expected" != "sha256:$digest" ]; then
    echo "::error::cascade-bridge.tgz has sha256 $digest, where the release names $expected"
    exit 1
  fi
  rm -rf "$engine/package/dist"
  mkdir -p "$engine/package/dist"
  tar -xzf "$temp/cascade-bridge.tgz" -C "$engine/package/dist" --strip-components=1
}

packages() {
  (cd "$engine/hosts/node" && npm ci --ignore-scripts --no-audit --no-fund)
}

bench() {
  # bench <executor-or-empty> <samples> <directory> <most bytes of an input, or empty for every input> <extra bench arguments...>
  local executor="$1" samples="$2" directory="$3" most="$4" adapter name flags=() chosen ids vocabulary
  shift 4
  [ "$WHICH" = pull-requests ] && flags+=(--pull-requests)
  [ -n "$executor" ] && flags+=(--executor "$executor")
  # The glossary's sentences are the rows' `extra`; an engine from before the option has none.
  grep -q -- '--glossary' "$engine/hosts/node/bench.mjs" && flags+=(--glossary "$SPECIFICATION/bench/glossary.json")
  mkdir -p "$directory"
  for adapter in $(adapters); do
    name=$(basename "$adapter")
    chosen=()
    if [ -n "$most" ]; then
      ids=$(measured_inputs "$adapter" "$most" '.bytes <= $most' | cut -d' ' -f1 | paste -sd, -)
      [ -n "$ids" ] || continue
      chosen=(--only "$ids")
    fi
    vocabulary=$(vocabulary_of "$adapter")
    node "$engine/hosts/node/bench.mjs" --inputs "$adapter/bench/manifest.json" "${flags[@]}" "${chosen[@]}" \
      --vocabularies "$vocabulary" --package "$engine/package/dist" --samples "$samples" --allow-fallbacks \
      "$@" --out "$directory/$name.json" > "$directory/$name.md"
  done
  if compgen -G "$directory/*.json" >/dev/null; then
    $compare merge "$directory"/*.json > "$directory/run.json"
  fi
}

run() {
  if [ "$REFERENCE" != true ]; then
    bench "" "$SAMPLES" "$OUT/default" ""
    return
  fi
  local adapter
  : > "$OUT/not-fed.txt"
  not_fed > "$OUT/not-fed.txt.new"
  mv "$OUT/not-fed.txt.new" "$OUT/not-fed.txt"
  for adapter in $(adapters); do
    measured_inputs "$adapter" "$REFERENCE_MAX_BYTES" '.bytes > $most'
  done > "$OUT/left-out.txt"
  # The general evaluator alone, one convert, for the digests it writes; the default executor's, the same way.
  bench "" 1 "$OUT/default" "$REFERENCE_MAX_BYTES" --digest-only
  bench spareval 1 "$OUT/reference" "$REFERENCE_MAX_BYTES" --timeout 3600 --digest-only || echo "::warning::the reference executor's run failed; nothing was checked for equivalence"
}

equivalence() {
  # Writes $OUT/equivalence.md: what the reference executor's outputs and the default's say, or why nothing.
  if [ ! -f "$OUT/reference/run.json" ] || [ ! -f "$OUT/default/run.json" ]; then
    echo "The reference executor (\`--executor spareval\`) wrote no output digests, so output equivalence was not checked." > "$OUT/equivalence.md"
  else
    local status=0
    $compare compare "$OUT/reference/run.json" "$OUT/default/run.json" --name '*/output/*' > "$OUT/equivalence.txt" || status=$?
    {
      if [ "$status" -eq 1 ]; then
        echo "**The default executor does not write the output of the reference executor** (\`--executor spareval\`). The build is not failed on this yet."
      elif [ "$status" -eq 0 ]; then
        echo "The default executor's output digests match the reference executor's (\`--executor spareval\`), or could not be checked as listed."
      else
        echo "Output equivalence could not be checked (exit $status)."
      fi
      echo
      echo '```'
      cat "$OUT/equivalence.txt"
      echo '```'
    } > "$OUT/equivalence.md"
  fi
  if [ -s "$OUT/left-out.txt" ]; then
    {
      echo
      echo "Left out of both, each being over $REFERENCE_MAX_BYTES bytes (id, bytes), which the reference executor does not finish in a job's time:"
      echo
      sed 's/^/- /' "$OUT/left-out.txt"
    } >> "$OUT/equivalence.md"
  fi
  if [ -s "$OUT/not-fed.txt" ]; then
    {
      echo
      echo "Not fed to either, each having timed out at the last verdict, \`$(cat "$OUT/last.stem")\` on \`perf-data\`, with the engine and the adapter at the commits they are at now. Nothing verifies them (id, bytes):"
      echo
      sed 's/^/- /' "$OUT/not-fed.txt"
    } >> "$OUT/equivalence.md"
  fi
}

summary() {
  local adapter name
  {
    if [ "$REFERENCE" = true ]; then
      echo "## Bridge reference executor: $repository @ ${GITHUB_SHA:0:7}"
    else
      echo "## Bridge performance: $repository @ ${GITHUB_SHA:0:7}"
    fi
    echo
    cat "$OUT/package.md"
    echo
    if [ -f "$OUT/skipped.md" ]; then
      cat "$OUT/skipped.md"
    elif [ "$REFERENCE" = true ]; then
      cat "$OUT/equivalence.md"
    else
      for adapter in $(adapters); do
        name=$(basename "$adapter")
        echo "<details><summary>$name</summary>"
        echo
        cat "$OUT/default/$name.md"
        echo
        echo "</details>"
        echo
      done
    fi
  } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
}

authenticated() {
  # git, with the token in a header of its own and never in a URL or a config.
  git -c "http.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)" "$@"
}

remote() {
  echo "${PERF_REMOTE:-https://github.com/${GITHUB_REPOSITORY:?}.git}"
}

publish() {
  # The default executor's file at bridge/, or the reference executor's file and verdict at bridge-reference/.
  local stem attempt work file
  local kept=()
  if [ "$REFERENCE" = true ]; then
    stem="bridge-reference/$(date -u +%Y/%m/%d)/${GITHUB_RUN_NUMBER:?}-${GITHUB_SHA:0:7}"
    [ -f "$OUT/reference/run.json" ] && kept+=("$OUT/reference/run.json|$stem.json")
    kept+=("$OUT/equivalence.md|$stem.md")
  else
    stem="bridge/$(date -u +%Y/%m/%d)/${GITHUB_RUN_NUMBER:?}-${GITHUB_SHA:0:7}"
    kept+=("$OUT/default/run.json|$stem.json")
  fi
  work=$(mktemp -d)
  for attempt in 1 2 3 4 5 6; do
    rm -rf "$work/perf-data"
    if authenticated ls-remote --exit-code --heads "$(remote)" perf-data >/dev/null 2>&1; then
      authenticated clone --quiet --branch perf-data --depth 1 "$(remote)" "$work/perf-data"
    else
      git init --quiet "$work/perf-data"
      git -C "$work/perf-data" checkout --quiet --orphan perf-data
      git -C "$work/perf-data" remote add origin "$(remote)"
    fi
    mkdir -p "$work/perf-data/$(dirname "$stem")"
    for file in "${kept[@]}"; do
      cp "${file%%|*}" "$work/perf-data/${file#*|}"
      git -C "$work/perf-data" add "${file#*|}"
    done
    git -C "$work/perf-data" -c user.name=github-actions[bot] -c user.email=41898282+github-actions[bot]@users.noreply.github.com \
      commit --quiet -m "bridge $([ "$REFERENCE" = true ] && echo reference executor || echo performance) of ${GITHUB_SHA:0:7} (run ${GITHUB_RUN_NUMBER})"
    if authenticated -C "$work/perf-data" push --quiet origin perf-data; then
      echo "wrote $stem to perf-data"
      return 0
    fi
    echo "the push lost a race (attempt $attempt); trying again"
    sleep $((attempt * 3 + RANDOM % 5))
  done
  echo "::error::could not push $stem to perf-data"
  return 1
}

newest() {
  # newest <perf-data checkout> <pathspec>: the newest file it holds, by day and then by run number.
  (cd "$1" && git ls-files "$2" | sort -V | tail -1)
}

comment() {
  local base work verdict body="$OUT/comment.md" marker='<!-- bridge-performance -->'
  {
    echo "$marker"
    echo "## Bridge performance: $repository @ ${PULL_REQUEST_HEAD:0:7}"
    echo
    cat "$OUT/package.md"
    echo
    echo "Timed on a shared runner, so read a change as a hint. Nothing is thresholded and nothing fails on it."
    echo
  } > "$body"
  work=$(mktemp -d)
  if authenticated ls-remote --exit-code --heads "$(remote)" perf-data >/dev/null 2>&1 \
    && authenticated clone --quiet --branch perf-data --depth 1 "$(remote)" "$work"; then
    base=$(newest "$work" 'bridge/*.json')
    verdict=$(newest "$work" 'bridge-reference/*.md')
  fi
  if [ -z "${base:-}" ]; then
    echo "There is no file on \`perf-data\` yet to compare against." >> "$body"
  else
    {
      echo "Against \`$base\` on \`perf-data\`, the newest main run."
      echo
      $compare compare "$work/$base" "$OUT/default/run.json" --name '*/convert/*,*/stage/*,*/load,*/load/*,*/boot/*,*/output/*,*/triples,*/findings' || true
      echo
      echo "<details><summary>every row</summary>"
      echo
      $compare compare "$work/$base" "$OUT/default/run.json" | head -c 50000 || true
      echo
      echo "</details>"
    } >> "$body"
  fi
  {
    echo
    echo "### Reference executor"
    echo
    if [ -z "${verdict:-}" ]; then
      echo "The reference executor (\`--executor spareval\`) runs nightly and on demand, not on a pull request, and no run has kept a verdict on \`perf-data\` yet."
    else
      echo "The reference executor (\`--executor spareval\`) runs nightly and on demand, not on a pull request. The newest run, \`$verdict\` on \`perf-data\`, of \`main\` at \`$(basename "$verdict" .md | cut -d- -f2)\` on $(echo "$verdict" | cut -d/ -f2-4 | tr / -), said:"
      echo
      cat "$work/$verdict"
    fi
  } >> "$body"
  cat "$body" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
  local existing
  existing=$(gh api --paginate "repos/$GITHUB_REPOSITORY/issues/$PULL_REQUEST/comments" --jq ".[] | select(.body | contains(\"$marker\")) | .id" | head -1)
  if [ -n "$existing" ]; then
    gh api -X PATCH "repos/$GITHUB_REPOSITORY/issues/comments/$existing" -F "body=@$body" --silent || echo "::warning::the comment was not updated"
  else
    gh api "repos/$GITHUB_REPOSITORY/issues/$PULL_REQUEST/comments" -F "body=@$body" --silent || echo "::warning::no comment was posted"
  fi
}

case "${1:-}" in
  package) package ;;
  same) same ;;
  packages) packages ;;
  run) run ;;
  summary) if [ "$REFERENCE" = true ] && [ ! -f "$OUT/skipped.md" ]; then equivalence; fi; summary ;;
  publish) if [ "$REFERENCE" = true ] && [ ! -f "$OUT/equivalence.md" ]; then equivalence; fi; publish ;;
  export) $compare export "$OUT/default/run.json" > "$OUT/history.json" ;;
  comment) comment ;;
  *) echo "usage: perf.sh package|same|packages|run|summary|publish|export|comment" >&2; exit 2 ;;
esac
