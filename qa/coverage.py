#!/usr/bin/env python3
"""
UI vs automation coverage: compares the controls the agent actually saw on screen with the fields,
locators, routes and tests in the automation framework, and lists the gaps.

  python3 qa/coverage.py ui <PID> --url /path --module Reports --controls "button:Execute; combobox:Partner; columnheader:Plate"
        record the controls of one page (from its accessibility snapshot); repeat-safe
  python3 qa/coverage.py status        pages already mapped (all runs) - to avoid re-mapping
  python3 qa/coverage.py report        writes coverage-gaps.md + coverage-summary.json into the current run

Controls are "role:name" exactly as in the snapshot (button, link, textbox, combobox, checkbox, radio,
tab, menuitem, columnheader, switch, spinbutton, searchbox, ...). Framework = framework_path in qa.config.yaml.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

QA = Path(__file__).resolve().parent
RUNS = QA / "runs"
NAV_ROLES = {"link", "menuitem"}


def norm(s: str) -> str:
    s = re.sub(r"[-_]+", " ", str(s).lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def norm_path(p: str) -> str:
    p = re.sub(r"^https?://[^/]+", "", str(p)).split("?")[0].split("#")[0].rstrip("/") or "/"
    return re.sub(r"/(\d+|[0-9a-f-]{16,}|:\w+|\$\{[^}]+\})(?=/|$)", "/:id", p.lower())


def current_run() -> Path:
    cur = RUNS / "CURRENT"
    if not cur.exists():
        sys.exit("No active run. Run: python3 qa/ledger.py init")
    return RUNS / cur.read_text(encoding="utf-8").strip()


def load_map(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def all_maps() -> dict:
    merged: dict = {}
    for f in sorted(RUNS.glob("*/ui-map.json")):
        for pid, pg in load_map(f).items():
            m = merged.setdefault(pid, {"url": pg.get("url", ""), "module": pg.get("module", ""), "controls": []})
            m["url"] = pg.get("url") or m["url"]
            m["module"] = pg.get("module") or m["module"]
            m["controls"] = list(dict.fromkeys(m["controls"] + pg.get("controls", [])))
    return merged


def cmd_ui(a) -> None:
    f = current_run() / "ui-map.json"
    m = load_map(f)
    pg = m.setdefault(a.pid, {"url": "", "module": "", "controls": []})
    if a.url:
        pg["url"] = a.url
    if a.module:
        pg["module"] = a.module
    new = []
    for c in re.split(r"[;\n]", a.controls or ""):
        c = c.strip()
        if ":" not in c:
            continue
        role, name = c.split(":", 1)
        c = f"{role.strip().lower()}:{name.strip()}"
        if name.strip() and c not in pg["controls"]:
            pg["controls"].append(c)
            new.append(c)
    f.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"ok ui {a.pid}: +{len(new)} controls ({len(pg['controls'])} total)")


def cmd_status(_a) -> None:
    m = all_maps()
    print(f"mapped pages: {len(m)} | controls: {sum(len(p['controls']) for p in m.values())}")
    by = defaultdict(list)
    for pid, p in m.items():
        by[p.get("module") or "?"].append(pid)
    for mod, pids in sorted(by.items()):
        print(f"- {mod}: {', '.join(sorted(pids))}")


def framework_json() -> dict:
    out = Path(tempfile.mkdtemp(prefix="qa-cov-")) / "fw.json"
    r = subprocess.run([sys.executable, "-I", str(QA / "scan_framework.py"), "--out", str(out.with_suffix(".md")),
                        "--json", str(out)], capture_output=True, text=True)
    if r.returncode or not out.exists():
        sys.exit(f"Framework scan failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return json.loads(out.read_text(encoding="utf-8"))


def cmd_report(_a) -> None:
    d = current_run()
    ui = all_maps()
    if not ui:
        sys.exit("No UI controls recorded yet (python3 qa/coverage.py ui ...). Run /qa-coverage or a test run first.")
    fw = framework_json()

    # framework index: name -> files that use it as a locator; text mentioned in tests/assertions
    loc: dict[str, set] = defaultdict(set)
    for rel, fields in fw.get("fields", {}).items():
        for f in fields:
            kind, _, val = f.partition(" ")
            names = []
            if kind == "role":
                names.append(val.split(":", 1)[-1])
            elif kind == "css":
                names += re.findall(r"#([\w-]+)|\[(?:name|id|data-testid|aria-label|placeholder)=['\"]?([^'\"\]]+)", val)
                names += re.findall(r"text=['\"]?([^'\"]+)", val)
                names = [n if isinstance(n, str) else (n[0] or n[1]) for n in names]
            else:
                names.append(val)
            for n in names:
                if norm(n):
                    loc[norm(n)].add(rel)
    mentions = " | ".join(norm(t) for ts in fw.get("tests", {}).values() for t in ts)
    mentions += " | " + " | ".join(norm(e) for es in fw.get("expects", {}).values() for e in es)
    fw_routes = set()
    for r in fw.get("routes", []):
        r = r.replace("expect URL ", "").strip().strip("'\"`")
        if re.match(r"^/.*/[gimsuy]*$", r) and "\\/" in r:  # regex like /\/approval\/\d+/
            r = re.sub(r"/[gimsuy]*$", "", r[1:]).replace("\\/", "/")
            r = re.sub(r"\\d\+|\[\^/\]\+|\.\+|\.\*|\\w\+", "1", r).strip("^$")
        if r.startswith(("/", "http")):
            fw_routes.add(norm_path(r))

    rows, gaps_by_mod, nav_seen = [], defaultdict(list), set()
    tot = cov_loc = cov_mention = 0
    seen_names = set()
    for pid, pg in sorted(ui.items(), key=lambda x: (x[1].get("module") or "", x[0])):
        mod = pg.get("module") or "?"
        path = norm_path(pg.get("url", ""))
        route_cov = any(path == r or (r != "/" and path.startswith(r.rstrip("/") + "/")) for r in fw_routes)
        p_tot = p_loc = 0
        uncovered = []
        for c in pg["controls"]:
            role, name = c.split(":", 1)
            n = norm(name)
            seen_names.add(n)
            if role in NAV_ROLES and n in nav_seen:
                continue  # count global nav links once
            if role in NAV_ROLES:
                nav_seen.add(n)
            p_tot += 1
            if n in loc:
                p_loc += 1
            elif n and n in mentions:
                cov_mention += 1
                uncovered.append(f"{c} _(only mentioned in a test title/assertion)_")
            else:
                uncovered.append(c)
        tot += p_tot
        cov_loc += p_loc
        rows.append((mod, pid, pg.get("url", ""), route_cov, p_tot, p_loc))
        if uncovered:
            gaps_by_mod[mod].append((pid, uncovered))

    stale = sorted({n for n in loc if n not in seen_names and len(n) > 2})
    zero = [r for r in rows if r[4] and r[5] == 0]
    pct = lambda a, b: f"{100 * a / b:.0f}% ({a}/{b})" if b else "n/a"

    L = ["# UI vs automation coverage gaps", "",
         f"Denominator: **{tot} distinct controls** on **{len(rows)} pages** the agent actually visited "
         "(global nav links counted once). Unvisited pages are not included.", "",
         f"- Controls targeted by a framework locator: **{pct(cov_loc, tot)}**",
         f"- Controls only mentioned in test titles/assertions (weak coverage): {cov_mention}",
         f"- Controls with **no automation reference**: {tot - cov_loc - cov_mention}",
         f"- Pages whose route appears in the framework: {pct(sum(r[3] for r in rows), len(rows))}",
         f"- Pages with **zero** locator coverage: {len(zero)}", "",
         "Matching is by accessible name/label/test-id/id. Locators built dynamically, or by CSS/XPath "
         "without a readable name, can't be matched, so treat gaps as **candidates to review**, not proof.", "",
         "## Coverage by page", "| Module | Page | URL | Route in framework | Controls | With locator |", "|---|---|---|---|---|---|"]
    for mod, pid, url, rc, t, c in rows:
        L.append(f"| {mod} | {pid} | {url} | {'yes' if rc else '**no**'} | {t} | {pct(c, t)} |")
    L += ["", "## Gaps by module (controls on screen with no automation locator)"]
    for mod in sorted(gaps_by_mod):
        L.append(f"### {mod}")
        for pid, items in gaps_by_mod[mod]:
            L.append(f"- **{pid}**: " + "; ".join(items[:40]) + (" …" if len(items) > 40 else ""))
        L.append("")
    if fw.get("skipped"):
        L += ["## Skipped / fixme tests (automation exists but doesn't run)"] + [f"- {s}" for s in fw["skipped"][:60]] + [""]
    L += ["## Framework locators not seen on any visited page",
          "Possibly stale (the UI changed) or on pages the agent didn't visit. Check before deleting.", ""]
    L += [f"- {n} — used in: " + ", ".join(sorted(loc[n])[:3]) for n in stale[:120]] or ["- none"]

    (d / "coverage-gaps.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    summary = {"pages": len(rows), "controls": tot, "with_locator": cov_loc, "mentioned_only": cov_mention,
               "uncovered": tot - cov_loc - cov_mention, "zero_coverage_pages": len(zero), "stale_locators": len(stale)}
    (d / "coverage-summary.json").write_text(json.dumps(summary), encoding="utf-8")
    rel = d.relative_to(QA.parent).as_posix()
    print(f"ok coverage -> {rel}/coverage-gaps.md | {len(rows)} pages, {tot} controls, "
          f"locator coverage {pct(cov_loc, tot)}, {tot - cov_loc - cov_mention} uncovered, "
          f"{len(zero)} zero-coverage pages, {len(stale)} possibly stale locators")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("ui"); p.add_argument("pid"); p.add_argument("--url"); p.add_argument("--module")
    p.add_argument("--controls", required=True); p.set_defaults(fn=cmd_ui)
    sp.add_parser("status").set_defaults(fn=cmd_status)
    sp.add_parser("report").set_defaults(fn=cmd_report)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
