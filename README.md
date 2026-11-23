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
  merge_group: # only on a branch with a merge queue

permissions: {}

concurrency:
  # A merge group has no PR number: its unique ref keeps queue runs apart.
  group: pr-conventions-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  conventions:
    uses: GabinSMD/shared-workflows/.github/workflows/pr-conventions.yml@main
    # with:
    #   extra-prefixes: "schemas|fiches"   # repo-specific branch prefixes
```

The checks show up as `conventions / Branch name` and `conventions / PR title`. To make them blocking, add them as required status checks in the branch protection settings. On a branch with a merge queue, add `merge_group` to the caller's triggers first: in a merge group both jobs are skipped (no PR title or branch there), and GitHub counts a skipped required check as passing.

## Auto-merge

Squash-merges an agent's pull request **without a human**, one per run, only when it is provably safe:

1. **CI green**: every check run and status on the head commit finished and passed (at least one).
2. **Code review OK**: the latest comment starting with `Revue de code :` says `OK` and is newer than the last commit. A PR touching a **UI path** also needs a `QA : OK` comment newer than the last commit.
3. **No sensitive file**. Always sensitive, in every repo: `.github/`, migrations and `*.sql`, Dockerfiles and compose files, `package.json` and lockfiles, `.env*`, secrets, `LICENSE`, `CODEOWNERS`. Each repo adds its own (money, auth, personal data, deployment).
4. Not a draft, targets the default branch, branch in the repo itself (no forks), no `manual` / `manuel` / `no-auto-merge` label, mergeable.

Verdicts count only from **trusted authors** (default: the repo owner), since anyone can comment on a public repo. The workflow runs from the default branch only and never checks out PR code. Logic and tests: `scripts/auto_merge.py`, `tests/`.

**Off by default.** Without the repository variable `AUTO_MERGE` set to `on`, it is a dry run: the run summary lists what it would merge and why the others wait. Remove the variable to stop everything; add the `manuel` label to keep one PR for yourself.

A merge done with `GITHUB_TOKEN` triggers no `push` workflow: list deployment workflows in `after-merge-dispatch` (they need a `workflow_dispatch` trigger), and set `pages-build: true` for a legacy GitHub Pages site.

Add this file to a repo as `.github/workflows/auto-merge.yml` (adapt the CI workflow names and paths):

```yaml
name: Auto-merge

on:
  schedule:
    - cron: "7,37 * * * *"        # safety net
  issue_comment:
    types: [created]              # a review or QA verdict was posted
  workflow_run:
    workflows: ["CI"]             # the repo's CI workflow names
    types: [completed]
  workflow_dispatch:

permissions: {}

concurrency:
  group: auto-merge
  cancel-in-progress: false

jobs:
  auto-merge:
    if: github.event_name != 'issue_comment' || github.event.issue.pull_request
    permissions:
      contents: write
      pull-requests: write
      checks: read
      statuses: read
      actions: write
      pages: write
    uses: GabinSMD/shared-workflows/.github/workflows/auto-merge.yml@main
    with:
      enabled: ${{ vars.AUTO_MERGE == 'on' }}
      sensitive-paths: |
        server/
        deploy/
      ui-paths: |
        client/
      after-merge-dispatch: deploy.yml
```

The repository must allow squash merges. Protecting the default branch (pull request and green CI required) is recommended: agents then cannot push to it, even by mistake.

## Cloud session setup

`cloud/setup.sh` configures every Claude Code cloud environment the same way: git identity, no Claude attribution, and the personal rules (branch convention, one task per session, when to ask for a local session). Add this line to each environment's **Setup script** on claude.ai/code, after any project-specific steps:

```bash
curl -fsSL https://raw.githubusercontent.com/GabinSMD/shared-workflows/main/cloud/setup.sh | bash
```
