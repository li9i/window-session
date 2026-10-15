# window-session in detail

The [README](../README.md) covers installing and the everyday commands. This page holds the rest.

Everything lives in one file, `~/.local/state/window-session.json`, checked every minute by a systemd user timer, and rewritten only when the window list has changed. It holds one entry per window: the program, the title, the workspace, the size and position, the directory a terminal was in, the Claude Code session it was running and the folder a file manager was showing. After a crash, `window-session restore` reads it and starts what is missing. States stored by hand under a name go in the same file and stay there until deleted.

* [Install](#install)
* [What it needs](#what-it-needs)
* [Commands](#commands)
* [The two records](#the-two-records)
* [Stored states](#stored-states)
* [Terminal commands](#terminal-commands)
* [Claude Code sessions](#claude-code-sessions)
* [What comes back and what does not](#what-comes-back-and-what-does-not)
* [How it works](#how-it-works)
* [Checks after a change](#checks-after-a-change)

## Install

- The installer fetches `x11-utils`, `xdotool` and `procps` on Ubuntu, links the command, the systemd timer, its tab completion and the bash hook for [terminal commands](#terminal-commands) into the home directory pointing back at the checkout, and starts the timer. Nothing is copied anywhere.
- To update, `git pull` and run the installer again. The second run is what makes a running timer take a changed schedule.
- `~/window-session/uninstall.sh` stops the timer and takes the links back out. It leaves the checkout, the packages and the record where they are.
- `~/.local/bin` has to be on your `PATH` for the command, though not for the timer. Ubuntu's stock `~/.profile` puts it there at login once the directory exists, so a fresh machine wants one log out and back in.

## What it needs

An X11 desktop with a window manager that publishes the standard window list on the root window, which nearly all of them do. Wayland is out. Python 3 with nothing beyond its standard library, `xprop`, `xdotool`, `pgrep`, and a systemd user session to run the timer. A [Claude Code session](#claude-code-sessions) in a container also needs `docker` to run without `sudo`.

It was written for and is used on Ubuntu MATE. One part depends on that: the record of the previous session is told apart from the current one by the start time of the MATE session process, `mate-session`, or of its window manager, `marco`. On another desktop neither is found, so nothing is kept aside when a session ends, and after a crash the near empty new desktop is written over the only record within a minute.

## Commands

`save` renews the record by hand. The timer calls it every minute, so this is only needed to catch a moment exactly:

```bash
window-session save            # writes nothing if the window list did not change
window-session save --force    # writes anyway
```

`show` and `restore` take the name of a [stored state](#stored-states), or `--current` or `--previous` to name a record rather than let the tool choose, and `--file` to read another state file:

```bash
window-session show --current
window-session restore --previous --go --place
window-session show --file /tmp/window-session-test.json
```

The timer is a normal systemd user unit:

```bash
systemctl --user status window-session-save.timer
systemctl --user list-timers window-session-save.timer
systemctl --user disable --now window-session-save.timer   # stop recording
systemctl --user enable --now window-session-save.timer    # record again
```

## The two records

The timer keeps two records, and `list` shows both:

```
current           2026-08-11 12:50:33  15 windows
previous session  2026-08-11 09:00:00  15 windows  <- used by restore
```

`current` is the desktop as it stands. `previous session` is what `current` held when the desktop session it described came to an end.

The second one is there because one record on its own cannot survive a crash. The desktop you log into afterwards is nearly empty, and the timer would write that over the only thing worth restoring within a minute. So each record carries the start time of the session it was taken in, and the first save under a new session moves the old record aside instead of overwriting it. The timer accumulates nothing: there is one file, and one record per side.

That is also how `show` and `restore` choose when told neither `--current` nor `--previous`. They take the previous session while the current record belongs to the session running now, which is the case after a crash, and the current record otherwise. `list` marks the one they would take.

Two more rules protect the record. Nothing is written when the X display cannot be reached, and nothing is written when no windows are open, so a session in the act of dying cannot spoil its own record. Writes go to a temporary file and are renamed over the old one, so a crash halfway through a write cannot leave half a record either. Only one command at a time reads, changes and writes the file, under a lock on `window-session.json.lock` beside it, so a store made while the timer saves is not written over.

The resolved file manager folders are cached in the same file, under `folder_cache`.

## Stored states

The two records follow the desktop on their own. A stored state is taken by hand and stays until it is deleted, so a desktop stored today can be put back days and any number of reboots later.

```bash
window-session store work --description "the uploader fix, three terminals"
window-session store                       # named like calm_curie
window-session show work
window-session restore work --go --place
window-session delete work
```

`list` shows the stored states under the two records, each with its description:

```
current           2026-10-10 21:46:59   4 windows
previous session  2026-10-10 11:51:35   5 windows  <- used by restore

stored
work            2026-10-10 22:24:00   3 windows  the uploader fix, three terminals
wise_ramanujan  2026-10-10 22:24:00   3 windows
```

A name already taken is refused and nothing is stored. Delete the old state first, or store under another name. A restore closes nothing. It starts each terminal and file manager window of the state that is not open on the same folder. Any other program is started for as many windows as the state holds beyond those open already, so a program that is open is not started a second time.

What comes back is what comes back after a crash, which the next section lists, and the browser tabs as well. Each tab that Chrome or Firefox had open and that is not open now opens again, in a new window with the other tabs of the window it was in. A tab open already, in any window, is left alone. When the browser is not running, the restore starts it to open those windows, and whatever the browser reopens by itself on start comes on top.

Stored states live in the same file, under `stored`.

## Terminal commands

A restored terminal window can have the commands that were typed in it back on its up arrow, on top of the shared history every new window starts with. That takes a hook in bash, which the installer links to `~/.local/share/window-session/history.bash` and which is turned on with two lines in `~/.bashrc`:

```bash
. ~/.local/share/window-session/history.bash
PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }_window_session_journal"
```

If `~/.bashrc` already times commands with a `DEBUG` trap that compares each command with `PROMPT_COMMAND`, call `_window_session_journal` from inside the function `PROMPT_COMMAND` runs instead, or every prompt starts that timer again.

The hook writes each command into a journal of its own shell under `~/.local/state/window-session/journals/`, named after the process id and the start time of the shell. Every record takes the journal of each terminal window along, and a new command is enough to renew the crash record at the next tick of the timer. On restore, the commands go into a file that the new shell reads at its first prompt and then deletes. Bash reads its own history file only after `~/.bashrc`, which is why the commands wait for the first prompt: read any earlier, the shared history would land on top of them.

What stays as it was: a new window starts with the shared history, which each window adds to only when it closes. A command that starts with a space, or that `HISTCONTROL` keeps out of the history, stays out of the journal too. The text that was on the screen does not come back: MATE's terminal keeps it in encrypted files whose key never leaves its memory. The timer deletes the journal of a shell once the shell is gone. By then its commands are in the records, which are what a restore reads.

## Claude Code sessions

A terminal window that was running Claude Code comes back running it again, on the same conversation. That holds for Claude started in the window and for Claude started in a container that the window went into with `docker exec`. The dry run says what each window comes back with:

```
Mate-terminal: 2 window(s) recorded, 0 already open, start 2
  /usr/bin/mate-terminal
  - Fix the retry loop in the upload client
    in /home/alex/projects/uploader
    was running docker exec -it -u developer uploader-app-1 bash
    comes back with claude --resume 0fcab278-6013-4072-b1a0-f354949ee454
  - Review the upload client
    in /home/alex/projects/uploader
    was running claude
    comes back with claude attach ceb4cbb3
```

The new window then runs, for Claude in a container:

```
bash -c "docker exec -it -u developer uploader-app-1 bash -c 'cd /home/alex/projects/uploader && claude --resume 0fcab278-6013-4072-b1a0-f354949ee454; exec bash'; exec bash"
```

Claude starts in the folder it ran in. When it quits, the shell it ran under takes over, in the container first and then in the window, as before. For Claude started in the window, the `docker exec` part is left out.

* A session sent to the background comes back with `claude attach` and its job. Claude opens a background job that still runs, and one that was stopped, the same way.
* The options Claude was started with come back too, less those that pick a session: `--resume`, `-r`, `--continue`, `-c`, `--session-id` and `--fork-session`. A prompt given on the command line would be sent again, so start Claude without one in a window you want back.
* The window has to be a `mate-terminal`, `gnome-terminal`, `terminator` or `xfce4-terminal`, the terminals that take a command to run. In any other terminal the window comes back as a shell.
* After a desktop crash, a container outlives the window, and so does the Claude that ran in it. Claude does not refuse a second copy of a session, and two copies would write to one conversation. So before it opens the window, `restore --go` looks for that Claude. Idle, it is stopped, and the new window takes the session over. At work, it is left alone, and the window opens in the container without Claude, with a line that says so. After a reboot the container starts again empty, so there is nothing to find.

How the session is found. Claude keeps a note on each running session in `~/.claude/sessions/`, or under `CLAUDE_CONFIG_DIR` when that is set, named after the process id that Claude sees. In a container that is its id inside the container. The note names the session, its folder and, for a session sent to the background, the job. The timer looks for Claude among the processes under the shell of each terminal window and reads the note where Claude runs, through `docker exec` for a container. The processes of a container run under the shim of its runtime, which names the container. A `docker exec` in a window is paired with the first shell opened in a container after it, so two opened at the same moment can swap.

## What comes back and what does not

Back:

* every program that had a window, and as many windows as it had
* the workspace, size and position of each window, with `--place`
* the directory the shell in each terminal window was in
* the folder each file manager window was showing
* for a stored state, the tabs Chrome and Firefox had open
* the commands typed in each terminal window, with the [bash hook](#terminal-commands)
* the Claude Code session each terminal window was running, in a container too: see [Claude Code sessions](#claude-code-sessions)

Not back, because it lives inside the program rather than in the window:

* whatever else was running in a terminal, and the text on its screen. The recorded command is printed as a reminder, not rerun. A `docker exec` into a container has to be started again by hand, unless Claude Code was running in it.
* unsaved documents.

After a crash, browsers and editors are left to their own restore. Chrome and Firefox are started once each and bring their own windows and tabs back themselves.

A dry run prints all of it:

```
Mate-terminal: 4 window(s) recorded, 0 already open, start 4
  /usr/bin/mate-terminal
  - Fix the retry loop in the upload client
    in /home/alex/projects/uploader
    was running docker exec -it -u developer uploader-app-1 bash
```

## How it works

The window list comes from `_NET_CLIENT_LIST` on the root window, and each window's class, title, workspace and process from its own properties. Panels, the desktop and other furniture are dropped by window type. Geometry comes from `xdotool`. The command line, working directory and executable of the owning process come from `/proc`.

Four things are less obvious.

**One process, many windows.** A terminal, a file manager and a browser each serve all their windows from one process, so counting processes would bring back one window where there were five. Restore matches windows instead. A terminal counts as open when a terminal is open in the same directory, and a file manager when one shows the same folder. Any other window is matched by count within its window class, so only the difference is started.

**Stale program paths.** A snap records a path carrying its revision, `/snap/firefox/8736/...`, and an AppImage records the temporary mount it was running from, `/tmp/.mount_.../obsidian`. Neither exists after a restart. The recorded path is used when it still exists, then the program name on `PATH`, then an AppImage of that name in `~/Applications`, `~/Downloads`, `~/Downloads/programs`, `~/Desktop`, `~/bin`, `~/.local/bin` or `~/opt`.

**The directory a terminal was in.** Taken from the shell processes running under the terminal process. Those shells are paired with the terminal's windows in creation order, which is right for one shell per window. With tabs in play the pairing can slip a window. The command reported for each is its deepest descendant, which is what was on screen.

**The folder a file manager was showing.** Caja publishes nothing about it: no window property, no open descriptor, and the title carries the folder name without the path. What it does hold is an inotify watch on the folder it displays, so `/proc/PID/fdinfo` gives the inode, and a scan of the home directory turns that inode into a path. Caja watches every ancestor of an open folder as well, so the window title has to match the folder name too. This is what tells eight folders named `prompts` apart. A cached path is only trusted while its inode is still watched, so navigating a window to another folder of the same name is noticed.

**The tabs a browser has open.** Read from the browser's own session file when a state is stored, and again when it is restored, to see which tabs are open now. Chrome keeps a log of commands under `~/.config/google-chrome/*/Sessions/`, appending one each time a tab opens, moves, navigates or closes, so the open tabs are what is left after replaying the whole log. Firefox rewrites `sessionstore-backups/recovery.jsonlz4` in its profile every 15 seconds, JSON compressed with LZ4, which the script decompresses itself. A tab opened in Firefox in the last 15 seconds before a store can be missing from it. The two also differ in how they take a window of tabs. Chrome opens every URL after `--new-window` as the tabs of one new window. Firefox opens only the first, so each later tab goes as `--new-tab` in a command of its own, which lands in the window that was opened last.

Placement, with `--place`, waits for the new windows to appear and matches them to the record by window class, in order. A move is measured against the window frame, which the window manager then adds back, and frame extents are reported in other units under display scaling, so each window is moved once, measured, and corrected by what it was out by.

Two routes that look right and are not. MATE's session manager has no save method on DBus, so the desktop cannot be asked to write its own session state. `mate-terminal --save-config` refuses to run against an instance holding no bus name, which is how the running terminal here is started. MATE's own `auto-save-session` only writes on a clean logout, which is exactly what a crash is not.

## Checks after a change

The tests fake the desktop and the processes, so they run anywhere, from the repository root:

```bash
python3 -m unittest discover -s tests
```

They cannot see a real desktop, so after touching anything, also run:

```bash
window-session save --force --verbose
window-session restore
```

The dry run should name every program that is open, with the right window count, a directory under each terminal window, a folder under each file manager window and the Claude command under each terminal window that runs Claude Code.

`WINDOW_SESSION_FILE` moves the state file, which keeps a test out of the real record. To check a restore without disturbing the desktop, copy the state file, cut the copy down to the one window you want, and point the tool at it:

```bash
export WINDOW_SESSION_FILE=/tmp/window-session-test.json
cp ~/.local/state/window-session.json $WINDOW_SESSION_FILE
# edit the copy down to one window, close that window, then
window-session restore --current --go --place
```

To check stored states against the copy, store one, find it in the list with its description, and delete it again:

```bash
window-session store check --description "a test"
window-session list
window-session delete check
```

To check the hand-over between sessions, set `session_start` in the copy's `current` record to something else and save. The old record must appear as `previous session`, and a second save must leave it alone rather than promote again:

```bash
window-session save --force --verbose
window-session list
```
