#!/usr/bin/env python3
"""Auto-merge: squash-merge ONE pull request per run when it is provably safe.

Called by .github/workflows/auto-merge.yml. Reads everything through the
GitHub API; never checks out or runs pull request code.

A PR is merged only if ALL of these hold:
  1. open, not a draft, targets the default branch, branch in this repo
     (no forks), no skip label;
  2. it touches NO sensitive path (money, auth, personal data, migrations,
     CI and deployment, dependencies: listed per repo by the caller);
  3. the latest "Revue de code :" comment is OK and newer than the last
     commit; if it touches a UI path, the latest "QA :" comment too.
     Verdicts count only from trusted authors (public repos accept comments
     from anyone);
  4. every check run and commit status on the head commit is finished and
     green, and there is at least one (this job's own run excluded);
  5. GitHub says it is mergeable.

One merge per run: the next run re-evaluates the others against the new base.
Without --enabled it only reports what it would do (dry run).
"""
import argparse
import datetime
import fnmatch
import json
import os
import subprocess
import sys

GREEN = {"success", "neutral", "skipped"}
REVIEW_PREFIX = "revue de code"
QA_PREFIX = "qa"


# ----------------------------------------------------------------- pure logic

def parse_globs(text):
    """Newline- or comma-separated globs; blank lines and # comments ignored."""
    out = []
    for line in (text or "").replace(",", "\n").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def matches(path, globs):
    """fnmatch where ** spans directories and a trailing / means 'everything under'."""
    for g in globs:
        if g.endswith("/"):
            g = g + "**"
        if fnmatch.fnmatchcase(path, g) or fnmatch.fnmatchcase(path, g.replace("**/", "")):
            return g
    return None


def verdict(comments, prefix, trusted, since):
    """Latest verdict of one kind ('revue de code' or 'qa') from a trusted author.
    Returns 'ok', 'changes', 'stale' (OK but older than the last commit) or None."""
    latest = None
    for c in comments:
        body = (c.get("body") or "").lstrip().lower()
        if (c.get("author") or "").lower() not in trusted:
            continue
        head = body.split("\n", 1)[0]
        if not (head.startswith(prefix + " :") or head.startswith(prefix + ":")):
            continue
        if latest is None or c["created_at"] >= latest["created_at"]:
            latest = dict(c, head=head)
    if latest is None:
        return None
    rest = latest["head"].split(":", 1)[1].strip()
    if rest.startswith("ok"):
        return "ok" if latest["created_at"] > since else "stale"
    return "changes"


def checks_state(check_runs, statuses, own_names):
    """'green', 'pending', 'red' or 'none' for the head commit."""
    runs = [r for r in check_runs if r.get("name") not in own_names]
    if not runs and not statuses:
        return "none"
    if any(r.get("status") != "completed" for r in runs) or any(s.get("state") == "pending" for s in statuses):
        return "pending"
    if any(r.get("conclusion") not in GREEN for r in runs) or any(s.get("state") != "success" for s in statuses):
        return "red"
    return "green"


def decide(pr, files, comments, last_commit_at, checks, cfg):
    """Return (merge: bool, reason: str). Pure: everything comes in as data."""
    if pr.get("draft"):
        return False, "draft"
    if pr["base"] != cfg["default_branch"]:
        return False, f"targets {pr['base']}, not {cfg['default_branch']}"
    if pr["head_repo"] != cfg["repo"]:
        return False, "branch from a fork"
    skip = set(pr.get("labels", [])) & set(cfg["skip_labels"])
    if skip:
        return False, f"label {sorted(skip)[0]}"
    if not files:
        return False, "no file changed"
    for f in files:
        g = matches(f, cfg["sensitive"])
        if g:
            return False, f"sensitive path {f} ({g})"
    review = verdict(comments, REVIEW_PREFIX, cfg["trusted"], last_commit_at)
    if review != "ok":
        return False, f"code review: {review or 'missing'}"
    if any(matches(f, cfg["ui"]) for f in files):
        qa = verdict(comments, QA_PREFIX, cfg["trusted"], last_commit_at)
        if qa != "ok":
            return False, f"QA (UI change): {qa or 'missing'}"
    if checks != "green":
        return False, f"checks {checks}"
    if pr.get("mergeable") is not True:
        return False, f"not mergeable ({pr.get('mergeable_state')})"
    return True, "all conditions met"


# ----------------------------------------------------------------- GitHub API

def gh(path, method="GET", fields=None, paginate=False):
    cmd = ["gh", "api", "-X", method, path]
    if paginate:
        cmd.insert(2, "--paginate")
        cmd += ["--jq", ".[]"]
    for k, v in (fields or {}).items():
        cmd += ["-f", f"{k}={v}"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{method} {path}: {out.stderr.strip()[:300]}")
    if paginate:
        return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    return json.loads(out.stdout) if out.stdout.strip() else None


def load(repo, number):
    pr = gh(f"repos/{repo}/pulls/{number}")
    files = []
    for f in gh(f"repos/{repo}/pulls/{number}/files?per_page=100", paginate=True):
        files.append(f["filename"])
        if f.get("previous_filename"):
            files.append(f["previous_filename"])
    comments = [{"author": c["user"]["login"], "body": c["body"], "created_at": c["created_at"]}
                for c in gh(f"repos/{repo}/issues/{number}/comments?per_page=100", paginate=True)]
    commits = gh(f"repos/{repo}/pulls/{number}/commits?per_page=100", paginate=True)
    last = max(c["commit"]["committer"]["date"] for c in commits) if commits else ""
    sha = pr["head"]["sha"]
    runs = gh(f"repos/{repo}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
    statuses = gh(f"repos/{repo}/commits/{sha}/status").get("statuses", [])
    info = {"number": number, "title": pr["title"], "draft": pr["draft"], "base": pr["base"]["ref"],
            "head_repo": (pr["head"].get("repo") or {}).get("full_name"), "sha": sha,
            "labels": [l["name"] for l in pr["labels"]], "mergeable": pr.get("mergeable"),
            "mergeable_state": pr.get("mergeable_state")}
    return info, files, comments, last, runs, statuses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--enabled", action="store_true")
    a = ap.parse_args()
    env = os.environ
    repo = env["GITHUB_REPOSITORY"]
    cfg = {
        "repo": repo,
        "default_branch": gh(f"repos/{repo}")["default_branch"],
        "sensitive": parse_globs(env.get("SENSITIVE_PATHS")) + parse_globs(env.get("ALWAYS_SENSITIVE")),
        "ui": parse_globs(env.get("UI_PATHS")),
        "trusted": {t.lower() for t in parse_globs(env.get("TRUSTED_AUTHORS")) or [repo.split("/")[0]]},
        "skip_labels": parse_globs(env.get("SKIP_LABELS")) or ["manual", "manuel", "no-auto-merge"],
    }
    own = set(parse_globs(env.get("OWN_CHECK_NAMES")))
    summary = [f"### Auto-merge ({'enabled' if a.enabled else 'DRY RUN'})", "", "| PR | Decision | Reason |", "|---|---|---|"]
    merged = None
    for p in gh(f"repos/{repo}/pulls?state=open&per_page=100", paginate=True):
        try:
            info, files, comments, last, runs, statuses = load(repo, p["number"])
            ok, why = decide(info, files, comments, last, checks_state(runs, statuses, own), cfg)
        except Exception as e:
            ok, why = False, f"error: {e}"
        print(f"#{p['number']}: {'MERGE' if ok else 'skip'} - {why}")
        summary.append(f"| #{p['number']} {p['title'][:60]} | {'merge' if ok else 'skip'} | {why} |")
        if ok and merged is None:
            merged = dict(info, ui=any(matches(f, cfg["ui"]) for f in files))
    if merged and a.enabled:
        n = merged["number"]
        gh(f"repos/{repo}/pulls/{n}/merge", "PUT", {"merge_method": "squash", "sha": merged["sha"],
                                                      "commit_title": f"{merged['title']} (#{n})"})
        gh(f"repos/{repo}/issues/{n}/comments", "POST", {"body": (
            "Fusion automatique : CI verte, revue de code OK"
            + (", QA OK" if merged["ui"] else "")
            + ", aucun fichier sensible. Pour l'empêcher sur une PR : étiquette `manuel`.")})
        if env.get("DELETE_BRANCH") == "true":
            branch = gh(f"repos/{repo}/pulls/{n}")["head"]["ref"]
            try:
                gh(f"repos/{repo}/git/refs/heads/{branch}", "DELETE")
            except RuntimeError as e:
                print(f"branch not deleted: {e}")
        for wf in parse_globs(env.get("AFTER_MERGE_DISPATCH")):
            gh(f"repos/{repo}/actions/workflows/{wf}/dispatches", "POST", {"ref": cfg["default_branch"]})
            print(f"dispatched {wf}")
        if env.get("PAGES_BUILD") == "true":
            gh(f"repos/{repo}/pages/builds", "POST")
            print("pages build requested")
        summary.append(f"\n**Merged #{n}.**")
        print(f"MERGED #{n}")
    elif merged:
        summary.append(f"\nWould merge #{merged['number']} (dry run).")
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
