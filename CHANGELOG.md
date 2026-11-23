# Changelog

Newest first. Releases are tags (`vX.Y.Z`) with `VERSION` in `bin/dvarapala`.

## v1.10.1 -- 2026-11-23

- **The sudo stand-in also catches agents outside a sandbox.** With no
  controlling terminal to ask for a password on, sudo can only fail unless no
  password is needed; then the stand-in runs plain sudo (cached or NOPASSWD
  credentials), and otherwise tells the agent to use dvarapala instead of
  printing sudo's "a terminal is required". `-S` and `-A` (a password from
  stdin or an askpass helper) always go straight to sudo.
- Fixed: in dash, the terminal check's failed redirection ended the script
  with exit 2 instead of reaching the hint (now checked in a subshell).

## v1.10.0 -- 2026-11-23

- **Notification first.** A request no longer opens a window that takes the
  keyboard focus: the window posts a notification and stays hidden until you
  click it (or its Review button), then opens with the click's activation
  token. Dismissing the notification denies the request, as closing the window
  does. Without a notification server the window opens straight away (ADR 15).
- **The notification goes away by itself** once the request is answered:
  approved, denied, timed out, answered on the phone. `bin/dvarapala` no longer
  sends its own critical notification, the one that never closed.
- **In the journal.** The window runs with `SyslogIdentifier=dvarapala`:
  `journalctl --user -t dvarapala` shows each request and its commands, the
  notification, when it was opened, the answer and the user's note. The root
  runner logs each root command and its exit code to the system journal as
  `dvarapala-root`, next to `/var/log/dvarapala.log`.

## v1.9.1 -- 2026-11-23

- **Steel grey, like GNOME Shell's own prompts.** The window takes Adwaita's
  dialog background (`#36363a` in dark, as the shell's keyring and polkit
  prompts), neutral buttons with the shell's 12px corners instead of an
  accent-filled Authenticate, and Adwaita's slate accent for the checkboxes and
  focus ring, whatever the system accent is. All of them are Adwaita's own
  palette colours (ADR 14).

## v1.9.0 -- 2026-11-23

- **The window looks like GNOME's own password prompts.** Stock libadwaita in
  the system's light or dark style and accent colour: a key icon, a heading
  ("Authentication Required"), who is asking and the agent's reason, the
  commands in a rounded list (each with its reason, a ROOT or YOU badge and a
  checkbox), the password and the note for the agent as entry rows, and Cancel /
  Authenticate as two wide buttons. No title bar; the whole window drags. The
  button says how many of the commands you've left ticked ("Authenticate (2 of
  3)"). A wrong password says so under the fields and marks the field red.
- **GNOME's keys.** Tab moves, Space ticks, Enter authenticates (or goes to the
  password first), Esc denies, asking once for the note; Esc again denies
  without one. The vim keymap, its footer and Ctrl+H are gone.
- The deny step hides the password field (nothing will run) and turns the
  buttons into "Deny Without Note" and "Deny".
- Removed `lib/theme.py`, `lib/keys.py`, `scripts/keybinds.py` and their tests;
  `install.sh` deletes their installed copies. ADR 13 supersedes ADR 6.

## v1.8.0 -- 2026-11-23

- **Tell the agent why.** A "Note for the agent" field under the commands:
  why you deny or untick something, or what to do instead. Deny (the button,
  `q` or `Esc`) now asks for it once before closing: Enter denies with the
  note, Esc denies without one, so denying stays two keys. `m` jumps to the
  field from the cards; Enter in it never runs anything. The note comes back
  in the result as `feedback` and at the end of `message`, with any answer
  (deny, timeout, or a run with unticked commands), and is kept in your
  request log. The MCP tool and schema tell agents to follow it and never
  resend the same commands unchanged (ADR 11).
- **Agents find dvarapala on their own.** `install.sh` puts a root-owned
  `/usr/local/bin/sudo` stand-in ahead of `/usr/bin/sudo`: outside an agent
  sandbox it is plain sudo (`exec /usr/bin/sudo "$@"`); inside one, where the
  no_new_privs flag makes real sudo fail anyway, it tells the agent to use
  `request_commands` or `dvarapala` instead. A `/usr/local/bin/sudo` that
  isn't ours is left alone; `--uninstall` removes only ours (ADR 12). The MCP
  server's instructions say the same.
- **Debian and Ubuntu.** Root commands find `/usr/sbin` and `/sbin` (sysctl,
  usermod, swapon...: separate directories there, links on Arch), and run with
  `DEBIAN_FRONTEND=noninteractive`, since they have no stdin. `install.sh`
  installs the dependencies with apt too, as it does with pacman.

## v1.7.0 -- 2026-11-09

- Every corner is rounded: the website's callouts.
- A logo and a shloka at the top of the README and the website: every Vayu tool has them now.

- Vim keys, modal like every Vayu tool but kept small (no Space leader): the
  window opens in **insert** mode in the password field when a command runs as
  root, otherwise in **normal** mode on the first command card. Normal: `j`/`k`
  move between the commands (`gg`/`G` first/last), `x` or `Space` ticks the
  one you're on, `a` / `n` tick all / none, `Enter` runs (or goes to the
  password first), `i` types the password, `q` or `Esc` denies. In the
  password field `Esc` goes back to the cards instead of denying at once;
  `Esc` again denies. Moving between cards no longer needs Tab.
- The card you're on has the accent border, and the footer shows the mode.
- Enter or Space on the Deny / Run buttons (reached with Tab) still presses
  that button. Tab and Shift+Tab still move the focus, and Ctrl chords that
  aren't the window's (Ctrl+C on a selected command) still reach GTK: NORMAL
  mode had swallowed every key it didn't know, so Tab went nowhere.
- `Ctrl+H` hides the window while the password is being checked too, as it did
  before the vim keys.
- The keys are data, resolved by Vyom's keys module (`lib/keys.py`, vendored,
  installed root-owned with the rest); `scripts/keybinds.py` writes the
  `# keybind:` lines and the README table, and CI checks them.

## v1.6.0 -- 2026-11-02

- **Renamed from anumati to dvarapala** (द्वारपाल, the guardian at the temple
  door; ADR 10). The command and MCP server are `dvarapala`;
  `/usr/local/bin/anumati` stays as a root-owned link to it, so agents and notes
  that still say anumati keep working. Reinstall with `./install.sh`.

## v1.5.0 -- 2026-11-02

- **The window closes as soon as you answer** (ADR 9). It used to stay up
  until the commands finished, showing each one's result, and stayed open
  after a failure until you closed it. Now it goes the moment you approve
  (after a right password, if one was needed) or deny; a wrong password
  still keeps it open to retry. The commands run on in the same process with
  no window, and the agent waits for the results, as before. The phone's
  request clears at the same moment.
- Gone with the results view: the per-card state and output, and the
  `Enter (after a failed run)` key. A failure now reaches you through the
  agent, which gets the full output; the logs are as before.
- `Ctrl+H` hides the window at any time. Hiding isn't an answer: an
  unanswered request can still be answered from the phone, otherwise the
  agent waits until it expires and counts as denied. It can't be brought back.
- If the run breaks unexpectedly, the agent now gets an `error` result
  instead of waiting forever on a process with no window.

## v1.4.0 -- 2026-10-28

- **Commands as you, not just as root** (ADR 8). A command can say
  `"as": "user"` (with an optional absolute `cwd`, default: home): for
  anything an agent can't run itself, like a command its sandbox blocks.
  It shows in the same window with a YOU badge (ROOT ones get a red badge
  and border), numbered in run order, with "as <user>, in <folder>" under
  it; the top bar counts each kind. YOU commands run as you from the window
  with a click: the password is asked for only when a ROOT command is
  ticked, and a request with only YOU commands has no password field.
  Commands run in request order, stopping at the first failure of either
  kind; each run of ROOT commands is one `sudo -k`. Without `"as"` a
  command is ROOT, so 1.x requests are unchanged; `cwd` on a ROOT command
  is refused.
- YOU commands get an allowlisted environment from the systemd user
  manager, not the agent's (no `BASH_ENV`, `LD_PRELOAD`, exported
  functions; `PATH` without relative or world-writable folders), and no
  login shell. New `lib/userrun.py` (pure Python, tested), installed next
  to the window.
- MCP: the tool is now `request_commands`; `request_root_commands` is still
  listed, as the same tool. CLI: `--as user` and `--cwd` for the one-off
  form. Results and your `requests.jsonl` carry each command's `as` and
  `cwd`; notifications say "Approval requested" when nothing runs as root.
- Answering from the phone: approving only YOU commands needs no password
  (`lib/remote.py`'s `parse_answer` takes the ROOT indexes); the request
  sent to ekatva carries `as` and `cwd`.
- Enter on a command's checkbox runs the request (or moves to the password
  field when it's needed and empty).

## v1.3.0 -- 2026-10-26

- Answer from your phone: when [ekatva](https://github.com/Theyashsawarkar/ekatva)
  runs, the window also hands its request to ekatva
  (`/run/user/<uid>/ekatva-root.sock`), which shows it on your paired
  phone. Approving there (which commands, and your password) ticks those
  commands in the window and fills the password field, then goes through
  the same sudo check and runner as typing it here; a wrong password is
  reported back so you can retry from the phone; denying there denies.
  The window sends nothing secret out, finds the socket by uid (not the
  agent's environment), and validates every answer strictly. Without
  ekatva nothing changes. New `lib/remote.py` (pure Python, tested), ADR 7.
  The footer says "also on your phone" while it's linked.

## v1.2.1 -- 2026-10-24

- The look and the theme check moved into `lib/theme.py` (pure Python),
  loaded by path by the window: the tests that check a tampered theme can't
  hide anything now run in CI, which has no GTK (1.2.0's CI failed there).
  install.sh installs it next to dialog.py.

## v1.2.0 -- 2026-10-24

- **Looks like the rest of the desktop.** The window has Vyom's layout: a
  "Root access" pill and the request in the top bar, the commands as
  rounded cards, the password and buttons, then the keys (Space, Enter,
  Esc) and the time left in the footer; Vyom's type, buttons and a 20 px
  glass card (0.84, never see-through enough to read what's behind).
- **In your theme, safely** (ADR 6). The colours come from varna's
  `palette.json`, read as plain `#rrggbb` data only, never CSS. The body
  text and the commands must stay readable (4.5:1) or the palette is
  ignored; the command is the theme's green only at 7:1, else plain text;
  any other colour that isn't readable enough becomes the text colour; the
  Run button's label is picked to read on the accent. A light theme gets a
  light window. Without varna: anumati's own colours, as before.
- Focus rings and selected text use the theme's accent (not GTK's blue).

## v1.1.1 -- 2026-10-21

- A website (GitHub Pages, https://theyashsawarkar.github.io/anumati/): the README as a home page, the
  changelog, and architecture decision records (`docs/adr/`), built from these files by
  `scripts/build-site.py`; CI checks the site is up to date.

## v1.1.0 -- 2026-10-21

- Renamed from `vayu-elevate` to **anumati** (अनुमति, "permission") and
  moved into its own repository. Everything moves with the name:
  `/usr/local/bin/anumati`, `/usr/local/lib/anumati/`,
  `/var/log/anumati.log`, `~/.local/state/anumati/requests.jsonl`, the
  window's app id `io.github.theyashsawarkar.Anumati`, the MCP server name.
- `install.sh` (was Vayu's `ai/apply.sh`) installs it root-owned, keeps
  `/usr/local/bin/vayu-elevate` as a link so the old name still works,
  removes the old `/usr/local/lib/vayu-elevate`, and gains `--uninstall`.
- Tests for request validation, and CI.

## v1.0.0 -- 2026-10-16

- First version, as `vayu-elevate` inside Vayu: the approval window, the
  root runner, JSON in and out, the MCP server, the audit logs.
