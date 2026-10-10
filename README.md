# window-session

`window-session` records which windows are open and puts them back after a crash or a reboot.

Everything lives in one file, `~/.local/state/window-session.json`, checked every minute by a systemd user timer, and rewritten only when the window list has changed. It holds one entry per window: the program, the title, the workspace, the size and position, the directory a terminal was in and the folder a file manager was showing. After a crash, `window-session restore` reads it and starts what is missing. States stored by hand under a name go in the same file and stay there until deleted.

* [Install](#install)
* [What it needs](#what-it-needs)
* [Commands](#commands)
* [The two records](#the-two-records)
* [Stored states](#stored-states)
* [What comes back and what does not](#what-comes-back-and-what-does-not)
* [How it works](#how-it-works)
* [Checks after a change](#checks-after-a-change)
* [Licence](#licence)

## Install

```bash
git clone https://github.com/li9i/window-session.git ~/window-session
~/window-session/install.sh
```

- The installer fetches `x11-utils`, `xdotool` and `procps` on Ubuntu, links the command, the systemd timer and its tab completion into the home directory pointing back at the checkout, and starts the timer. Nothing is copied anywhere.
- To update, `git pull` and run the installer again. The second run is what makes a running timer take a changed schedule.
- `~/window-session/uninstall.sh` stops the timer and takes the links back out. It leaves the checkout, the packages and the record where they are.
- `~/.local/bin` has to be on your `PATH` for the command, though not for the timer. Ubuntu's stock `~/.profile` puts it there at login once the directory exists, so a fresh machine wants one log out and back in.

## What it needs

An X11 desktop with a window manager that publishes the standard window list on the root window, which nearly all of them do. Wayland is out. Python 3 with nothing beyond its standard library, `xprop`, `xdotool`, `pgrep`, and a systemd user session to run the timer.

It was written for and is used on Ubuntu MATE. One part depends on that: the record of the previous session is told apart from the current one by the start time of the MATE session process, `mate-session`, or of its window manager, `marco`. On another desktop neither is found, so nothing is kept aside when a session ends, and after a crash the near empty new desktop is written over the only record within a minute.

## Commands

```bash
window-session list                    # the two records and the stored states
window-session show                    # what was open, in readable form
window-session restore                 # a dry run: what it would start
window-session restore --go            # start it
window-session restore --go --place    # start it, then put the windows back
```

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

Two more rules protect the record. Nothing is written when the X display cannot be reached, and nothing is written when no windows are open, so a session in the act of dying cannot spoil its own record. Writes go to a temporary file and are renamed over the old one, so a crash halfway through a write cannot leave half a record either.

The resolved file manager folders are cached in the same file, under `folder_cache`.

## Stored states

The two records follow the desktop on their own. A stored state is taken by hand and stays until it is deleted, so a desktop stored today can be put back days and any number of reboots later.

```bash
window-session store work --description "the uploader fix, three terminals"
window-session store                       # named after the date and time
window-session show work
window-session restore work --go --place
window-session delete work
```

`list` shows the stored states under the two records, each with its description:

```
current           2026-10-10 21:46:59   4 windows
previous session  2026-10-10 11:51:35   5 windows  <- used by restore

stored
work                 2026-10-10 21:55:19   4 windows  the uploader fix, three terminals
2026-10-10_21:55:19  2026-10-10 21:55:19   4 windows
```

A name already taken is refused and nothing is stored. Delete the old state first, or store under another name. A restore starts what the stored state has and the desktop lacks, and closes nothing, the same as a restore after a crash.

What comes back is what comes back after a crash, which the next section lists. A browser opens its own most recent tabs, not the tabs it had when the state was stored.

Stored states live in the same file, under `stored`.

## What comes back and what does not

Back:

* every program that had a window, and as many windows as it had
* the workspace, size and position of each window, with `--place`
* the directory the shell in each terminal window was in
* the folder each file manager window was showing

Not back, because it lives inside the program rather than in the window:

* whatever was running in a terminal. The recorded command is printed as a reminder, not rerun. A `docker exec` into a container, or a Claude Code session, has to be started again by hand.
* unsaved documents.

Browsers and editors are left to their own restore. Chrome and Firefox are started once each and bring their own windows and tabs back themselves.

A dry run prints all of it:

```
Mate-terminal: 4 window(s) recorded, 0 open now, start 4
  /usr/bin/mate-terminal
  - Fix the retry loop in the upload client
    in /home/alex/projects/uploader
    was running docker exec -it -u developer uploader-app-1 bash
```

## How it works

The window list comes from `_NET_CLIENT_LIST` on the root window, and each window's class, title, workspace and process from its own properties. Panels, the desktop and other furniture are dropped by window type. Geometry comes from `xdotool`. The command line, working directory and executable of the owning process come from `/proc`.

Four things are less obvious.

**One process, many windows.** A terminal, a file manager and a browser each serve all their windows from one process, so counting processes would bring back one window where there were five. Restore counts windows per window class instead, compares that with what is open now, and starts the difference.

**Stale program paths.** A snap records a path carrying its revision, `/snap/firefox/8736/...`, and an AppImage records the temporary mount it was running from, `/tmp/.mount_.../obsidian`. Neither exists after a restart. The recorded path is used when it still exists, then the program name on `PATH`, then an AppImage of that name in `~/Applications`, `~/Downloads`, `~/Downloads/programs`, `~/Desktop`, `~/bin`, `~/.local/bin` or `~/opt`.

**The directory a terminal was in.** Taken from the shell processes running under the terminal process. Those shells are paired with the terminal's windows in creation order, which is right for one shell per window. With tabs in play the pairing can slip a window. The command reported for each is its deepest descendant, which is what was on screen.

**The folder a file manager was showing.** Caja publishes nothing about it: no window property, no open descriptor, and the title carries the folder name without the path. What it does hold is an inotify watch on the folder it displays, so `/proc/PID/fdinfo` gives the inode, and a scan of the home directory turns that inode into a path. Caja watches every ancestor of an open folder as well, so the window title has to match the folder name too. This is what tells eight folders named `prompts` apart. A cached path is only trusted while its inode is still watched, so navigating a window to another folder of the same name is noticed.

Placement, with `--place`, waits for the new windows to appear and matches them to the record by window class, in order. A move is measured against the window frame, which the window manager then adds back, and frame extents are reported in other units under display scaling, so each window is moved once, measured, and corrected by what it was out by.

Two routes that look right and are not. MATE's session manager has no save method on DBus, so the desktop cannot be asked to write its own session state. `mate-terminal --save-config` refuses to run against an instance holding no bus name, which is how the running terminal here is started. MATE's own `auto-save-session` only writes on a clean logout, which is exactly what a crash is not.

## Checks after a change

There is no test suite. After touching anything, run:

```bash
window-session save --force --verbose
window-session restore
```

The dry run should name every program that is open, with the right window count, a directory under each terminal window and a folder under each file manager window.

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

## Licence

[MIT](LICENSE).
