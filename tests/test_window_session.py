"""Behaviour of window-session, with the desktop and the processes faked.

Run from the repository root:

    python3 -m unittest discover -s tests
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
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

    def test_a_stored_program_starts_even_when_a_copy_is_open(self):
        app = self.window("App", "app")
        self.restore_stored([app], [app])
        self.assertEqual(len(self.spawned), 1)

    def test_a_crash_record_does_not_start_an_open_program_twice(self):
        app = self.window("App", "app")
        self.restore_crash_record([app], [app])
        self.assertEqual(self.spawned, [])

    def test_a_crash_record_matches_terminals_by_folder_too(self):
        self.restore_crash_record([self.terminal("/b")],
                                  [self.terminal("/a")])
        self.assertEqual(len(self.spawned), 1)


if __name__ == "__main__":
    unittest.main()
