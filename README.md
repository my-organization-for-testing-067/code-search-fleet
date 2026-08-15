# ai-toolbox

Personal collection of AI-related tooling — mainly for Claude (Claude Code, claude.ai).

## Layout

```
ai-toolbox/
├── skills/     ← Claude Code skills, one folder per skill (skills/<name>/SKILL.md)
├── agents/     ← custom agent definitions (<name>.md with frontmatter)
├── prompts/    ← reusable prompts and prompt fragments
├── scripts/    ← fleet and ticket-workspace tooling
├── fixtures/   ← throwaway multi-repo fixture for testing that tooling
└── docs/       ← setup conventions and workflow docs
```

## Multi-repo workflow

`docs/repo-fleet.md` is the source of truth for working across the company's
repos: a fleet directory holding every repo on main, ticket workspaces built
from git worktrees, and the search model layered over them.

```sh
scripts/cs uses "/api/v1/inventory/reserve"        # search: one facade over 5 engines
scripts/cs engines                                 # which engines are installed
scripts/refresh-fleet                              # daily: pull every repo to origin main
scripts/new-ticket PROJ-123 repo-a repo-b          # worktrees + indexes for a ticket
scripts/close-ticket PROJ-123                      # tear it down when merged
scripts/build-fixtures /tmp/fixture-fleet          # fake fleet to test the above
```

Configure roots in `~/.config/ai-toolbox/fleet.env` (`FLEET_ROOT`,
`TICKETS_ROOT`, `BRANCH_PREFIX`) or via the environment.

## Skills

Each skill lives in `skills/<name>/SKILL.md` with frontmatter:

```markdown
---
name: my-skill
description: One line describing when Claude should use this skill.
---

Instructions for the skill…
```

To use a skill in a project, symlink or copy it into that project's
`.claude/skills/`, or into `~/.claude/skills/` to make it available everywhere:

```sh
ln -s ~/git/home/ai-toolbox/skills/<name> ~/.claude/skills/<name>
```

## Agents

Agent definitions (`agents/<name>.md`) follow the same idea — symlink into
`~/.claude/agents/` or a project's `.claude/agents/`.
