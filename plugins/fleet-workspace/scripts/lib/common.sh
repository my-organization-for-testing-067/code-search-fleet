#!/usr/bin/env bash
# Shared config and helpers for the fleet/ticket scripts.
# See skills/ticket-workspace/SKILL.md for the setup this assumes.

# Config precedence: environment > config file > defaults.
#
# Two paths, in this order: ~/.config/ai-toolbox/fleet.env is where this tooling
# used to live and is still honoured so an existing setup keeps working;
# ~/.config/repo-fleet/fleet.env is what `fleet-init --config` writes and wins,
# because the tooling is no longer ai-toolbox-specific.
for _cfg in "${HOME}/.config/ai-toolbox/fleet.env" "${HOME}/.config/repo-fleet/fleet.env"; do
  # shellcheck disable=SC1090
  [[ -f "$_cfg" ]] && source "$_cfg"
done
unset _cfg

FLEET_ROOT="${FLEET_ROOT:-${HOME}/code/fleet}"
TICKETS_ROOT="${TICKETS_ROOT:-${HOME}/tickets}"
BRANCH_PREFIX="${BRANCH_PREFIX:-feature/}"

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
