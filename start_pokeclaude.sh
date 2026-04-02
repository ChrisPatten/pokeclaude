#!/bin/zsh
set -euo pipefail
session_name="pokeclaude"

if tmux has-session -t "${session_name}" 2>/dev/null; then
  echo "tmux session '${session_name}' is already running"
  exit 0
fi

tmux new-session -d -s "${session_name}" -e TERM=xterm-256color -e COLORTERM=truecolor \
  'claude --channels plugin:telegram@claude-plugins-official'
echo "started detached tmux session '${session_name}'"