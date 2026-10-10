#!/usr/bin/env bash

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
SHARE_DIR="$HOME/.local/share/window-session"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="window-session-save.service"
TIMER="window-session-save.timer"
STATE_FILE="$HOME/.local/state/window-session.json"

say() {
  printf '\n==> %s\n' "$1"
}

unlink_ours() {
  local name="$1" target
  if [ ! -L "$name" ]; then
    if [ -e "$name" ]; then
      echo "  $name is not a link this installer made, so it stays"
    fi
    return
  fi
  target="$(readlink -f "$name" || true)"
  case "$target" in
    "$REPO"/*)
      rm -f "$name"
      echo "  removed $name"
      ;;
    *)
      echo "  $name points outside $REPO, so it stays"
      ;;
  esac
}

echo "Uninstalling window-session linked from $REPO"

say "1. The timer"
systemctl --user disable --now "$TIMER"

say "2. Links"
unlink_ours "$BIN_DIR/window-session"
unlink_ours "$UNIT_DIR/$SERVICE"
unlink_ours "$UNIT_DIR/$TIMER"
unlink_ours "$COMPLETION_DIR/window-session"
unlink_ours "$SHARE_DIR/history.bash"
systemctl --user daemon-reload

say "Done"
echo "The checkout at $REPO is untouched, so delete it yourself when you want"
echo "it gone. So is the record of the windows, in case the next thing you do"
echo "is a restore:"
echo
echo "  $STATE_FILE"
