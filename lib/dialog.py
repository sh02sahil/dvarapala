#!/usr/bin/python3 -I
"""The dvarapala approval window, in the look of GNOME's own password prompts:
stock libadwaita, following the system's light/dark style and accent colour.
It shows what an AI agent wants to run (as root, or as you: each command is
marked) and why, lets the user pick which commands to allow, takes the sudo
password once if any root command is picked, and goes away the moment the
user has answered. This process then runs the picked ones in order, with no
window, and writes the result for the agent, which is the one that waits.

Installed root-owned as /usr/local/lib/dvarapala/dialog.py by dvarapala's
install.sh, and started only by dvarapala, as a transient user service (not a
child of the agent, so the agent can't ptrace it) with a cleared environment
and XDG dirs pointing at root-owned directories, so no user GTK CSS can
restyle or hide anything: it is stock Adwaita and nothing else (ADR 13).

    dialog.py <request-dir>     reads request.json, writes result.json

Keys are GNOME's own: Tab moves, Space ticks a command, Enter authenticates,
Esc denies (asking once for an optional note for the agent; Esc again denies
without one).
"""
import ctypes
import json
import os
import pwd
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "io.github.theyashsawarkar.Dvarapala"
RUNNER = "/usr/local/lib/dvarapala/runner.py"
SUDO = "/usr/bin/sudo"
EXPIRES_AFTER = 600          # seconds the request stays open (then: denied)
MAX_ATTEMPTS = 3             # wrong passwords before the request fails
STATE_LOG = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".local/state/dvarapala/requests.jsonl")

# Layout and fonts only. Every colour comes from Adwaita itself (its light and
# dark styles and the system accent), which keeps all text readable: nothing
# here, and no user CSS, can make a command hard to see.
CSS = """
.dvarapala-row { padding: 10px 12px; }
.dvarapala-cmd { font-family: monospace; }
.dvarapala-badge {
  padding: 1px 8px;
  border-radius: 999px;
  background-color: alpha(currentColor, 0.12);
  font-size: 0.8em;
  font-weight: bold;
}
.dvarapala-row.declined .dvarapala-content { opacity: 0.5; }
"""


def _load(name):
    """A module next to this file, loaded by path from this root-owned
    directory: python -I puts no script directory on sys.path."""
    import importlib.util
    here = os.path.dirname(os.path.realpath(__file__))
    spec = importlib.util.spec_from_file_location(f"dvarapala_{name}", os.path.join(here, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


remote = _load("remote")
userrun = _load("userrun")


def harden():
    # Not dumpable: other processes of this user can't ptrace this one or
    # read /proc/<pid>/mem, where the password lives while it's typed.
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(4, 0, 0, 0, 0)  # PR_SET_DUMPABLE
    except OSError:
        pass


MAX_NOTE = 2000


def feedback_fields(note, message):
    """The user's note for the agent, added to any result: in "feedback",
    and repeated in "message" so an agent that reads only the message sees
    it too. Returns (message, extra result fields)."""
    note = " ".join((note or "").split())[:MAX_NOTE]
    if not note:
        return message, {}
    return f"{message} The user's note: {note}", {"feedback": note}


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, path)


class Request:
    def __init__(self, path):
        with open(path) as f:
            data = json.load(f)
        self.id = str(data["id"])[:64]
        self.requester = str(data.get("requester") or "An AI agent")[:80]
        self.reason = str(data.get("reason") or "")[:2000]
        home = pwd.getpwuid(os.getuid()).pw_dir
        # (cmd, why, "root"|"user", cwd): anything but "user" runs as root.
        self.commands = [(str(c["cmd"]), str(c.get("why") or ""), "user" if c.get("as") == "user" else "root",
                          str(c.get("cwd") or home) if c.get("as") == "user" else "/")
                         for c in data["commands"]][:50]
        self.root = [i for i, c in enumerate(self.commands) if c[2] == "root"]


def summary(commands):
    """'2 commands as root and 1 as you' (dvarapala's notification says the same)."""
    root = sum(c[2] == "root" for c in commands)
    user = len(commands) - root
    first = root or user
    text = f"{first} command{'s' * (first != 1)} as {'root' if root else 'you'}"
    return text + (f" and {user} as you" if root and user else "")


def short_home(path):
    home = pwd.getpwuid(os.getuid()).pw_dir
    return "~" + path[len(home):] if path == home or path.startswith(home + "/") else path


class ApprovalWindow(Adw.Window):
    def __init__(self, app, req, outdir):
        heading = "Authentication Required" if req.root else "Approval Required"
        super().__init__(application=app, title=heading)
        self.req, self.outdir = req, outdir
        self.started = time.monotonic()
        self.attempts = 0
        self.done = False          # result written
        self.running = False
        self.denying = False       # Deny pressed: asking for the optional note
        self.results = [{"index": i, "command": c, "why": w, "as": who, "cwd": cwd,
                         "decision": "approved", "state": "not_run"}
                        for i, (c, w, who, cwd) in enumerate(req.commands)]
        self.user = pwd.getpwuid(os.getuid()).pw_name
        self.checks, self.rows = [], []
        self.set_default_size(500, -1)
        self.connect("close-request", self.on_close)

        # Capture phase: the window sees Esc/Enter before any child.
        ctl = Gtk.EventControllerKey()
        ctl.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        ctl.connect("key-pressed", self.on_key)
        self.add_controller(ctl)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=28, margin_bottom=20, margin_start=28, margin_end=28)

        # Like GNOME's password prompts: an icon, a heading, what's asked.
        icon = Gtk.Image(icon_name="dialog-password-symbolic" if req.root else "system-run-symbolic",
                         pixel_size=64, margin_bottom=4)
        icon.add_css_class("dim-label")
        box.append(icon)
        self.heading = Gtk.Label(label=heading, wrap=True, justify=Gtk.Justification.CENTER)
        self.heading.add_css_class("title-2")
        box.append(self.heading)
        self.body = Gtk.Label(label=f"{req.requester} wants to run {summary(req.commands)}.",
                              wrap=True, justify=Gtk.Justification.CENTER)
        box.append(self.body)
        if req.reason:
            # The agent's own words: quoted, so they read as its claim.
            r = Gtk.Label(label=f"“{req.reason}”", wrap=True, selectable=True,
                          justify=Gtk.Justification.CENTER)
            r.add_css_class("dim-label")
            box.append(r)

        # The commands, exactly as they will run, in run order.
        cmds = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, margin_top=6)
        cmds.add_css_class("boxed-list")
        for i, (cmd, why, as_, cwd) in enumerate(req.commands):
            cmds.append(self.command_row(i, cmd, why, as_, cwd))
        cmds.connect("row-activated", lambda _lb, row: self.toggle(self.rows.index(row)))
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                      propagate_natural_height=True, max_content_height=340)
        scroller.set_child(cmds)
        box.append(scroller)

        # Password (only when something runs as root) and the note for the agent.
        fields = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        fields.add_css_class("boxed-list")
        self.password = Adw.PasswordEntryRow(title="Password", visible=bool(req.root))
        self.password.connect("entry-activated", lambda *_: self.on_run())
        self.password.connect("changed", lambda *_: self.password.remove_css_class("error"))
        fields.append(self.password)
        self.note = Adw.EntryRow(title="Note for the agent (optional)")
        self.note.connect("entry-activated", lambda *_: self.on_note_enter())
        fields.append(self.note)
        box.append(fields)

        self.error = Gtk.Label(visible=False, wrap=True, justify=Gtk.Justification.CENTER)
        self.error.add_css_class("error")
        box.append(self.error)

        how = []
        if req.root:
            how.append("Root commands run as root, from /.")
        if len(req.root) < len(req.commands):
            how.append(f"Commands marked YOU run as {self.user}, outside the agent's sandbox, without a password.")
        how.append("They run in order and stop at the first that fails. Untick anything you don't want run.")
        note = Gtk.Label(label=" ".join(how), wrap=True, justify=Gtk.Justification.CENTER)
        note.add_css_class("caption")
        note.add_css_class("dim-label")
        box.append(note)

        buttons = Gtk.Box(spacing=12, homogeneous=True, margin_top=8)
        self.cancel_btn = Gtk.Button(label="Cancel")
        self.cancel_btn.add_css_class("pill")
        self.cancel_btn.connect("clicked", lambda *_: self.deny_now(with_note=False) if self.denying
                                else self.ask_deny())
        buttons.append(self.cancel_btn)
        self.run_btn = Gtk.Button()
        self.run_btn.add_css_class("pill")
        self.run_btn.add_css_class("suggested-action")
        self.run_btn.connect("clicked", lambda *_: self.on_run())
        buttons.append(self.run_btn)
        box.append(buttons)

        # Answerable from the phone too, when ekatva runs (lib/remote.py).
        self.remote = remote.Remote.start(
            {"id": req.id, "via": "anumati", "requester": req.requester, "reason": req.reason,
             "commands": [{"cmd": c, "why": w, "as": who, **({"cwd": cwd} if who == "user" else {})}
                          for c, w, who, cwd in req.commands]},
            lambda answer: GLib.idle_add(self.remote_answer, answer), root=req.root)
        self.countdown = Gtk.Label(justify=Gtk.Justification.CENTER)
        self.countdown.add_css_class("caption")
        self.countdown.add_css_class("dim-label")
        box.append(self.countdown)

        # No title bar, like a system prompt; the whole window still drags.
        handle = Gtk.WindowHandle()
        handle.set_child(box)
        self.set_content(handle)
        self.update_run_label()
        self.tick()
        GLib.timeout_add_seconds(1, self.tick)
        (self.password if req.root else self.run_btn).grab_focus()

    def command_row(self, i, cmd, why, as_, cwd):
        row = Gtk.ListBoxRow(activatable=True)
        row.add_css_class("dvarapala-row")
        line = Gtk.Box(spacing=12)
        check = Gtk.CheckButton(active=True, valign=Gtk.Align.CENTER)
        check.connect("toggled", self.on_toggle, i)
        line.append(check)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        content.add_css_class("dvarapala-content")
        top = Gtk.Box(spacing=8)
        w = Gtk.Label(label=why or "(no reason given)", xalign=0, wrap=True, hexpand=True)
        w.add_css_class("heading")
        top.append(w)
        # Who it runs as, on every row, in its own colour: never implied by position.
        badge = Gtk.Label(label="ROOT" if as_ == "root" else "YOU", valign=Gtk.Align.START)
        badge.add_css_class("dvarapala-badge")
        badge.add_css_class("error" if as_ == "root" else "accent")
        top.append(badge)
        content.append(top)
        # The exact text that will run: selectable, wrapped by character so
        # nothing can hide past the edge.
        c = Gtk.Label(label=cmd, xalign=0, wrap=True, selectable=True)
        c.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        c.add_css_class("dvarapala-cmd")
        content.append(c)
        if as_ == "user":
            where = Gtk.Label(label=f"as {self.user}, in {short_home(cwd)}", xalign=0, wrap=True, selectable=True)
            where.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            where.add_css_class("caption")
            where.add_css_class("dim-label")
            content.append(where)
        line.append(content)
        row.set_child(line)
        self.checks.append(check)
        self.rows.append(row)
        return row

    # ---- selection -------------------------------------------------------
    def selected(self):
        return [i for i, c in enumerate(self.checks) if c.get_active()]

    def needs_password(self):
        return any(i in self.req.root for i in self.selected())

    def toggle(self, i):
        if self.checks[i].get_sensitive():
            self.checks[i].set_active(not self.checks[i].get_active())

    def on_toggle(self, check, i):
        self.results[i]["decision"] = "approved" if check.get_active() else "declined"
        (self.rows[i].remove_css_class if check.get_active() else self.rows[i].add_css_class)("declined")
        self.update_run_label()

    def update_run_label(self):
        if self.denying:
            return   # the buttons read "Deny Without Note" / "Deny" now
        n, total = len(self.selected()), len(self.req.commands)
        if not n:
            label = "Nothing Selected"
        else:
            label = "Authenticate" if self.needs_password() else "Allow"
            if n < total:
                label += f" ({n} of {total})"
        self.run_btn.set_label(label)
        self.run_btn.set_sensitive(n > 0 and not self.running and not self.done)
        if not self.running and not self.done:
            self.password.set_sensitive(self.needs_password())

    def focus_within(self, widget):
        f = self.get_focus()
        while f is not None:
            if f is widget:
                return True
            f = f.get_parent()
        return False

    def on_key(self, _ctrl, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            if not (self.running or self.done):
                self.deny_now(with_note=False) if self.denying else self.ask_deny()
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not (self.running or self.done):
            # The entries and buttons handle their own Enter.
            if self.focus_within(self.password) or self.focus_within(self.note) \
                    or isinstance(self.get_focus(), Gtk.Button):
                return False
            if self.denying:
                self.deny_now()
            elif self.needs_password() and not self.password.get_text():
                self.password.grab_focus()
            else:
                self.on_run()
            return True
        return False

    def tick(self):
        if self.done or self.running:
            self.countdown.set_label("")
            return not self.done
        left = EXPIRES_AFTER - int(time.monotonic() - self.started)
        if left <= 0:
            self.finish_denied("timeout", f"No answer within {EXPIRES_AFTER // 60} minutes.")
            return False
        phone = " · also on your phone" if self.remote.connected else ""
        self.countdown.set_label(f"Expires in {left // 60}:{left % 60:02d}, then counts as denied{phone}")
        return True

    # ---- denying, with an optional note ------------------------------------
    def ask_deny(self):
        """Deny, but first offer the note: the agent learns why and can
        correct itself. Already written a note, or asked once: deny now."""
        if self.running or self.done:
            return
        if self.denying or self.note.get_text().strip():
            self.deny_now()
            return
        self.denying = True
        for w in self.checks:
            w.set_sensitive(False)
        self.password.set_text("")
        self.password.set_visible(False)   # nothing will run: no password to ask for
        self.heading.set_label("Deny This Request?")
        self.body.set_label("Tell the agent why, or what to do instead, so it can adjust. "
                            "Enter denies with your note; Esc denies without one.")
        self.note.set_title("Why are you denying this? (optional)")
        self.cancel_btn.set_label("Deny Without Note")
        self.run_btn.set_label("Deny")
        self.run_btn.remove_css_class("suggested-action")
        self.run_btn.add_css_class("destructive-action")
        self.run_btn.set_sensitive(True)
        self.note.grab_focus()

    def deny_now(self, with_note=True):
        if not with_note:
            self.note.set_text("")
        self.finish_denied("denied", "The user denied the request.")

    def on_note_enter(self):
        if self.denying:
            self.deny_now()
        else:
            self.run_btn.grab_focus()   # Enter in the note never runs anything by itself

    def quit(self):
        self.get_application().quit()

    # ---- an answer from the phone ------------------------------------------
    def remote_answer(self, answer):
        """The same as answering here: the ticks you see are what runs, and
        the password goes through the same sudo check."""
        if self.done or self.running:
            return False
        if not answer["approve"]:
            self.finish_denied("denied", "Denied on the phone.")
            return False
        for i, check in enumerate(self.checks):
            check.set_active(i in answer["allow"])
        if answer["password"] is not None:
            self.password.set_text(answer["password"])
        answer["password"] = None
        self.on_run()
        return False

    # ---- running ---------------------------------------------------------
    def on_run(self):
        if self.denying:
            self.deny_now()   # the button reads "Deny" now
            return
        if self.running or self.done or not self.selected():
            return
        pw = self.password.get_text()
        if self.needs_password() and not pw:
            self.password.grab_focus()
            return
        self.running = True
        # Move focus off the password field before disabling it: disabling the
        # focused widget left GTK's focus broken.
        self.set_focus(None)
        for w in (*self.checks, self.password, self.cancel_btn):
            w.set_sensitive(False)
        self.run_btn.set_sensitive(False)
        self.error.set_visible(False)
        if not self.needs_password():
            self.password.set_text("")
            self.start_run(None)
            return
        self.run_btn.set_label("Checking…")
        threading.Thread(target=self.check_password, args=(pw,), daemon=True).start()

    def check_password(self, pw):
        try:
            p = subprocess.run([SUDO, "-S", "-k", "-p", "", "--", "/usr/bin/true"],
                               input=(pw + "\n").encode(), capture_output=True, timeout=30)
            ok = p.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            ok = False
        GLib.idle_add(self.after_password, ok, pw if ok else None)

    def after_password(self, ok, pw):
        if not ok:
            self.attempts += 1
            self.running = False
            if self.attempts >= MAX_ATTEMPTS:
                self.finish_denied("auth_failed", f"Wrong password {MAX_ATTEMPTS} times.")
                return False
            self.remote.send({"t": "wrong", "attempts": self.attempts})
            self.error.set_label(f"Sorry, that didn't work. Please try again "
                                 f"(attempt {self.attempts} of {MAX_ATTEMPTS}).")
            self.error.set_visible(True)
            for w in (*self.checks, self.password, self.cancel_btn):
                w.set_sensitive(True)
            self.password.set_text("")
            self.password.add_css_class("error")
            self.password.grab_focus()
            self.update_run_label()
            return False
        self.password.set_text("")
        self.start_run(pw)
        return False

    def start_run(self, pw):
        """Answered: the window and the phone's request go now, the commands
        run on without them, and the agent waits for the result."""
        chosen = self.selected()
        for i, r in enumerate(self.results):
            if i not in chosen:
                r["state"] = "declined"
        self.set_visible(False)
        self.remote.send({"t": "done", "status": "approved"})
        self.remote.close()
        threading.Thread(target=self.run_all, args=(pw, chosen), daemon=True).start()

    def run_all(self, pw, chosen):
        """The chosen commands in request order: each run of consecutive
        ROOT commands goes to the root runner (one sudo), each YOU command
        runs here; the first failure skips the rest. With no window left to
        show a crash, anything unexpected still has to reach the agent."""
        try:
            self.run_groups(pw, chosen)
        except Exception as e:
            GLib.idle_add(self.finish, "error", f"The run stopped unexpectedly: {e}")

    def run_groups(self, pw, chosen):
        groups = []
        for i in chosen:
            who = self.req.commands[i][2]
            if groups and groups[-1][0] == who:
                groups[-1][1].append(i)
            else:
                groups.append((who, [i]))
        env = userrun.build_env(userrun.manager_env(), pwd.getpwuid(os.getuid()).pw_dir) \
            if any(who == "user" for who, _ in groups) else None
        failed = False
        for who, idxs in groups:
            if failed:
                for i in idxs:
                    GLib.idle_add(self.on_event, {"event": "skipped"}, i)
                continue
            if who == "root":
                ok, err = self.run_root(pw, idxs)
                if err is not None:
                    GLib.idle_add(self.finish, "error", err)
                    return
                failed = not ok
                continue
            for i in idxs:
                if failed:
                    GLib.idle_add(self.on_event, {"event": "skipped"}, i)
                    continue
                cmd, _, _, cwd = self.req.commands[i]
                GLib.idle_add(self.on_event, {"event": "start"}, i)
                res = userrun.run(cmd, cwd, env)
                GLib.idle_add(self.on_event, {"event": "done", **res}, i)
                failed = res["exit_code"] != 0
        del pw
        GLib.idle_add(self.finish, "completed", "Ran the approved commands.")

    def run_root(self, pw, idxs):
        """(all succeeded, error message if the runner itself broke)"""
        payload = {"id": self.req.id, "requester": self.req.requester,
                   "commands": [self.req.commands[i][0] for i in idxs],
                   "stop_on_failure": True, "timeout": 1800}
        ok, finished = True, False
        try:
            p = subprocess.Popen([SUDO, "-S", "-k", "-p", "", "--", "/usr/bin/python3", "-I", RUNNER],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            p.stdin.write((pw + "\n" + json.dumps(payload) + "\n").encode())
            p.stdin.close()
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("event") == "finished":
                    finished = True
                elif ev.get("event") in ("start", "done", "skipped"):
                    if ev.get("event") == "done" and ev.get("exit_code") != 0:
                        ok = False
                    GLib.idle_add(self.on_event, ev, idxs[ev["index"]])
            p.wait()
            err = p.stderr.read().decode("utf-8", "replace").strip()
        except OSError as e:
            return False, f"The root runner couldn't start: {e}"
        if not finished:
            # The runner died before "finished" (sudo refused, python error...)
            return False, f"The root runner exited with {p.returncode}: {err[-500:]}"
        return ok, None

    def on_event(self, ev, i):
        kind = ev.get("event")
        r = self.results[i]
        if kind == "start":
            r["state"] = "running"
        elif kind == "skipped":
            r["state"] = "skipped"
        elif kind == "done":
            code = ev["exit_code"]
            r.update(state="ok" if code == 0 else "failed", exit_code=code, stdout=ev["stdout"],
                     stderr=ev["stderr"], duration=ev["duration"], timed_out=ev["timed_out"],
                     truncated=ev.get("truncated", False))
        return False

    # ---- result ----------------------------------------------------------
    def finish_denied(self, status, message):
        for r in self.results:
            r["decision"] = "declined" if status == "denied" else r["decision"]
            r["state"] = "not_run"
        self.finish(status, message)

    def finish(self, status, message):
        if self.done:
            return
        self.done = True
        self.running = False
        self.remote.send({"t": "done", "status": status})
        self.remote.close()
        message, extra = feedback_fields(self.note.get_text(), message)
        result = {"id": self.req.id, "status": status, "message": message, **extra,
                  "approved": [r["index"] for r in self.results if r["decision"] == "approved" and status == "completed"],
                  "declined": [r["index"] for r in self.results if r["decision"] == "declined"],
                  "results": self.results}
        try:
            write_json_atomic(os.path.join(self.outdir, "result.json"), result)
        except OSError as e:
            print(f"dvarapala dialog: can't write the result: {e}", file=sys.stderr)
        self.log(result)
        self.quit()

    def log(self, result):
        try:
            os.makedirs(os.path.dirname(STATE_LOG), exist_ok=True)
            entry = {"time": time.time(), "id": self.req.id, "requester": self.req.requester,
                     "reason": self.req.reason, "status": result["status"],
                     **({"feedback": result["feedback"]} if "feedback" in result else {}),
                     "commands": [{"cmd": r["command"], "as": r["as"], "cwd": r["cwd"], "decision": r["decision"],
                                   "state": r["state"], "exit_code": r.get("exit_code")} for r in self.results]}
            with open(STATE_LOG, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    def on_close(self, *_):
        if not self.done:
            if self.running:
                return True  # the password is being checked; a right one hides the window
            self.finish_denied("denied", "The user closed the window.")
        return False


def main():
    harden()
    if len(sys.argv) != 2:
        print("usage: dialog.py <request-dir>", file=sys.stderr)
        return 2
    outdir = sys.argv[1]
    try:
        req = Request(os.path.join(outdir, "request.json"))
    except (OSError, ValueError, KeyError, TypeError) as e:
        write_json_atomic(os.path.join(outdir, "result.json"),
                          {"status": "error", "message": f"bad request: {e}", "results": []})
        return 2
    Adw.init()   # follows the system's light/dark style and accent colour
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), provider,
                                              Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", lambda a: ApprovalWindow(a, req, outdir).present())
    app.run([])
    return 0


if __name__ == "__main__":
    sys.exit(main())
