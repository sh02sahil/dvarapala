"""The user's note for the agent ("feedback"), the root runner's environment
on Debian/Ubuntu, and the sudo stand-in. No window, no root: pure functions
read out of lib/dialog.py without GTK (by parsing it), and scripts run
as subprocesses."""
import ast
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def dialog_function(name, ns=None):
    """One top-level function (and MAX_NOTE) from lib/dialog.py, without
    importing GTK."""
    tree = ast.parse((ROOT / "lib" / "dialog.py").read_text())
    nodes = [n for n in tree.body
             if (isinstance(n, ast.FunctionDef) and n.name == name)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "MAX_NOTE" for t in n.targets))]
    ns = {} if ns is None else ns
    exec(compile(ast.Module(nodes, []), "dialog.py", "exec"), ns)
    return ns[name], ns


class Feedback(unittest.TestCase):
    def setUp(self):
        self.fields, self.ns = dialog_function("feedback_fields")

    def test_no_note_changes_nothing(self):
        for note in ("", "   ", None, "\n\t"):
            self.assertEqual(self.fields(note, "The user denied the request."),
                             ("The user denied the request.", {}))

    def test_note_goes_in_feedback_and_message(self):
        msg, extra = self.fields("  use apt, not snap  ", "The user denied the request.")
        self.assertEqual(extra, {"feedback": "use apt, not snap"})
        self.assertEqual(msg, "The user denied the request. The user's note: use apt, not snap")

    def test_note_is_one_line_and_capped(self):
        msg, extra = self.fields("line one\nline two\r\n\tthree", "Denied.")
        self.assertEqual(extra["feedback"], "line one line two three")
        _, extra = self.fields("x" * 5000, "Denied.")
        self.assertEqual(len(extra["feedback"]), self.ns["MAX_NOTE"])

    def test_schema_and_mcp_tool_mention_feedback(self):
        out = subprocess.run([sys.executable, str(ROOT / "bin" / "dvarapala"), "--schema"],
                             capture_output=True, text=True, timeout=20)
        schema = json.loads(out.stdout)
        self.assertIn("feedback", schema["result"]["properties"])
        self.assertIn("feedback", (ROOT / "bin" / "dvarapala").read_text().split("MCP_TOOL = {", 1)[1])


class DialogUnit(unittest.TestCase):
    def test_window_unit_logs_as_dvarapala(self):
        # bin/dvarapala's helper, read out of it without running anything.
        tree = ast.parse((ROOT / "bin" / "dvarapala").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "dialog_unit_cmd")
        ns = {"DIALOG": "/usr/local/lib/dvarapala/dialog.py"}
        exec(compile(ast.Module([fn], []), "dvarapala", "exec"), ns)
        cmd = ns["dialog_unit_cmd"]("dvarapala-123", {"HOME": "/home/u"}, "/run/user/1/dvarapala/123")
        self.assertIn("--property=SyslogIdentifier=dvarapala", cmd)
        self.assertIn("--user", cmd)
        # env -i, then only the given environment: nothing from the caller.
        i = cmd.index("/usr/bin/env")
        self.assertEqual(cmd[i + 1:i + 3], ["-i", "HOME=/home/u"])
        self.assertEqual(cmd[-3:], ["-I", "/usr/local/lib/dvarapala/dialog.py", "/run/user/1/dvarapala/123"])

    def test_bin_no_longer_posts_its_own_notification(self):
        # The window posts it (and closes it when answered); a second one from
        # bin/dvarapala would be the one that never goes away.
        self.assertNotIn("notify-send", (ROOT / "bin" / "dvarapala").read_text())


class RunnerEnvironment(unittest.TestCase):
    def test_sbin_and_noninteractive(self):
        spec = importlib.util.spec_from_file_location("runner", ROOT / "lib" / "runner.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        path = runner.ENV["PATH"].split(":")
        # Debian and Ubuntu keep sysctl, usermod, swapon... in /usr/sbin.
        for d in ("/usr/sbin", "/usr/bin", "/usr/local/sbin", "/usr/local/bin"):
            self.assertIn(d, path)
        self.assertLess(path.index("/usr/local/bin"), path.index("/usr/bin"))
        self.assertEqual(runner.ENV["DEBIAN_FRONTEND"], "noninteractive")


class SudoHint(unittest.TestCase):
    HINT = ROOT / "lib" / "sudo-hint"

    def test_hint_in_a_sandbox_plain_sudo_outside(self):
        with open("/proc/self/status") as f:
            sandboxed = any(line.split() == ["NoNewPrivs:", "1"] for line in f)
        r = subprocess.run(["sh", str(self.HINT), "-n", "true"], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=20)
        if sandboxed:
            self.assertEqual(r.returncode, 1)
            self.assertIn("request_commands", r.stderr)
            self.assertIn("dvarapala --requester", r.stderr)
        else:
            # Outside a sandbox it is /usr/bin/sudo itself: never the hint.
            self.assertNotIn("request_commands", r.stderr)

    def test_installer_marker_matches(self):
        # install.sh only replaces or removes a /usr/local/bin/sudo carrying this marker.
        marker = "dvarapala's sudo stand-in"
        self.assertIn(marker, self.HINT.read_text())
        self.assertGreaterEqual((ROOT / "install.sh").read_text().count(marker), 2)


if __name__ == "__main__":
    unittest.main()
