#!/usr/bin/env bash
set -euo pipefail

# Generate the bundled CLI git-info file (ngencerf/git_info.json). PyInstaller embeds
# it via --add-data, and `ngencerf version` / `ngencerf about` read it at runtime.
#
# Split out of build_cli.sh so it can run on the CI host (which has git + jq + the full
# tag history) BEFORE the Linux build. The Linux build runs inside a manylinux2014
# container that has neither jq nor the full checkout, so build_cli.sh reuses the file
# this script produces instead of regenerating it there.

# Move to the CLI directory so relative paths resolve the same way build_cli.sh does.
cd "$(dirname "$0")"

echo "==> Generating CLI git info..."

git fetch --force --tags origin '+refs/tags/*:refs/tags/*' 2>/dev/null || true

jq -n \
  --arg commit_hash "$(git rev-parse HEAD 2>/dev/null || echo unknown)" \
  --arg branch "$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)" \
  --arg tags "$(git tag --points-at HEAD 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//')" \
  --arg author "$(git log -1 --pretty=format:'%an' 2>/dev/null || echo unknown)" \
  --arg commit_date "$(git log -1 --pretty=format:'%cI' 2>/dev/null || echo unknown)" \
  --arg message "$(git log -1 --pretty=format:'%s' 2>/dev/null | tr '\n' ';' || echo unknown)" \
  --arg build_date "$(date -u +'%Y-%m-%d %H:%M:%S UTC')" \
  '{
    "ngencerf-cli": {
      commit_hash: $commit_hash,
      branch: $branch,
      tags: $tags,
      author: $author,
      commit_date: $commit_date,
      message: $message,
      build_date: $build_date
    }
  }' \
  > ngencerf/git_info.json
