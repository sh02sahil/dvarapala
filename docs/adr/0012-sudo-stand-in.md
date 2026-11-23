# 12. A sudo stand-in that points sandboxed agents at dvarapala

**Status:** Accepted  
**Date:** 2026-11-23

## Context

Agents reach for `sudo` first. Inside their sandbox (Claude Code, Codex, the Claude desktop app) the no_new_privs flag is set, so the kernel refuses sudo's setuid and sudo prints an error that says nothing about what to do instead. Each agent had to be told about dvarapala in its global instructions, and agents that weren't told asked the user to paste commands into a terminal.

## Decision

`install.sh` installs `lib/sudo-hint` root-owned as `/usr/local/bin/sudo`, which comes before `/usr/bin/sudo` in PATH. When no_new_privs is not set it `exec`s `/usr/bin/sudo "$@"`, so for the user nothing changes. When it is set, real sudo could not have worked, so it exits 1 and tells the agent to use the `request_commands` MCP tool or `dvarapala --why ... --cmd ...`. The MCP server's instructions say the same. A `/usr/local/bin/sudo` without the stand-in's marker is never replaced, and `--uninstall` removes only the stand-in.

## Consequences

- Agents find dvarapala at the first failed `sudo`, without per-agent instructions.
- It is root-owned like the rest, so an agent can't turn it into something that reads the password the user types into sudo in a terminal. (A user-writable directory earlier in PATH, such as `~/.local/bin`, could still shadow it; that was already true of sudo itself.)
- It only redirects: it never runs anything as root and never starts the window itself, because the agent still has to give a reason for each command.
