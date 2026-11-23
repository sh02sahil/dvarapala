# 13. Stock Adwaita, like the system's password prompts

**Status:** Accepted (supersedes [6](0006-themed-but-never-hidden.md))  
**Date:** 2026-11-23

## Context

The window wore its own look: Vyom's panels in the user's varna theme, a vim-style modal keymap with a key footer, and Nerd Font glyphs. That was right inside Vayu, but on a stock GNOME desktop it looked like no other prompt on the system, and a password prompt earns trust by looking like the system's own. ADR 6 then needed a contrast check so that a theme could never hide a row.

## Decision

The window is stock libadwaita, laid out like GNOME's password prompts (the keyring's, polkit's): an icon, a heading, who is asking and why, the commands in a boxed list (each with its reason, a ROOT or YOU badge and a checkbox), the password and the note for the agent as entry rows, and Cancel / Authenticate as two wide buttons. It follows the system's light or dark style and accent colour through the settings portal. Its own CSS sets only layout and fonts (padding, monospace for commands, the badge's shape); every colour is Adwaita's. Keys are GNOME's: Tab, Space, Enter, Esc. The theme module, the vendored keys module and their tests are gone; install.sh removes their installed copies.

## Consequences

- Nothing user-controlled styles the window: user CSS is still kept out by the root-owned XDG dirs, and Adwaita's light, dark and accent variants all keep text readable, so ADR 6's contrast check has nothing left to check.
- No vim keys and no Ctrl+H to hide the window; an unanswered request still expires after 10 minutes, and the phone can still answer it.
- It no longer matches a Vayu desktop's panels; it matches GNOME instead.
