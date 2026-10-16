#!/usr/bin/env bash
# Runs a build command in CI. If it fails, the relevant lines of its output are also
# published as GitHub annotations, so failures can be read without opening the raw log.
log=$(mktemp)
"$@" 2>&1 | tee "$log"
code=${PIPESTATUS[0]}
if [ "$code" -ne 0 ]; then
  echo "::group::failure summary"
  grep -iE "error|fatal|failed|exception|traceback|not found|denied|cannot|no such" "$log" \
    | grep -viE "warning|0 error|-Werror" | tail -n 25 \
    | while IFS= read -r line; do echo "::error::${line:0:500}"; done
  tail -n 12 "$log" | while IFS= read -r line; do echo "::error::tail: ${line:0:500}"; done
  echo "::endgroup::"
fi
exit "$code"
