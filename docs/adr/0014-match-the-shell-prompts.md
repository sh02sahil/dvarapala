# 14. Match GNOME Shell's own prompts: dialog grey, neutral buttons, slate accent

**Status:** Accepted (amends [13](0013-stock-adwaita.md): the accent no longer follows the system)  
**Date:** 2026-11-23

## Context

ADR 13 made the window stock libadwaita, following the system accent. On a desktop with a blue accent, that gave a blue Authenticate button, blue checkboxes and a blue focus ring, while the prompts it should look like (the keyring's and polkit's, drawn by GNOME Shell) are steel grey: GNOME Shell 50's theme gives `.modal-dialog` a `#36363a` background with 18px corners, and its buttons are neutral (bold, 12px corners, white on `rgba(255,255,255,0.1)`), with the accent only as a faint focus outline.

## Decision

The window uses three of Adwaita's own palette variables the way the shell's prompts look: `--dialog-bg-color` for its background (`#36363a` in dark, as in the shell), the built-in `--accent-slate` as its accent (checkboxes, focus ring, the YOU badge), and plain neutral buttons with 12px corners instead of an accent-filled Authenticate. Deny keeps Adwaita's destructive style.

## Consequences

- It looks like the shell's prompts whatever the system accent is.
- Every colour is still one of Adwaita's own, in its light and dark styles, so text stays readable and nothing user-controlled styles the window (ADR 13 still holds there).
