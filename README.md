# ai-toolbox

Personal collection of AI-related tooling — mainly for Claude (Claude Code, claude.ai).

## Layout

```
ai-toolbox/
├── skills/     ← Claude Code skills, one folder per skill (skills/<name>/SKILL.md)
├── agents/     ← custom agent definitions (<name>.md with frontmatter)
└── prompts/    ← reusable prompts and prompt fragments
```

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
