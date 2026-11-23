# 11. Ask for a note when the user denies

**Status:** Accepted  
**Date:** 2026-11-23

## Context

A denied request told the agent only that it was denied. Agents then guessed: they retried the same command, tried a slightly different one, or gave up, when the user usually had a reason worth one line ("use the distro package, not the snap", "don't touch /etc/fstab, I'll do it"). The window had no place to say it.

## Decision

The window has a "Note for the agent" field under the commands. Deny (the button, `q` or `Esc`) asks for the note once before closing: Enter denies with the note, Esc denies without one, so a deny stays two keys and nobody has to write anything. A note already written, or a second Deny, denies at once. Enter in the note field never runs anything. Whatever the answer (denied, timed out, or a run with unticked commands), a note goes back as the result's `feedback` and at the end of `message`, and into the user's request log. The MCP tool description and the schema tell agents to follow it and never resend the same commands unchanged.

## Consequences

- Denying costs one more key (Esc Esc, or Deny then Esc) than it did.
- The note is the user's own text, made one line and capped at 2000 characters; it goes to the agent, never to the root runner.
- An answer from the phone carries no note (ekatva has no field for it).
