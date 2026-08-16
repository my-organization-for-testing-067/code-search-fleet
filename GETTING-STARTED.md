# Getting started

An opinionated setup for working across many repositories at once. Two plugins:

| Plugin | What it gives you |
|---|---|
| **`fleet-workspace`** | One directory holding every company repo, plus a per-ticket workspace of git worktrees for just the repos that ticket touches |
| **`code-search`** | One search interface over five engines, which understands that layout — search a ticket and the rest of the fleet as one thing |

You mostly do not run these commands yourself. They are **Claude Code skills**:
you describe what you want, the agent runs them. The commands are here because
knowing what it will do is how you tell whether it did the right thing.

---

## 1. Install

```sh
claude plugin marketplace add my-organization-for-testing-067/code-search-fleet
claude plugin install fleet-workspace@code-search-fleet
claude plugin install code-search@code-search-fleet
```

Restart Claude Code so the skills load. Check with `claude plugin list`.

## 2. Set up the fleet, once

Say to the agent:

> **"Set up the repo fleet. Put the repos in ~/code/fleet and ticket workspaces
> in ~/tickets, then clone our repos: acme/inventory-api, acme/checkout-service,
> acme/web-monorepo."**

It will run roughly this:

```sh
fleet-init --status     # nothing configured yet
fleet-init --config --fleet-root ~/code/fleet --tickets-root ~/tickets
fleet-init --clone acme/inventory-api acme/checkout-service acme/web-monorepo
fleet-init --cron       # prints the line for the daily refresh
```

`--clone` uses `gh` when it is available, so private repos work. Repos already
present are skipped, so **re-running `--clone` later is how you add repos**.

Then add the printed line to `crontab -e` so the fleet stays current:

```
0 7 * * *  /path/to/refresh-fleet --quiet
```

The fleet is hard-reset daily. That is safe **only** because you never edit it
directly — all work happens in ticket workspaces. This is the one rule of the
whole setup.

## 3. Start a ticket

> **"Start ticket PROJ-123. It changes the inventory API and the checkout
> service."**

```sh
new-ticket PROJ-123 inventory-api checkout-service
```

You get `~/tickets/PROJ-123/` with a **git worktree** per repo on branch
`feature/PROJ-123`. Not clones — no re-downloading a large repo per ticket.

If you do not know which repos a ticket touches, ask before creating it:

> **"Which repos use the endpoint /api/v1/inventory/reserve?"**

Re-running `new-ticket` **resumes** rather than restarts, so adding a repo later
is just running it again with the extra name.

## 4. Work, and search as you go

From inside the workspace, search sees your branch *and* every repo the ticket
does not contain:

> **"Who else calls /api/v1/inventory/reserve?"**

```
searching: PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)
checkout-service/src/main/kotlin/.../InventoryClient.kt:12
web-monorepo/packages/admin-ui/src/restockTool.ts:5

answer: heuristic via ripgrep (literal, prose filtered) · 2 hit(s) · 2 repo(s)
```

**That second hit is the point of the whole setup.** `web-monorepo` is not in the
ticket. Searching only your workspace would have made renaming that route look
safe.

Read the `answer:` line before trusting a result — especially an empty one. It
says what kind of evidence produced it, and `cs why <kind>` says what that kind
cannot see. A `textual` "nothing found" is weak evidence; a `resolved` one is
strong.

## 5. Finish

> **"I'm done with PROJ-123, clean it up."**

```sh
close-ticket PROJ-123
```

It **refuses** to remove a worktree with uncommitted changes, or one holding
commits not in the default branch, so unmerged work is never silently lost.
`--force` overrides once you are sure.

---

## Customising it for your company

Two things differ everywhere, and both are extension points rather than code you
need to fork.

### Branch naming

Edit `~/.config/repo-fleet/fleet.env`:

```sh
export BRANCH_PREFIX="feature/"              # default -> feature/PROJ-123

# Or take full control; {ticket} is substituted, and this wins over the prefix:
export BRANCH_TEMPLATE="users/zvi/{ticket}"  # -> users/zvi/PROJ-123
```

### Per-repo setup (`post-create` hooks)

A fresh worktree has no `node_modules`, no restored packages, no local `.env`.
What a repo needs before you can work in it cannot be guessed from outside your
company, so it is a hook: an ordinary executable, run once per repo, with the
worktree as the working directory.

**Two places, both optional, run in this order:**

| Location | Scope | Use it for |
|---|---|---|
| `~/.config/repo-fleet/hooks/post-create` | your machine, every repo | copying local secrets, editor setup |
| `<repo>/.fleet/post-create` | one repo | that repo's install/restore step |

The per-repo one is looked for in the worktree first and the fleet clone second,
so **either** works: commit `.fleet/post-create` to the repo and every engineer
gets it, or drop it untracked into your fleet clone if you cannot commit to that
repo.

`fleet-init --config` scaffolds `hooks/post-create.sample`. Enable it with:

```sh
cd ~/.config/repo-fleet/hooks && cp post-create.sample post-create && chmod +x post-create
```

Each hook receives:

```
FLEET_TICKET    PROJ-123
FLEET_REPO      inventory-api
FLEET_WORKTREE  /Users/you/tickets/PROJ-123/inventory-api
FLEET_BRANCH    feature/PROJ-123
FLEET_ROOT      /Users/you/code/fleet
TICKETS_ROOT    /Users/you/tickets
```

A minimal one:

```sh
#!/usr/bin/env bash
set -euo pipefail
[[ -f "$FLEET_ROOT/$FLEET_REPO/.env.local" ]] && cp "$FLEET_ROOT/$FLEET_REPO/.env.local" .
if   [[ -f package.json ]];         then npm ci --silent
elif [[ -f pyproject.toml ]];       then uv sync --quiet
elif compgen -G '*.sln*' >/dev/null; then dotnet restore --verbosity quiet
fi
```

**Whatever a hook writes into the worktree must be gitignored by that repo.**
`node_modules` and `.env.local` normally are. Anything that is not shows up in
`git status`, which makes the worktree permanently dirty — and `close-ticket`
then refuses to tear it down. It will tell you when the only changes are
untracked files, which is the signal that a hook is the cause.

**A failing hook warns; it does not abort.** A workspace that exists but is not
fully provisioned beats no workspace, and you see the exit code:

```
✓ inventory-api — new branch off origin/main
    hook: post-create (global)
!     hook post-create (repo, local) FAILED with exit 1 — worktree kept, finish setup by hand
```

`fleet-init --status` lists every hook it can see, including ones that are
present but **not executable** — the most common reason a hook silently does
nothing.

### Search

`cs engines` shows which engines are installed; `scripts/bootstrap` installs the
missing ones. Every engine is optional and `cs` routes around absences.

```sh
export CS_EXCLUDE_EXTRA="generated proto_gen"  # extra dirs to skip
export CS_MAX_RESULTS=200    # cap; 0 for unlimited, or pass --all
export CS_TIMEOUT=120        # per-engine seconds; a timeout reports PARTIAL
```

---

## Checking it works

```sh
fleet-init --status                 # config, repos, hooks, live tickets
cs engines                          # which search engines are present
scripts/verify-search               # 20 checks against a throwaway fixture fleet
```

`verify-search` builds its own fixture repos, so it answers "does this work on
**this** machine" rather than "did it work where it was built". Run it if search
results ever look wrong.

## Where things are

| | |
|---|---|
| Agent-facing search skill | `skills/code-search/SKILL.md` |
| Agent-facing workflow skill | `plugins/fleet-workspace/skills/ticket-workspace/SKILL.md` |
| Why the search is built this way | `README.md`, `fixtures/BASELINE.md` |
| Your config | `~/.config/repo-fleet/fleet.env` |
| Your hooks | `~/.config/repo-fleet/hooks/` |
