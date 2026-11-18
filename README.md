# shared-workflows

Reusable GitHub Actions workflows shared by all my projects. A rule changes here once and applies everywhere.

## PR conventions

Checks every pull request:

- **Branch**: `<type>/<issue>-<a-few-words>`, lowercase with hyphens, e.g. `feat/982-player-act-warnings`
- **PR title**: conventional commit in English, `type(scope): imperative sentence`, no final period
- **Types**: feat fix refactor perf test docs chore ci build security hotfix revert
- **Not checked**: long-lived branches (main, master, develop, staging) and bot PRs (Dependabot, Renovate, GitHub Actions)

Add this file to a repo as `.github/workflows/pr-conventions.yml`:

```yaml
name: PR conventions

on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

permissions: {}

concurrency:
  group: pr-conventions-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  conventions:
    uses: GabinSMD/shared-workflows/.github/workflows/pr-conventions.yml@main
    # with:
    #   extra-prefixes: "schemas|fiches"   # repo-specific branch prefixes
```

The checks show up as `conventions / Branch name` and `conventions / PR title`. To make them blocking, add them as required status checks in the branch protection settings. On a branch with a merge queue, also add `merge_group` to the caller's triggers first.

## Cloud session setup

`cloud/setup.sh` configures every Claude Code cloud environment the same way: git identity, no Claude attribution, and the personal rules (branch convention, one task per session, when to ask for a local session). Add this line to each environment's **Setup script** on claude.ai/code, after any project-specific steps:

```bash
curl -fsSL https://raw.githubusercontent.com/GabinSMD/shared-workflows/main/cloud/setup.sh | bash
```
