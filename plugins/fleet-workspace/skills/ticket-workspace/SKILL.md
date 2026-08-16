---
name: ticket-workspace
description: Set up and manage multi-repo work — clone a fleet of repositories, create a per-ticket workspace of git worktrees holding only the repos a ticket changes, and tear it down safely. Use when starting or finishing work on a ticket that spans more than one repo, when setting up the fleet for the first time, or when asked where to make a change across several repositories. Trigger phrases: "start a ticket", "new ticket", "work on PROJ-", "set up the fleet", "clone the repos", "finish this ticket", "clean up the workspace", "which repos do I need".
---

# Ticket workspaces over a fleet of repositories

Two levels, and the distinction is the whole design:

- **The fleet** — every repo cloned side by side under one root, all on their
  default branch. Read-mostly: it exists to be searched and to be the base for
  worktrees. **Feature work never happens here.** Because nothing is edited in
  it, the daily refresh can hard-reset without losing anything.
- **A ticket workspace** — a directory per ticket containing **git worktrees**
  (not fresh clones) of only the repos that ticket changes, each on a branch
  named for the ticket.

Worktrees, not clones, is the point: a ticket costs no re-clone of a large repo,
and the fleet stays the single copy on disk.

## Resolving the commands

The working directory is the user's project, so these are never on a relative
path. Resolve once and reuse:

```sh
FW="${CLAUDE_PLUGIN_ROOT}/scripts"     # installed as a plugin
"$FW/fleet-init" --status
```

From a clone instead, use `plugins/fleet-workspace/scripts`.

## First: is the fleet set up?

**Always run `fleet-init --status` before anything else.** It answers in one
shot whether there is a config, where the roots point, and which repos are
actually cloned — and every other command in this skill is meaningless until
that is true.

```sh
"$FW/fleet-init" --status
```

If it reports no config:

```sh
"$FW/fleet-init" --config --fleet-root ~/code/fleet --tickets-root ~/tickets
"$FW/fleet-init" --clone acme/inventory-api acme/checkout-service ...
"$FW/fleet-init" --cron          # prints the daily refresh line for crontab -e
```

`--config` writes `~/.config/repo-fleet/fleet.env`; environment variables still
override it. `--clone` takes `owner/repo` or full URLs, uses `gh` when available
so private repos work, and **skips repos already present** — so re-running it is
how you add repos later, not something to avoid. `--clone-from <file>` reads one
per line.

**Do not guess the roots or the repo list.** If they are not configured and the
user has not said, ask. A fleet pointed at the wrong directory silently produces
empty search results, which is worse than an error.

### Company-specific setup is a hook, not a code change

A fresh worktree has no `node_modules`, no restored packages, no local `.env`.
What a repo needs before work can start differs per company, so `new-ticket`
runs an optional executable per repo — `~/.config/repo-fleet/hooks/post-create`
(every repo) and `<repo>/.fleet/post-create` (that repo). Both get
`FLEET_TICKET`, `FLEET_REPO`, `FLEET_WORKTREE`, `FLEET_BRANCH`, `FLEET_ROOT`,
`TICKETS_ROOT`, with the worktree as the working directory.

If the user asks for setup steps to run automatically when a workspace is
created, **write a hook** — do not modify the scripts. `fleet-init --config`
scaffolds `hooks/post-create.sample` to copy. `fleet-init --status` lists the
hooks it can see, and flags any that exist but are not executable, which is the
usual reason one silently does nothing.

Branch naming is configurable the same way, in `~/.config/repo-fleet/fleet.env`:
`BRANCH_PREFIX` (default `feature/`), or `BRANCH_TEMPLATE` such as
`users/zvi/{ticket}` when the convention is not a prefix.

A hook that fails **warns and continues** — the workspace is still created, and
the exit code is reported. If a user says setup "didn't run", check in this
order: is the hook executable, did it exit non-zero, is it in the worktree or
only the fleet clone.

## Daily: refresh the fleet

```sh
"$FW/refresh-fleet"                    # every repo
"$FW/refresh-fleet" inventory-api      # or named ones
```

Fetches and hard-resets each repo to its origin default branch, detected from
`origin/HEAD` rather than assumed to be `main`. A repo with local modifications
means someone worked directly in the fleet, which violates the model — it is
reported and skipped rather than reset; `--force` discards. Worktrees on other
branches are unaffected.

## Starting a ticket

```sh
"$FW/new-ticket" PROJ-123 inventory-api checkout-service
```

Creates `$TICKETS_ROOT/PROJ-123/` with a worktree per repo on
`feature/PROJ-123`. All repo names are validated **before anything is created**,
so a typo cannot leave a half-built workspace.

**Re-running resumes rather than restarts**: an existing branch is reused and
repos already in the workspace are left alone, so adding a repo to a live ticket
is just running it again with the extra name.

Choosing which repos to include is the one judgement call. Include a repo if the
ticket changes it. If you are unsure whether a change reaches another repo, find
out *before* creating the workspace, using the `code-search` plugin against the
whole fleet — that is exactly what `cs uses` and `cs deps` are for.

## Searching from inside a workspace

If the `code-search` plugin is installed, `cs` detects the workspace and layers
it automatically — the ticket's repos at your branch state, every other repo at
the fleet's default branch:

```
searching: PROJ-123 (2 repo(s), your branch) + fleet (8 repo(s), main)
```

This matters more than it sounds, and it is the reason the two levels exist.
Searching **only** the workspace makes renaming a shared route look safe, because
the caller that breaks lives in a repo the ticket does not contain. Searching
**only** the fleet shows stale copies of the files you are editing. Both answers
are wrong in ways that do not announce themselves.

So after changing anything shared — a route, a topic name, a config key, a
published symbol — search the **whole fleet** before concluding the change is
contained:

```sh
cs uses '/api/v1/inventory/reserve'   # from inside the workspace: ticket + fleet
cs deps inventory-api                 # which repos declare a dependency on it
```

`cs --fleet` ignores the workspace; `cs --ticket=<id>` layers a named one.

## Finishing a ticket

```sh
"$FW/close-ticket" PROJ-123
```

Removes each worktree and deletes the local branches. It **refuses** to remove a
worktree with uncommitted changes, or one holding commits not yet in the default
branch, so unmerged work is never silently discarded. It exits non-zero when
anything was blocked.

- `--force` discards and removes anyway.
- `--keep-branches` removes the worktrees but retains the branches.

A blocked repo is left in place while clean ones are still removed, so a partial
teardown is normal: resolve the blocked repo (push, merge, or discard) and run it
again. Nothing that was removed had unmerged work — the guards guarantee that.

## Reporting to the user

Give paths as `repo/path:line`. When you say a change is contained to the
ticket's repos, say what you checked — a fleet-wide `cs uses` returning nothing
is weak evidence if the caller could build the string at runtime, and the
`code-search` plugin labels every answer with exactly how much it is worth.
