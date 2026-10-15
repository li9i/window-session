# window-session

`window-session` records which windows are open and puts them back after a crash or a reboot.

A systemd user timer saves the open windows to `~/.local/state/window-session.json` every minute. After a crash, `window-session restore` starts what is missing. A desktop can also be stored under a name and put back days later. A terminal window that was running [Claude Code](docs/details.md#claude-code-sessions) comes back running it on the same conversation, in a docker container too.

The details, from what comes back to how to test a change, are in [docs/details.md](docs/details.md).

## Install

```bash
git clone https://github.com/li9i/window-session.git ~/window-session
~/window-session/install.sh
```

To update, `git pull` and run the installer again. `~/window-session/uninstall.sh` takes it out.

It needs X11 (not Wayland), Python 3, `xprop`, `xdotool`, `pgrep` and a systemd user session. It was written for Ubuntu MATE, and on other desktops a crash can cost the record: see [what it needs](docs/details.md#what-it-needs).

## Commands

```bash
window-session list                    # the two records and the stored states
window-session show                    # what was open, in readable form
window-session restore                 # a dry run: what it would start
window-session restore --go            # start it
window-session restore --go --place    # start it, then put the windows back

window-session store work              # store the desktop under a name
window-session restore work --go --place
window-session delete work
```

## Terminal commands

To give a restored terminal window back the commands typed in it, add to `~/.bashrc`:

```bash
. ~/.local/share/window-session/history.bash
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }_window_session_journal"
```

If `~/.bashrc` already has a `DEBUG` trap, read [terminal commands](docs/details.md#terminal-commands) first.

## Licence

[MIT](LICENSE).
