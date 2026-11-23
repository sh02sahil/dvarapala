# 15. Notification first; the window opens on its click

**Status:** Accepted  
**Date:** 2026-11-23

## Context

The window opened the moment a request arrived and took the keyboard focus from whatever the user was typing; at worst, keystrokes meant for another app landed in the password field. A separate `notify-send` from `bin/dvarapala` announced the request at critical urgency, and nothing ever closed it, so it stayed on screen after the request was answered.

## Decision

The window process posts the request's notification itself, through `org.freedesktop.Notifications`, and stays hidden. Clicking the notification (or its Review button) opens the window, with the click's activation token, so the focus is given rather than taken. However the request ends (approved, denied, timed out, answered on the phone, wrong password three times), the window closes the notification. Dismissing the notification denies the request, as closing the window does; a click is remembered first, so the server's own close after a click is not taken for a dismissal. Without a notification server, the window opens straight away, as before. `bin/dvarapala` no longer sends a notification of its own.

The window's journal lines (`SyslogIdentifier=dvarapala`) record each request, the notification, the opening, the answer and the user's note; the root runner records each root command and its exit code in the system journal as `dvarapala-root`, next to its root-only audit file.

## Consequences

- A request never interrupts typing; the user opens it when ready, within the 10-minute expiry.
- Clearing all notifications denies any request still waiting, and the agent is told so.
- `journalctl --user -t dvarapala` and `journalctl -t dvarapala-root` show what was asked and what ran.
