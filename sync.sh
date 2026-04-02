#!/bin/bash
# sync.sh — Run the sync-save subagent for a given trainer.
#
# Usage: ./sync.sh <user_id>

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <user_id>" >&2
  exit 1
fi

USER_ID="$1"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_ROOT"

claude --agent sync-save -p "Sync the latest save for user_id ${USER_ID}."
