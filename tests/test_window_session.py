"""Behaviour of window-session, with the desktop and the processes faked.

Run from the repository root:

    python3 -m unittest discover -s tests
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import multiprocessing
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "bin", "window-session")


def load_script():
    loader = importlib.machinery.SourceFileLoader("window_session", SCRIPT)
    spec = importlib.util.spec_from_loader("window_session", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class WindowSessionTest(unittest.TestCase):

    def setUp(self):
        self.ws = load_script()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws.STATE_FILE = os.path.join(self.tmp.name, "state.json")
        self.desktop = []
        self.spawned = []
        self.ws.read_windows = lambda: [dict(w) for w in self.desktop]
        self.ws.session_start_time = lambda: 1.0
        self.ws.annotate_folders = lambda windows, state: None
        self.ws.annotate_shell_dirs = lambda windows: None
        self.ws.spawn = self.fake_spawn

    def fake_spawn(self, command, cwd):
        self.spawned.append(command)
        return True

    def program(self, name):
        path = os.path.join(self.tmp.name, name)
        if not os.path.exists(path):
            with open(path, "w") as handle:
                handle.write("#!/bin/sh\n")
            os.chmod(path, 0o755)
        return path

    def window(self, wm_class, name, **extra):
        window = {
            "wm_class": wm_class,
            "cmdline": [self.program(name)],
            "title": wm_class,
            "desktop": 0,
            "geometry": {"x": 0, "y": 0, "width": 100, "height": 100},
        }
        window.update(extra)
        return window

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                mock.patch.object(sys, "argv", ["window-session"] + list(argv)):
            code = self.ws.main()
        return code, out.getvalue()


class StoredStatesTest(WindowSessionTest):

    def setUp(self):
        super().setUp()
        self.desktop = [self.window("App", "app"),
                        self.window("Other", "other")]

    def test_store_then_list_shows_the_name_and_the_description(self):
        self.run_cli("store", "work", "--description", "three terminals")
        _, out = self.run_cli("list")
        line = [l for l in out.splitlines() if l.startswith("work")][0]
        self.assertIn("2 windows", line)
        self.assertTrue(line.endswith("three terminals"))

    def test_a_taken_name_is_refused_and_the_first_state_kept(self):
        self.run_cli("store", "work", "--description", "first")
        self.desktop = self.desktop[:1]
        code, out = self.run_cli("store", "work", "--description", "second")
        self.assertEqual(code, 1)
        self.assertIn("taken", out)
        _, out = self.run_cli("list")
        self.assertIn("2 windows  first", out)
        self.assertNotIn("second", out)

    def test_store_without_a_name_still_lists_one_state(self):
        code, out = self.run_cli("store")
        self.assertEqual(code, 0)
        _, listing = self.run_cli("list")
        stored = listing.split("stored\n", 1)[1].splitlines()
        self.assertEqual(len(stored), 1)
        self.assertIn(stored[0].split()[0], out)

    def test_a_state_stored_without_a_name_gets_adjective_and_surname(self):
        _, out = self.run_cli("store")
        name = out.split()[-1]
        adjective, surname = name.split("_")
        self.assertIn(adjective, self.ws.NAME_ADJECTIVES)
        self.assertIn(surname, self.ws.NAME_SURNAMES)

    def test_a_made_up_name_already_taken_is_not_used_again(self):
        self.ws.NAME_ADJECTIVES = ["calm"]
        self.ws.NAME_SURNAMES = ["curie", "turing"]
        self.run_cli("store")
        code, _ = self.run_cli("store")
        self.assertEqual(code, 0)
        _, out = self.run_cli("list")
        names = sorted(l.split()[0]
                       for l in out.split("stored\n", 1)[1].splitlines())
        self.assertEqual(names, ["calm_curie", "calm_turing"])

    def test_list_names_prints_only_the_stored_names(self):
        self.run_cli("store", "work")
        self.run_cli("store", "play")
        _, out = self.run_cli("list", "--names")
        self.assertEqual(out.splitlines(), ["work", "play"])

    def test_show_prints_the_description_under_the_name(self):
        self.run_cli("store", "work", "--description", "three terminals")
        _, out = self.run_cli("show", "work")
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("work record"))
        self.assertEqual(lines[1], "three terminals")

    def test_delete_removes_only_that_state(self):
        self.run_cli("store", "work")
        self.run_cli("store", "play")
        self.run_cli("delete", "work")
        _, out = self.run_cli("list")
        names = [l.split()[0] for l in out.split("stored\n", 1)[1].splitlines()]
        self.assertEqual(names, ["play"])

    def test_a_mistyped_name_is_named_back_and_nothing_happens(self):
        self.run_cli("store", "work")
        for command in ("restore", "show", "delete"):
            code, out = self.run_cli(command, "wrok")
            self.assertEqual(code, 1)
            self.assertIn("wrok", out)
        _, out = self.run_cli("list")
        self.assertIn("work", out)

    def test_stores_made_while_saves_run_are_all_kept(self):
        def saves():
            for _ in range(300):
                self.run_cli("save", "--force")

        workers = [multiprocessing.Process(target=saves) for _ in range(2)]
        for worker in workers:
            worker.start()
        for i in range(60):
            self.run_cli("store", "s%d" % i)
        for worker in workers:
            worker.join()
        _, out = self.run_cli("list", "--names")
        self.assertEqual(len(out.split()), 60)
        self.assertEqual([worker.exitcode for worker in workers], [0, 0])

    def test_the_timer_save_keeps_the_stored_states(self):
        self.run_cli("store", "work")
        self.desktop = self.desktop[:1]
        self.run_cli("save", "--force")
        _, out = self.run_cli("list")
        self.assertIn("work", out)

    def test_restore_of_a_stored_state_names_it(self):
        self.run_cli("store", "work")
        _, out = self.run_cli("restore", "work")
        self.assertTrue(out.startswith("work record, 2 windows"))


class RestoreTest(WindowSessionTest):

    def terminal(self, folder):
        return self.window("Mate-terminal", "mate-terminal", shell_cwd=folder)

    def file_manager(self, folder):
        return self.window("Caja", "caja", folder=folder)

    def restore_stored(self, stored, open_now):
        self.desktop = stored
        self.run_cli("store", "work")
        self.desktop = open_now
        self.run_cli("restore", "work", "--go")

    def restore_crash_record(self, recorded, open_now):
        self.desktop = recorded
        self.run_cli("save")
        self.desktop = open_now
        self.run_cli("restore", "--current", "--go")

    def test_a_terminal_open_elsewhere_does_not_hold_back_a_stored_one(self):
        self.restore_stored([self.terminal("/b")], [self.terminal("/a")])
        self.assertEqual(len(self.spawned), 1)
        self.assertIn("--working-directory=/b", self.spawned[0])

    def test_a_terminal_open_in_the_same_folder_is_not_started_again(self):
        self.restore_stored([self.terminal("/b")], [self.terminal("/b")])
        self.assertEqual(self.spawned, [])

    def test_a_file_manager_on_another_folder_does_not_hold_back_one(self):
        self.restore_stored([self.file_manager("/b")],
                            [self.file_manager("/a")])
        self.assertEqual(len(self.spawned), 1)
        self.assertIn("/b", self.spawned[0])

    def test_a_file_manager_on_the_same_folder_is_not_started_again(self):
        self.restore_stored([self.file_manager("/b")],
                            [self.file_manager("/b")])
        self.assertEqual(self.spawned, [])

    def test_a_stored_program_open_already_is_not_started_twice(self):
        app = self.window("App", "app")
        self.restore_stored([app], [app])
        self.assertEqual(self.spawned, [])

    def test_a_crash_record_does_not_start_an_open_program_twice(self):
        app = self.window("App", "app")
        self.restore_crash_record([app], [app])
        self.assertEqual(self.spawned, [])

    def test_a_crash_record_matches_terminals_by_folder_too(self):
        self.restore_crash_record([self.terminal("/b")],
                                  [self.terminal("/a")])
        self.assertEqual(len(self.spawned), 1)


def snss(*commands):
    """A Chrome session file holding the commands given."""
    data = b"SNSS" + struct.pack("<i", 3)
    for kind, payload in commands:
        data += struct.pack("<H", len(payload) + 1) + bytes([kind]) + payload
    return data


def snss_navigation(tab, index, url):
    encoded = url.encode()
    body = struct.pack("<iii", tab, index, len(encoded))
    body += encoded + b"\0" * (-len(encoded) % 4)
    return 6, struct.pack("<I", len(body)) + body


def mozlz4(text):
    """A Firefox session file, its block made of literals alone."""
    raw = text.encode()
    extra = len(raw) - 15
    block = bytes([0xF0]) + b"\xff" * (extra // 255) + bytes([extra % 255])
    return (b"mozLz40\0" + struct.pack("<I", len(raw)) + block + raw)


class BrowserTabsTest(WindowSessionTest):

    def write(self, name, data):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def test_chrome_tabs_come_out_per_window_in_tab_order(self):
        path = self.write("Session_1", snss(
            (0, struct.pack("<ii", 7, 1)),
            (0, struct.pack("<ii", 7, 2)),
            (0, struct.pack("<ii", 8, 3)),
            (2, struct.pack("<ii", 1, 1)),
            (2, struct.pack("<ii", 2, 0)),
            (2, struct.pack("<ii", 3, 0)),
            snss_navigation(1, 0, "https://a.example/"),
            snss_navigation(2, 0, "https://b.example/old"),
            snss_navigation(2, 1, "https://b.example/new"),
            (7, struct.pack("<ii", 2, 1)),
            snss_navigation(3, 0, "https://c.example/"),
        ))
        self.assertEqual(self.ws.read_snss(path), [
            ["https://b.example/new", "https://a.example/"],
            ["https://c.example/"],
        ])

    def test_chrome_drops_closed_tabs_and_closed_windows(self):
        path = self.write("Session_1", snss(
            (0, struct.pack("<ii", 7, 1)),
            (0, struct.pack("<ii", 7, 2)),
            (0, struct.pack("<ii", 8, 3)),
            snss_navigation(1, 0, "https://a.example/"),
            snss_navigation(2, 0, "https://b.example/"),
            snss_navigation(3, 0, "https://c.example/"),
            (7, struct.pack("<ii", 1, 0)),
            (7, struct.pack("<ii", 2, 0)),
            (7, struct.pack("<ii", 3, 0)),
            (16, struct.pack("<iq", 2, 0)),
            (17, struct.pack("<iq", 8, 0)),
        ))
        self.assertEqual(self.ws.read_snss(path), [["https://a.example/"]])

    def test_firefox_tabs_come_out_per_window_at_their_current_entry(self):
        session = json.dumps({"windows": [
            {"tabs": [
                {"entries": [{"url": "https://a.example/old"},
                             {"url": "https://a.example/new"}],
                 "index": 2},
                {"entries": [{"url": "https://b.example/"}], "index": 1},
            ]},
            {"tabs": [{"entries": [{"url": "https://c.example/"}],
                       "index": 1}]},
        ]})
        path = self.write("recovery.jsonlz4", mozlz4(session))
        self.assertEqual(self.ws.read_mozlz4(path), [
            ["https://a.example/new", "https://b.example/"],
            ["https://c.example/"],
        ])


class TabRestoreTest(WindowSessionTest):

    def setUp(self):
        super().setUp()
        self.session = os.path.join(self.tmp.name, "Session_1")
        self.ws.BROWSER_SESSIONS = {"chrome": ("snss", [self.session])}
        self.chrome = self.window("Google-chrome", "chrome")

    def chrome_shows(self, *windows):
        commands = []
        tab = 0
        for window, urls in enumerate(windows):
            for index, url in enumerate(urls):
                tab += 1
                commands += [(0, struct.pack("<ii", window, tab)),
                             (2, struct.pack("<ii", tab, index)),
                             snss_navigation(tab, 0, url)]
        with open(self.session, "wb") as handle:
            handle.write(snss(*commands))

    def opened(self):
        return [command[command.index("--new-window") + 1:]
                for command in self.spawned]

    def test_tabs_not_open_come_back_in_their_windows(self):
        self.desktop = [self.chrome]
        self.chrome_shows(["https://a/", "https://b/"], ["https://c/"])
        self.run_cli("store", "work")
        self.chrome_shows(["https://a/"])
        self.run_cli("restore", "work", "--go")
        self.assertEqual(self.opened(), [["https://b/"], ["https://c/"]])

    def test_every_tab_comes_back_when_the_browser_is_not_running(self):
        self.desktop = [self.chrome]
        self.chrome_shows(["https://a/", "https://b/"], ["https://c/"])
        self.run_cli("store", "work")
        self.desktop = []
        self.run_cli("restore", "work", "--go")
        self.assertEqual(self.opened(),
                         [["https://a/", "https://b/"], ["https://c/"]])

    def test_firefox_gets_its_window_first_and_each_later_tab_after(self):
        firefox = self.window("firefox", "firefox")
        session = os.path.join(self.tmp.name, "recovery.jsonlz4")
        self.ws.BROWSER_SESSIONS = {"firefox": ("mozlz4", [session])}
        with open(session, "wb") as handle:
            handle.write(mozlz4(json.dumps({"windows": [{"tabs": [
                {"entries": [{"url": "https://a/"}], "index": 1},
                {"entries": [{"url": "https://b/"}], "index": 1},
            ]}]})))
        self.desktop = [firefox]
        self.run_cli("store", "work")
        self.desktop = []
        self.run_cli("restore", "work", "--go")
        self.assertEqual([command[1:] for command in self.spawned],
                         [["--new-window", "https://a/"],
                          ["--new-tab", "https://b/"]])

    def test_nothing_opens_when_every_tab_is_open(self):
        self.desktop = [self.chrome]
        self.chrome_shows(["https://a/"])
        self.run_cli("store", "work")
        self.run_cli("restore", "work", "--go")
        self.assertEqual(self.spawned, [])


if __name__ == "__main__":
    unittest.main()
