# Keep a journal of the commands typed in this shell, one file per shell, so
# that window-session can give a restored terminal window the commands that
# were typed in it.
#
# Source this file from ~/.bashrc and call _window_session_journal from
# PROMPT_COMMAND. The journal is named after the process id of the shell and
# its start time, which is how window-session finds it from the outside.
#
# A shell that window-session restores finds WINDOW_SESSION_HISTORY set to a
# file of the commands of the window it stands in for. Bash reads its own
# history file only after ~/.bashrc, so those commands are read at the first
# prompt instead. That puts them on top of the shared history, where the up
# arrow finds them first, and they go into the journal of the new shell too.

WINDOW_SESSION_JOURNALS="$HOME/.local/state/window-session/journals"
read -r -a _window_session_stat < "/proc/$$/stat"
WINDOW_SESSION_JOURNAL="$WINDOW_SESSION_JOURNALS/$$-${_window_session_stat[21]}"

_window_session_journal() {
  local line
  if [ -z "$_window_session_histcmd" ]; then
    mkdir -p "$WINDOW_SESSION_JOURNALS"
    if [ -n "$WINDOW_SESSION_HISTORY" ]; then
      history -r "$WINDOW_SESSION_HISTORY"
      cat "$WINDOW_SESSION_HISTORY" >> "$WINDOW_SESSION_JOURNAL"
      rm -f "$WINDOW_SESSION_HISTORY"
      unset WINDOW_SESSION_HISTORY
    fi
  elif [ "$HISTCMD" != "$_window_session_histcmd" ]; then
    line=$(fc -ln -0)
    printf '%s\n' "${line#"${line%%[![:space:]]*}"}" \
      >> "$WINDOW_SESSION_JOURNAL"
  fi
  _window_session_histcmd=$HISTCMD
}
