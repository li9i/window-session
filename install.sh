#!/usr/bin/env bash

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
COMPLETION_DIR="$HOME/.local/share/bash-completion/completions"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE="window-session-save.service"
TIMER="window-session-save.timer"

say() {
  printf '\n==> %s\n' "$1"
}

link() {
  local target="$1" name="$2"
  mkdir -p "$(dirname "$name")"
  ln -sfn "$target" "$name"
  echo "  $name -> $target"
}

echo "Installing window-session from $REPO"

say "1. Packages"
if command -v apt-get >/dev/null 2>&1; then
  echo "This needs root."
  sudo apt-get install -y x11-utils xdotool procps
else
  echo "No apt-get here, so install these yourself:"
  echo "  xprop, xdotool and pgrep"
fi

say "2. Links"
link "$REPO/bin/window-session" "$BIN_DIR/window-session"
link "$REPO/systemd/$SERVICE" "$UNIT_DIR/$SERVICE"
link "$REPO/systemd/$TIMER" "$UNIT_DIR/$TIMER"
link "$REPO/share/bash-completion/completions/window-session" \
  "$COMPLETION_DIR/window-session"

say "3. The timer"
# The link systemd keeps for an enabled timer points at the file the unit link
# resolved to when it was enabled, so a checkout that moved leaves it pointing
# at nothing. enable replaces it. reenable must not be used here: systemd takes
# a unit link that points outside its own directories for one it made, and the
# disable half of reenable deletes it. The restart is what makes a running
# timer take a schedule that changed since it started.
systemctl --user daemon-reload
systemctl --user enable "$TIMER"
systemctl --user restart "$TIMER"
echo "  $TIMER records the open windows every minute"

say "Done"
case ":$PATH:" in
  *":$BIN_DIR:"*)
    echo "window-session is on your path. Try: window-session list"
    ;;
  *)
    echo "$BIN_DIR is not on your path, so the command will not resolve yet."
    echo "The timer does not need it and is recording already. Ubuntu's stock"
    echo "~/.profile puts the directory on the path at login once it exists,"
    echo "and it exists now, so log out and back in. To use it before then:"
    echo
    echo "  $BIN_DIR/window-session list"
    ;;
esac
