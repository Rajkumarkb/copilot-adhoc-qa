#!/usr/bin/env python3
"""
Find what changed in the automation framework since the app model was last built, so the
Adhoc QA agent can update its flow logic and test new/changed fields first.

  python3 qa/ci/diff_inventory.py [--base SHA] [--app-changes FILE]

Base commit, in order: qa/knowledge/model-base.txt (sha the committed app-model was built from),
--base, HEAD~1. Writes:
  qa/knowledge/framework-inventory.md   (fresh scan of HEAD)
  qa/knowledge/changes.md               (new/removed tests, fields, routes, APIs, skips, changed files)
  qa/knowledge/model-base.next          (HEAD sha: commit it as model-base.txt with a refreshed model)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

QA = Path(__file__).resolve().parent.parent
REPO = QA.parent
KN = QA / "knowledge"
SCAN = QA / "scan_framework.py"


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(r.stderr.strip())
    return r.stdout.strip()


def valid_sha(sha: str | None) -> bool:
    return bool(sha) and set(sha) != {"0"} and subprocess.run(
        ["git", "-C", str(REPO), "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode == 0


def scan(path: Path, md: Path, js: Path) -> dict:
    subprocess.run([sys.executable, "-I", str(SCAN), str(path), "--out", str(md), "--json", str(js)],
                   check=True, stdout=subprocess.DEVNULL)
    return json.loads(js.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base")
    ap.add_argument("--app-changes", help="file listing app-repo changed files (from repository_dispatch)")
    a = ap.parse_args()

    head = git("rev-parse", "HEAD")
    mb = KN / "model-base.txt"
    base, why = None, ""
    if mb.exists() and valid_sha(mb.read_text().strip()):
        base, why = mb.read_text().strip(), "model-base.txt (commit the app model was built from)"
    elif valid_sha(a.base):
        base, why = a.base, "previous main commit"
    elif valid_sha(git("rev-parse", "HEAD~1", check=False)):
        base, why = git("rev-parse", "HEAD~1"), "HEAD~1"

    tmp = Path(tempfile.mkdtemp(prefix="qa-diff-"))
    KN.mkdir(exist_ok=True)
    new = scan(REPO, KN / "framework-inventory.md", tmp / "head.json")
    (KN / "model-base.next").write_text(head + "\n", encoding="utf-8")

    L = [f"# Changes since the app model was built (auto-generated)", ""]
    if not base or base == head:
        L += [f"Base: none (`{head[:8]}`). No diff available; treat the whole app as unchanged baseline.", ""]
        old = None
    else:
        wt = tmp / "base"
        git("worktree", "add", "--detach", "--force", str(wt), base)
        try:
            old = scan(wt, tmp / "base.md", tmp / "base.json")
        finally:
            git("worktree", "remove", "--force", str(wt), check=False)
        L += [f"Base `{base[:8]}` ({why}) → HEAD `{head[:8]}`", ""]

    count = 0
    if old is not None:
        def section(title: str, items: list[str]) -> None:
            nonlocal count
            if items:
                count += len(items)
                L.append(f"## {title} ({len(items)})")
                L.extend(f"- {i}" for i in items[:150])
                if len(items) > 150:
                    L.append(f"- … {len(items) - 150} more")
                L.append("")

        def per_file(key: str, label_new: str, label_gone: str) -> tuple[list[str], list[str]]:
            add, gone = [], []
            for f in sorted(set(new[key]) | set(old[key])):
                a_, b_ = set(new[key].get(f, [])), set(old[key].get(f, []))
                add += [f"`{f}`: {x}" for x in sorted(a_ - b_)]
                gone += [f"`{f}`: {x}" for x in sorted(b_ - a_)]
            return add, gone

        f_add, f_gone = per_file("fields", "NEW FIELD", "REMOVED FIELD")
        t_add, t_gone = per_file("tests", "NEW TEST", "REMOVED TEST")
        e_add, _ = per_file("expects", "", "")
        section("NEW or CHANGED fields / locators (test these first)", f_add)
        section("REMOVED fields / locators", f_gone)
        section("NEW tests (new or changed behaviour)", t_add)
        section("REMOVED tests", t_gone)
        section("NEW or CHANGED assertions (expected results)", e_add)
        section("NEW routes", sorted(set(new["routes"]) - set(old["routes"])))
        section("NEW API calls", sorted(set(new["apis"]) - set(old["apis"])))
        section("NEWLY skipped / fixme tests", sorted(set(new["skipped"]) - set(old["skipped"])))
        section("New page objects", sorted(set(new["page_objects"]) - set(old["page_objects"])))
        files = [f for f in git("diff", "--name-only", base, head).splitlines()
                 if f and not f.startswith(("qa/", ".github/", ".vscode/"))]
        section("Changed framework files", files)

    if a.app_changes and Path(a.app_changes).exists():
        app = [l.strip() for l in Path(a.app_changes).read_text(encoding="utf-8").splitlines() if l.strip()]
        if app:
            count += len(app)
            L += [f"## AlertBus app files changed ({len(app)})", *[f"- {x}" for x in app[:200]], ""]

    if count == 0:
        L.append("No framework or app changes detected since the base commit.")
    (KN / "changes.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"ok changes -> qa/knowledge/changes.md | {count} change items | base {base[:8] if base else 'none'} -> {head[:8]}")


if __name__ == "__main__":
    main()
