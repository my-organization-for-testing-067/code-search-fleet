#!/usr/bin/env bash
# Shared config and helpers for the fleet/ticket scripts.
# See skills/ticket-workspace/SKILL.md for the setup this assumes.

# Config precedence: environment > config file > defaults.
FLEET_CONFIG_DIR="${FLEET_CONFIG_DIR:-${HOME}/.config/repo-fleet}"
# shellcheck disable=SC1091
[[ -f "$FLEET_CONFIG_DIR/fleet.env" ]] && source "$FLEET_CONFIG_DIR/fleet.env"

FLEET_ROOT="${FLEET_ROOT:-${HOME}/code/fleet}"
TICKETS_ROOT="${TICKETS_ROOT:-${HOME}/tickets}"
BRANCH_PREFIX="${BRANCH_PREFIX:-feature/}"
# Full control over branch naming, for companies whose convention is not a
# prefix -- e.g. BRANCH_TEMPLATE='users/zvi/{ticket}'. {ticket} is substituted;
# when unset the prefix form is used.
BRANCH_TEMPLATE="${BRANCH_TEMPLATE:-}"

branch_for() {
  local ticket="$1"
  if [[ -n "$BRANCH_TEMPLATE" ]]; then
    printf '%s\n' "${BRANCH_TEMPLATE//\{ticket\}/$ticket}"
  else
    printf '%s\n' "${BRANCH_PREFIX}${ticket}"
  fi
}

if [[ -t 2 ]]; then
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BOLD=$'\033[1m'; C_OFF=$'\033[0m'
else
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BOLD=''; C_OFF=''
fi

info()  { printf '%s\n' "$*" >&2; }
ok()    { printf '%s✓%s %s\n' "$C_GREEN" "$C_OFF" "$*" >&2; }
warn()  { printf '%s!%s %s\n' "$C_YELLOW" "$C_OFF" "$*" >&2; }
err()   { printf '%s✗%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; }
die()   { err "$*"; exit 1; }

# List fleet repos (directory name only), one per line.
fleet_repos() {
  [[ -d "$FLEET_ROOT" ]] || die "fleet root not found: $FLEET_ROOT"
  local d
  for d in "$FLEET_ROOT"/*/; do
    [[ -d "${d}.git" ]] || continue
    basename "$d"
  done
}

# Default branch for a repo, from origin/HEAD, falling back to main then master.
default_branch() {
  local repo_dir="$1" ref
  if ref=$(git -C "$repo_dir" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null); then
    printf '%s\n' "${ref#refs/remotes/origin/}"
    return 0
  fi
  local b
  for b in main master; do
    if git -C "$repo_dir" show-ref --verify --quiet "refs/remotes/origin/$b"; then
      printf '%s\n' "$b"
      return 0
    fi
  done
  return 1
}

# ---- hooks -----------------------------------------------------------------
# The one thing that cannot be guessed from outside a company: what a repo needs
# before you can work in it. A fresh worktree has no node_modules, no restored
# NuGet packages, no local .env, no IDE files. Rather than encode any of that,
# two hook locations are run in order, both optional and both plain executables:
#
#   1. $FLEET_CONFIG_DIR/hooks/<name>   your machine — applies to every repo
#   2. <repo>/.fleet/<name>             the repo itself — travels with it, so a
#                                       team owns its own setup in version control
#
# Both receive the same environment: FLEET_TICKET, FLEET_REPO, FLEET_WORKTREE,
# FLEET_BRANCH, FLEET_ROOT, TICKETS_ROOT. The worktree is the working directory.
#
# A failing hook warns rather than aborts: a workspace that exists but is not
# fully provisioned is more useful than no workspace, and the failure is visible.
run_hooks() {
  local name="$1" repo="$2" worktree="$3" ticket="$4" branch="$5" hook rc origin
  # The repo-level hook is looked for in the worktree first and the fleet clone
  # second, so both ways of owning it work and neither runs twice: committed to
  # the repo (it is in the worktree, and every engineer gets it), or dropped
  # untracked into the fleet clone (yours alone, for a repo you cannot commit to).
  local repo_hook="$worktree/.fleet/$name"
  [[ -f "$repo_hook" ]] || repo_hook="$FLEET_ROOT/$repo/.fleet/$name"
  for hook in "$FLEET_CONFIG_DIR/hooks/$name" "$repo_hook"; do
    [[ -f "$hook" ]] || continue
    if [[ ! -x "$hook" ]]; then
      warn "    hook $name found but not executable, skipped: $hook"
      warn "    fix with: chmod +x $hook"
      continue
    fi
    case "$hook" in
      "$FLEET_CONFIG_DIR"/hooks/*) origin=global ;;
      "$worktree"/*)               origin="repo, committed" ;;
      *)                           origin="repo, local" ;;
    esac
    # `|| rc=$?` rather than a bare call then `$?`: the callers run under
    # `set -e`, where a failing subshell aborts the script outright -- so a
    # single broken hook would take the whole workspace down instead of
    # producing the warning below.
    rc=0
    (
      cd "$worktree" || exit 1
      export FLEET_TICKET="$ticket" FLEET_REPO="$repo" FLEET_WORKTREE="$worktree" \
             FLEET_BRANCH="$branch" FLEET_ROOT TICKETS_ROOT
      exec "$hook"
    ) </dev/null || rc=$?
    if [[ $rc -eq 0 ]]; then
      info "    hook: $name ($origin)"
    else
      warn "    hook $name ($origin) FAILED with exit $rc — worktree kept, finish setup by hand"
    fi
  done
}
