#!/usr/bin/env python3
"""
Adhoc QA ledger: keeps the application map, coverage ledger, E2E flow, notes and
defect register on disk so the Copilot chat never has to hold them in context.

Short, terse output on purpose (token saving). Cross-platform (Windows/macOS/Linux).

Commands (run from the workspace root):
  python qa/ledger.py init                    start a new run from qa/qa.config.yaml
  python qa/ledger.py brief                   re-print the run brief (scope, rules)
  python qa/ledger.py page  <PID> [--url U] [--title T] [--module M] [--status S] [--role R] [--note N]
  python qa/ledger.py feat  <PID> "<feature>" [--status S] [--dims pos,neg,bnd,nav,data,role,ui] [--note N]
  python qa/ledger.py flow  "<action>" --from URL --to URL [--data D] [--result R] [--assert A] [--ev FILE]
  python qa/ledger.py note  <obs|ambiguity|blocker|env|activity> "<text>"
  python qa/ledger.py defect-new "<title>"    creates defects/D-###.yaml template, prints its path
  python qa/ledger.py status                  compact coverage + next targets (use instead of reading files)
  python qa/ledger.py report                  builds report.md + report.html for the current run

Statuses: discovered | visited | partial | explored | blocked | na
Dims:     pos=positive  neg=negative  bnd=boundary  nav=navigation/state
          data=persistence/integrity  role=role/permission  ui=UI/interaction
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
   import yaml  # PyYAML
except ImportError:  # pragma: no cover - fall back to the project .venv created by qa/setup.py
   _venv = Path(__file__).resolve().parent.parent / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
   if _venv.exists() and not os.environ.get("QA_LEDGER_IN_VENV"):
       import subprocess
       sys.exit(subprocess.call([str(_venv), *sys.argv], env={**os.environ, "QA_LEDGER_IN_VENV": "1"}))
   sys.exit("PyYAML missing. Run: python3 qa/setup.py")

ROOT = Path(__file__).resolve().parent            # .../qa
CONFIG = ROOT / "qa.config.yaml"
RUNS = ROOT / "runs"
CURRENT = RUNS / "CURRENT"

STATUSES = {
    "discovered": "Discovered", "visited": "Visited", "partial": "Partially Explored",
    "explored": "Explored", "blocked": "Blocked", "na": "Not Applicable",
}
DIMS = {
    "pos": "Positive path", "neg": "Negative path", "bnd": "Boundary / edge",
    "nav": "Navigation & state", "data": "Data persistence", "role": "Role & permission",
    "ui": "UI & interaction",
}
SEVERITIES = ["Critical", "High", "Medium", "Low"]
KINDS = ["confirmed", "suspected", "environment", "ambiguity"]
VERDICTS = ["NOT READY", "CONDITIONAL", "READY FOR REVIEW"]

DEFECT_TEMPLATE = """# Fill every field you have evidence for. Write "unavailable" rather than guessing.
id: {id}
title: "{title}"
kind: suspected          # confirmed | suspected | environment | ambiguity
status: Open             # Open | Fixed-Retested | Won't fix | Duplicate
severity: Medium         # Critical | High | Medium | Low
priority: P2             # P1 | P2 | P3 | P4
severity_rationale: ""
module: ""
page: ""
environment: "{env}"
browser: "Chromium (Playwright MCP)"
url: ""
navigation_path: ""
preconditions: ""
role: ""
steps:
  - ""
test_data: ""            # sanitized, never real secrets
expected: ""
expected_source: ""      # requirement / business rule / convention / "assumed - needs confirmation"
actual: ""
reproducibility: ""      # e.g. 3/3, intermittent 2/5 (conditions)
evidence: []             # e.g. [qa/runs/<run>/evidence/D-001.png], console/network excerpts
related: ""
business_impact: ""
recommendation: ""
"""

NARRATIVE_TEMPLATE = """# Final narrative for the report. Keep each answer short (1-4 lines).
# Only describe what was ACTUALLY done. Leave a key empty rather than inventing.
testing_period: ""
scope: ""
exclusions: ""
overall_outcome: ""
highest_risk_findings: ""
major_blockers: ""
major_workflows: ""
roles_examined: ""
integrations_identified: ""
unknown_or_inaccessible: ""
e2e_flow_name: ""
e2e_final_outcome: ""
e2e_uncertainties: ""
buddy_testing: ""
pair_testing: ""
monkey_testing: ""
positive_negative: ""
boundary_testing: ""
navigation_state: ""
data_integrity: ""
auth_checks: ""
other_techniques: ""
risk_business: ""
risk_data: ""
risk_authorization: ""
risk_workflow_integration: ""
risk_untested_areas: ""
risk_environment: ""
action_immediate: ""
action_investigate: ""
action_retest: ""
action_remaining_exploration: ""
action_blockers: ""
action_next_priorities: ""
verdict: ""              # NOT READY | CONDITIONAL | READY FOR REVIEW
verdict_reason: ""
"""


# ----------------------------------------------------------------------------- io
def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_yaml(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_dir() -> Path:
    if not CURRENT.exists():
        sys.exit("No active run. Run: python qa/ledger.py init")
    d = RUNS / CURRENT.read_text(encoding="utf-8").strip()
    if not d.exists():
        sys.exit(f"Run folder missing: {d}")
    return d


def load_ledger(d: Path) -> dict:
    with open(d / "ledger.json", encoding="utf-8") as f:
        return json.load(f)

IDLE_CAP_SEC = 600  # gaps longer than 10 min between ledger writes count as idle, not testing time

def touch(led: dict) -> None:
   """Accumulate ACTIVE testing time (calendar gaps between sessions are not counted)."""
   t = dt.datetime.now().astimezone()
   last = led.get("last_touch")
   if last:
       gap = (t - dt.datetime.fromisoformat(last)).total_seconds()
       led["active_sec"] = led.get("active_sec", 0) + max(0, min(gap, IDLE_CAP_SEC))
   led["last_touch"] = t.isoformat(timespec="seconds")

def active_min(led: dict) -> int:
   return int(led.get("active_sec", 0) // 60)

def save_ledger(d: Path, led: dict) -> None:
    touch(led)  # update last modified timestamp before saving
    tmp = d / "ledger.json.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(led, f, indent=1, ensure_ascii=False)
    os.replace(tmp, d / "ledger.json")


def norm_status(s: str | None) -> str | None:
    if s is None:
        return None
    k = s.strip().lower().replace(" ", "")
    alias = {"partiallyexplored": "partial", "notapplicable": "na", "n/a": "na"}
    k = alias.get(k, k)
    if k not in STATUSES:
        sys.exit(f"Bad status '{s}'. Use: {', '.join(STATUSES)}")
    return k


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


# ----------------------------------------------------------------------- commands
def cmd_init(_a) -> None:
    if not CONFIG.exists():
        sys.exit("qa/qa.config.yaml not found.")
    cfg = load_yaml(CONFIG)
    base = str(cfg.get("base_url", "")).strip()
    if not base or "example.com" in base:
        sys.exit("Set base_url in qa/qa.config.yaml to your QA environment first.")
    prod = [h.lower() for h in cfg.get("production_hosts") or []]
    origin = f"{urlparse(base).scheme}://{urlparse(base).netloc}".lower()
    authorized = [h.lower() for h in cfg.get("authorized_hosts") or [host_of(base)]]
    if host_of(base) not in authorized or any(h in prod for h in authorized):
        sys.exit("STOP: authorized_hosts must include base_url and cannot include a production host.")
    if cfg.get("environment", "").strip().lower() in {"prod", "production", "live"}:
        sys.exit("STOP: environment is production. This agent tests QA environments only.")

    pw_cfg = ROOT / "playwright-mcp.json"
    if pw_cfg.exists():
        try:
            allowed = [o.lower().rstrip("/") for o in
                       json.loads(pw_cfg.read_text(encoding="utf-8")).get("network", {}).get("allowedOrigins", [])]
            if allowed and origin not in allowed:
                sys.exit(f"STOP: {origin} is not in network.allowedOrigins of qa/playwright-mcp.json. "
                         "Add it there (plus any API/SSO origins the app needs) and restart the MCP server.")
            if allowed:
                missing_qa = [h for h in authorized if not any(host_of(a) == h for a in allowed)]
                if missing_qa:
                    print("WARN authorized_hosts not in allowedOrigins (their pages will be blocked): " + ", ".join(missing_qa))
                miss = [h for h in (cfg.get("auth_hosts") or [])
                        if not any(host_of(a) == h.lower() for a in allowed)]
                if miss:
                    print("WARN auth_hosts not in allowedOrigins (login pages will be blocked): " + ", ".join(miss))
        except json.JSONDecodeError:
            sys.exit("qa/playwright-mcp.json is not valid JSON.")
    if not (ROOT / ".env.qa").exists():
        print("WARN qa/.env.qa not found - copy .env.qa.example and fill the test credentials.")

    RUNS.mkdir(exist_ok=True)
    run_id = dt.datetime.now().strftime("run-%Y%m%d-%H%M%S")
    d = RUNS / run_id
    (d / "defects").mkdir(parents=True)
    (d / "evidence").mkdir()
    led = {
        "run_id": run_id, "started": now(), "config": cfg,
        "pages": {}, "features": {}, "flow": [], "notes": [], "defect_seq": 0,
    }
    save_ledger(d, led)
    (d / "narrative.yaml").write_text(NARRATIVE_TEMPLATE, encoding="utf-8")
    CURRENT.write_text(run_id, encoding="utf-8")
    print(f"RUN {run_id} started. Evidence dir: qa/runs/{run_id}/evidence")
    print_brief(cfg)


def print_brief(cfg: dict) -> None:
    roles = cfg.get("roles") or []
    print(f"APP: {cfg.get('app_name','?')} | ENV: {cfg.get('environment','?')} | URL: {cfg.get('base_url')}")
    if cfg.get("purpose"):
        print(f"PURPOSE: {cfg['purpose']}")
    if cfg.get("primary_journey"):
        print(f"PRIMARY JOURNEY: {cfg['primary_journey']}")
    for r in roles:
        print(f"ROLE {r.get('name')}: login={r.get('login_path','/')} "
              f"user<-type '{r.get('username_secret')}' pass<-type '{r.get('password_secret')}'")
    print(f"NEVER TOUCH HOSTS: {', '.join(cfg.get('production_hosts') or []) or 'none listed'}")
    print(f"AUTHORIZED QA HOSTS: {', '.join(cfg.get('authorized_hosts') or [host_of(cfg.get('base_url',''))])}")
    print(f"AUTH HOSTS (login only): {', '.join(cfg.get('auth_hosts') or []) or 'none'} | "
          f"LOGIN MODE: {cfg.get('login_mode', 'auto')}")
    print(f"CREATE RECORDS: {'yes, prefix ' + str(cfg.get('test_record_prefix','QA-')) if cfg.get('allow_create_records') else 'NO'}")
    print(f"ASK BEFORE (label contains): {', '.join(cfg.get('approval_required_keywords') or [])}")
    for o in cfg.get("off_limits") or []:
        print(f"OFF-LIMITS: {o}")
    print(f"TIMEBOX: {cfg.get('timebox_minutes','?')} min | DEPTH: {cfg.get('depth','broad')} | "
          f"CHECKPOINT every ~{cfg.get('checkpoint_every_actions',40)} browser actions")


def cmd_brief(_a) -> None:
    print_brief(load_ledger(run_dir())["config"])


def cmd_page(a) -> None:
    d = run_dir(); led = load_ledger(d)
    p = led["pages"].setdefault(a.pid, {"id": a.pid, "status": "discovered", "notes": [], "first_seen": now()})
    for k in ("url", "title", "module", "role"):
        v = getattr(a, k)
        if v:
            p[k] = v
    st = norm_status(a.status)
    if st:
        p["status"] = st
    if a.note:
        p["notes"].append(a.note)
    p["updated"] = now()
    save_ledger(d, led)
    print(f"ok page {a.pid}={STATUSES[p['status']]}")


def cmd_feat(a) -> None:
    d = run_dir(); led = load_ledger(d)
    if a.pid not in led["pages"]:
        led["pages"][a.pid] = {"id": a.pid, "status": "discovered", "notes": [], "first_seen": now()}
    key = f"{a.pid}::{a.name}"
    f = led["features"].setdefault(key, {"page": a.pid, "name": a.name, "status": "discovered",
                                        "dims": [], "notes": []})
    st = norm_status(a.status)
    if st:
        if st == "explored" and not a.outcome and f.get("outcome") != "verified":
            sys.exit("Cannot mark a feature explored without --outcome verified. Complete and verify the productive action first.")
        f["status"] = st
    if a.dims:
        for dim in [x.strip().lower() for x in a.dims.split(",") if x.strip()]:
            if dim not in DIMS:
                sys.exit(f"Bad dim '{dim}'. Use: {', '.join(DIMS)}")
            if dim not in f["dims"]:
                f["dims"].append(dim)
    if a.note:
        f["notes"].append(a.note)
    if a.outcome:
        outcome = a.outcome.strip().lower()
        if outcome not in {"verified", "not-achieved", "unknown"}:
            sys.exit("Bad outcome. Use: verified, not-achieved, unknown")
        f["outcome"] = outcome
    save_ledger(d, led)
    print(f"ok feat {a.pid}/{a.name}={STATUSES[f['status']]} dims={','.join(f['dims']) or '-'}")


def cmd_flow(a) -> None:
    d = run_dir(); led = load_ledger(d)
    led["flow"].append({"n": len(led["flow"]) + 1, "from": a.frm, "action": a.action, "to": a.to,
                        "data": a.data, "result": a.result, "assert": a.asrt, "evidence": a.ev,
                        "at": now()})
    save_ledger(d, led)
    print(f"ok flow step {len(led['flow'])}")


def cmd_note(a) -> None:
    kinds = {"obs", "ambiguity", "blocker", "env", "activity"}
    if a.kind not in kinds:
        sys.exit(f"Bad kind. Use: {', '.join(sorted(kinds))}")
    d = run_dir(); led = load_ledger(d)
    led["notes"].append({"kind": a.kind, "text": a.text, "at": now()})
    save_ledger(d, led)
    print(f"ok note {a.kind}")


def cmd_defect_new(a) -> None:
    d = run_dir(); led = load_ledger(d)
    led["defect_seq"] += 1
    did = f"D-{led['defect_seq']:03d}"
    env = f"{led['config'].get('environment','QA')} {led['config'].get('base_url','')}"
    path = d / "defects" / f"{did}.yaml"
    path.write_text(DEFECT_TEMPLATE.format(id=did, title=a.title.replace('"', "'"), env=env), encoding="utf-8")
    save_ledger(d, led)
    rel = path.relative_to(ROOT.parent).as_posix()
    print(f"{did} -> fill {rel} (screenshot: qa/runs/{led['run_id']}/evidence/{did}.png)")


def load_defects(d: Path) -> list[dict]:
    out = []
    for p in sorted((d / "defects").glob("D-*.yaml")):
        try:
            x = load_yaml(p)
        except yaml.YAMLError as e:
            x = {"id": p.stem, "title": f"(unparseable YAML: {e})", "kind": "suspected"}
        x["_file"] = p.name
        out.append(x)
    return out


def coverage(led: dict) -> dict:
    pages = [p for p in led["pages"].values() if p["status"] != "na"]
    feats = [f for f in led["features"].values() if f["status"] != "na"]
    modules = sorted({p.get("module") or "(unassigned)" for p in led["pages"].values()})
    visited = [p for p in pages if p["status"] in {"visited", "partial", "explored"}]
    fe = [f for f in feats if f["status"] == "explored"]
    fp = [f for f in feats if f["status"] == "partial"]
    fb = [f for f in feats if f["status"] == "blocked"]
    pb = [p for p in pages if p["status"] == "blocked"]
    fu = [f for f in feats if f["status"] in {"discovered", "visited"}]
    dims = {k: sum(1 for f in feats if k in f["dims"]) for k in DIMS}
    verified = [f for f in feats if f.get("outcome") == "verified"]
    return dict(pages=pages, feats=feats, modules=modules, visited=visited, fe=fe, fp=fp,
                fb=fb, pb=pb, fu=fu, dims=dims, verified=verified)


def pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.0f}% ({n}/{total})" if total else "n/a (0 identified)"


def cmd_status(_a) -> None:
    d = run_dir(); led = load_ledger(d); c = coverage(led); defs = load_defects(d)
    cfg = led["config"]
    touch(led); save_ledger(d, led)  # status checks count as activity too
    mins = active_min(led)
    tb = int(cfg.get("timebox_minutes") or 0)
    if not tb:
       tbs = "no timebox"
    elif not c["fe"] and not c["fp"]:
       tbs = f"timebox {tb} min - NOT STARTED: no feature tested yet, keep testing"
    elif mins >= tb:
       tbs = f"TIMEBOX USED UP ({tb} min) - finish current item, then report"
    else:
       tbs = f"{tb - mins} min left of {tb}"
    print(f"RUN {led['run_id']} | active testing {mins} min | {tbs}")
    print(f"modules={len(c['modules'])} pages={len(c['pages'])} features={len(c['feats'])} "
          f"(denominators = items discovered so far; undiscovered scope unknown)")
    print(f"pages visited {pct(len(c['visited']), len(c['pages']))} | features explored "
          f"{pct(len(c['fe']), len(c['feats']))}, partial {len(c['fp'])}, blocked {len(c['fb'])}, untouched {len(c['fu'])}")
    print("dims: " + " ".join(f"{k}={v}/{len(c['feats'])}" for k, v in c["dims"].items()))
    print(f"E2E flow steps: {len(led['flow'])} | verified feature outcomes: {len(c['verified'])}/{len(c['feats'])}")
    open_defs = [x for x in defs if str(x.get("status", "Open")).lower().startswith("open")]
    by = {s: sum(1 for x in open_defs if x.get("severity") == s) for s in SEVERITIES}
    print("open defects: " + " ".join(f"{s[0]}={n}" for s, n in by.items()) +
          f" | total files {len(defs)}")
    # Productivity-first continuation: deepen unfinished work before discovering more pages.
    targets = sorted(c["fp"], key=lambda f: len(f["dims"])) + c["fu"]
    if targets:
        print("NEXT: " + "; ".join(f"{f['page']}/{f['name']}[{','.join(f['dims']) or '-'}]" for f in targets[:8]))
    unvisited = [p["id"] for p in c["pages"] if p["status"] == "discovered"]
    if unvisited:
        print("UNVISITED PAGES: " + ", ".join(unvisited[:12]) + (" ..." if len(unvisited) > 12 else ""))
    blockers = [n["text"] for n in led["notes"] if n["kind"] == "blocker"]
    if blockers:
        print("BLOCKERS: " + " | ".join(blockers[-3:]))
    later = [n["text"] for n in led["notes"] if n["text"].startswith("VERIFY-LATER")]
    done = {n["text"].split("DONE ", 1)[1] for n in led["notes"] if n["text"].startswith("VERIFY-DONE ")}
    later = [t for t in later if t not in done]
    if later:
        print("VERIFY LATER (check, then note obs \"VERIFY-DONE <same text>\"): " + " | ".join(later[-10:]))


# ------------------------------------------------------------------------- report
def md_esc(s) -> str:
    s = "" if s is None else str(s)
    return s.replace("|", "\\|").replace("\n", "<br>")


def nz(v, fallback="Not recorded") -> str:
    v = "" if v is None else str(v).strip()
    return v if v else f"_{fallback}_"


def build_report(d: Path) -> tuple[str, list[str]]:
    led = load_ledger(d); cfg = led["config"]; c = coverage(led); defs = load_defects(d)
    narr_p = d / "narrative.yaml"
    narr = load_yaml(narr_p) if narr_p.exists() else {}
    warnings: list[str] = []

    open_defs = [x for x in defs if str(x.get("status", "Open")).lower().startswith("open")]
    conf_crit = [x for x in open_defs if x.get("kind") == "confirmed" and x.get("severity") == "Critical"]
    conf_high = [x for x in open_defs if x.get("kind") == "confirmed" and x.get("severity") == "High"]

    verdict = str(narr.get("verdict") or "").strip().upper()
    if verdict not in VERDICTS:
        verdict = "NOT READY" if conf_crit else "CONDITIONAL"
        warnings.append(f"narrative.yaml verdict missing/invalid -> derived '{verdict}' from data.")
    if conf_crit and verdict != "NOT READY":
        warnings.append(f"Verdict forced to NOT READY: {len(conf_crit)} open confirmed Critical defect(s).")
        verdict = "NOT READY"
    if verdict == "READY FOR REVIEW" and (conf_high or c["fb"] or c["pb"] or c["fu"]):
        warnings.append("Verdict downgraded to CONDITIONAL: open High defects, blocked or untouched items remain.")
        verdict = "CONDITIONAL"

    if not c["fe"] and not c["fp"]:
        warnings.append("No feature was explored or partially explored - this report reflects discovery only, "
                        "not adhoc testing. Continue the run (/qa-continue) before reporting.")
    if c["fp"]:
        warnings.append(f"{len(c['fp'])} partial feature(s) remain; partial is unfinished, not completed coverage.")
    if c["fe"] and not led["flow"]:
        warnings.append("Features are marked explored but no end-to-end transition flow was recorded.")

    for x in defs:
        if x.get("status", "").lower().startswith("fixed") and "retest" not in str(x.get("reproducibility", "")).lower():
            warnings.append(f"{x.get('id')}: marked fixed - confirm a fix was deployed AND retested.")
        if x.get("kind") == "confirmed" and not x.get("evidence"):
            warnings.append(f"{x.get('id')}: confirmed defect without evidence listed.")

    ended = now()
    L: list[str] = []
    w = L.append
    w(f"# QA Adhoc Testing Report — {cfg.get('app_name','Application')}")
    w("")
    w(f"**Run:** {led['run_id']} · **Environment:** {cfg.get('environment','QA')} ({cfg.get('base_url')}) · "
      f"**Period:** {str(narr.get('testing_period') or '').strip() or (led['started'][:16].replace('T', ' ') + ' → ' + ended[:16].replace('T', ' '))}")
    w("")
    w(f"> **Final QA recommendation: {verdict}** — {nz(narr.get('verdict_reason'))}")
    w(">")
    w("> This is based only on the tested scope below. It is not a guarantee of defect-free software "
      "and not an automatic release authorization.")
    w("")

    # A
    w("## A. Executive summary")
    w(f"- **Scope:** {nz(narr.get('scope'))}")
    w(f"- **Exclusions:** {nz(narr.get('exclusions'))}")
    w("- **Methods:** exploratory adhoc testing (buddy, pair, monkey) via browser UI automation "
      "(Playwright MCP accessibility snapshots, console and network observation where used).")
    w(f"- **Overall outcome:** {nz(narr.get('overall_outcome'))}")
    w(f"- **Highest-risk findings:** {nz(narr.get('highest_risk_findings'))}")
    w(f"- **Major blockers:** {nz(narr.get('major_blockers'))}")
    w(f"- **Sign-off recommendation:** {verdict}")
    w("")

    # B
    w("## B. Application discovery")
    w(f"Modules discovered ({len(c['modules'])}): {', '.join(c['modules']) or '—'}")
    w("")
    w("| Page | Module | URL | Title | Status | Role | Notes |")
    w("|---|---|---|---|---|---|---|")
    for p in led["pages"].values():
        w(f"| {md_esc(p['id'])} | {md_esc(p.get('module',''))} | {md_esc(p.get('url',''))} | "
          f"{md_esc(p.get('title',''))} | {STATUSES[p['status']]} | {md_esc(p.get('role',''))} | "
          f"{md_esc('; '.join(p['notes']))} |")
    w("")
    w(f"- **Major workflows:** {nz(narr.get('major_workflows'))}")
    w(f"- **Roles examined:** {nz(narr.get('roles_examined'))}")
    w(f"- **Features & integrations:** {nz(narr.get('integrations_identified'))}")
    w(f"- **Unknown / inaccessible:** {nz(narr.get('unknown_or_inaccessible'))}")
    w("")

    # C
    w("## C. End-to-end positive flow")
    w(f"**Workflow:** {nz(narr.get('e2e_flow_name'))}")
    w("")
    if led["flow"]:
        w("| # | From | Action | To | Data | Result | Assertion | Evidence |")
        w("|---|---|---|---|---|---|---|---|")
        for s in led["flow"]:
            w(f"| {s['n']} | {md_esc(s['from'])} | {md_esc(s['action'])} | {md_esc(s['to'])} | "
              f"{md_esc(s.get('data'))} | {md_esc(s.get('result'))} | {md_esc(s.get('assert'))} | "
              f"{md_esc(s.get('evidence'))} |")
    else:
        w("_No end-to-end flow steps were recorded._")
        warnings.append("No E2E positive flow recorded (Phase 2).")
    w("")
    w(f"- **Final outcome:** {nz(narr.get('e2e_final_outcome'))}")
    w(f"- **Failures / uncertainties:** {nz(narr.get('e2e_uncertainties'))}")
    w("")

    # D
    w("## D. Exploratory testing summary")
    for k, label in [("buddy_testing", "Buddy testing"), ("pair_testing", "Pair testing"),
                     ("monkey_testing", "Monkey testing"), ("positive_negative", "Positive & negative"),
                     ("boundary_testing", "Boundary"), ("navigation_state", "Navigation & state"),
                     ("data_integrity", "Data integrity"), ("auth_checks", "Authentication & authorization"),
                     ("other_techniques", "Other techniques")]:
        w(f"- **{label}:** {nz(narr.get(k), 'Not performed / not recorded')}")
    acts = [n for n in led["notes"] if n["kind"] in {"activity", "obs"}]
    if acts:
        w("")
        w("<details><summary>Activity & observation log</summary>")
        w("")
        for n in acts:
            w(f"- `{n['at'][11:19]}` [{n['kind']}] {n['text']}")
        w("")
        w("</details>")
    w("")

    # E
    w("## E. Coverage dashboard")
    w("Denominators are the items **identified during this run**. Undiscovered scope is unknown, so "
      "these percentages describe coverage of what was found, not of the whole application.")
    w("")
    w("| Measure | Value | Definition |")
    w("|---|---|---|")
    w(f"| Modules identified | {len(c['modules'])} | distinct module names on recorded pages |")
    w(f"| Pages identified (in scope) | {len(c['pages'])} | pages not marked Not Applicable |")
    w(f"| Page visitation | {pct(len(c['visited']), len(c['pages']))} | Visited, Partially Explored or Explored ÷ in-scope pages |")
    w(f"| Features identified (in scope) | {len(c['feats'])} | features not marked Not Applicable |")
    w(f"| Feature exploration | {pct(len(c['fe']), len(c['feats']))} | Explored (meaningfully challenged) ÷ in-scope features |")
    w(f"| Partially explored | {len(c['fp'])} | |")
    w(f"| Blocked | features {len(c['fb'])}, pages {len(c['pb'])} | |")
    w(f"| Untouched features | {len(c['fu'])} | Discovered/Visited only |")
    for k, label in DIMS.items():
        w(f"| {label} coverage | {pct(c['dims'][k], len(c['feats']))} | features where this dimension was exercised ÷ in-scope features |")
    w("")
    w("### Feature ledger")
    w("| Page | Feature | Status | Dimensions | Notes |")
    w("|---|---|---|---|---|")
    for f in led["features"].values():
        w(f"| {md_esc(f['page'])} | {md_esc(f['name'])} | {STATUSES[f['status']]} | "
          f"{', '.join(DIMS[x] for x in f['dims']) or '—'} | {md_esc('; '.join(f['notes']))} |")
    gaps = c["fu"] + c["fp"] + c["fb"]
    w("")
    w("**Remaining coverage gaps:** " + ("; ".join(
        f"{f['page']}/{f['name']} ({STATUSES[f['status']]})" for f in gaps) or "none recorded"))
    w("")

    # F
    w("## F. Defect summary")
    w("| Kind | Critical | High | Medium | Low | Total |")
    w("|---|---|---|---|---|---|")
    for k in KINDS:
        row = [sum(1 for x in defs if x.get("kind") == k and x.get("severity") == s) for s in SEVERITIES]
        w(f"| {k.title()} | " + " | ".join(map(str, row)) + f" | {sum(row)} |")
    st_counts: dict[str, int] = {}
    for x in defs:
        st_counts[str(x.get("status", "Open"))] = st_counts.get(str(x.get("status", "Open")), 0) + 1
    w("")
    w("By status: " + (", ".join(f"{k}: {v}" for k, v in st_counts.items()) or "no defects recorded"))
    w("")
    for k, heading in [("confirmed", "Confirmed defects"), ("suspected", "Suspected / unconfirmed issues"),
                       ("environment", "Environment issues"), ("ambiguity", "Requirement ambiguities")]:
        group = [x for x in defs if x.get("kind") == k]
        w(f"### {heading} ({len(group)})")
        if not group:
            w("_None._")
        for x in sorted(group, key=lambda y: SEVERITIES.index(y.get("severity")) if y.get("severity") in SEVERITIES else 9):
            w(f"#### {x.get('id')} — {x.get('title')}")
            w(f"- **Severity / priority:** {x.get('severity')} / {x.get('priority')} — {nz(x.get('severity_rationale'))}")
            w(f"- **Status:** {x.get('status')} · **Reproducibility:** {nz(x.get('reproducibility'))}")
            w(f"- **Module / page:** {nz(x.get('module'))} / {nz(x.get('page'))}")
            w(f"- **Environment / browser:** {nz(x.get('environment'))} / {nz(x.get('browser'))}")
            w(f"- **URL / path:** {nz(x.get('url'))} — {nz(x.get('navigation_path'))}")
            w(f"- **Preconditions / role:** {nz(x.get('preconditions'))} / {nz(x.get('role'))}")
            steps = [s for s in (x.get("steps") or []) if str(s).strip()]
            w("- **Steps to reproduce:**")
            for i, s in enumerate(steps, 1):
                w(f"  {i}. {s}")
            if not steps:
                w("  _Not recorded_")
            w(f"- **Test data:** {nz(x.get('test_data'))}")
            w(f"- **Expected:** {nz(x.get('expected'))} _(source: {nz(x.get('expected_source'), 'unstated')})_")
            w(f"- **Actual:** {nz(x.get('actual'))}")
            ev = x.get("evidence") or []
            w(f"- **Evidence:** {', '.join(map(str, ev)) if ev else '_none attached_'}")
            w(f"- **Related:** {nz(x.get('related'))}")
            w(f"- **Business impact:** {nz(x.get('business_impact'))}")
            w(f"- **Recommendation:** {nz(x.get('recommendation'))}")
            w("")
        w("")
    other = [n for n in led["notes"] if n["kind"] in {"ambiguity", "env", "blocker"}]
    if other:
        w("### Logged notes (ambiguities, environment, blockers)")
        for n in other:
            w(f"- [{n['kind']}] {n['text']}")
        w("")

    # G
    w("## G. Risk assessment")
    for k, label in [("risk_business", "Critical business risks"), ("risk_data", "Data integrity risks"),
                     ("risk_authorization", "Authorization risks"), ("risk_workflow_integration", "Workflow & integration risks"),
                     ("risk_untested_areas", "High-risk untested areas"), ("risk_environment", "Environment-limitation risks")]:
        w(f"- **{label}:** {nz(narr.get(k))}")
    w("")

    # H
    w("## H. Recommended actions")
    for k, label in [("action_immediate", "Immediate corrective actions"), ("action_investigate", "Investigation areas"),
                     ("action_retest", "Required retesting"), ("action_remaining_exploration", "Remaining exploratory work"),
                     ("action_blockers", "Environment / access blockers"), ("action_next_priorities", "Next testing priorities")]:
        w(f"- **{label}:** {nz(narr.get(k))}")
    w("")

    # I
    w("## I. Final QA recommendation")
    w(f"**{verdict}** — {nz(narr.get('verdict_reason'))}")
    w("")
    w(f"- Tested scope: {nz(narr.get('scope'))}")
    w(f"- Outstanding open defects: {len(open_defs)} "
      f"({', '.join(f'{s}: {sum(1 for x in open_defs if x.get('severity') == s)}' for s in SEVERITIES)})")
    w("- Limitations: browser-UI exploratory testing only; no database or server-log access; API behavior "
      "observed only through browser network traffic where checked; no load/stress testing; coverage "
      "percentages are relative to discovered scope.")
    if warnings:
        w("")
        w("### Report integrity warnings")
        for x in warnings:
            w(f"- {x}")
    w("")
    return "\n".join(L), warnings


def md_to_html(md_text: str, title: str) -> str:
    # Report text includes content captured from the app under test: treat it all as untrusted.
    # 1) escape every HTML tag before Markdown conversion, 2) restore only the few tags the
    # report itself emits, 3) drop javascript:/data:/vbscript: links, 4) a CSP blocks all scripts.
    try:
        import markdown  # optional
        body = markdown.markdown(html.escape(md_text, quote=False), extensions=["tables"])
        for dbl, single in (("&amp;lt;", "&lt;"), ("&amp;gt;", "&gt;"), ("&amp;amp;", "&amp;")):
            body = body.replace(dbl, single)  # undo double-escaping inside code spans
        for safe in ("br", "details", "/details", "summary", "/summary"):
            body = body.replace(f"&lt;{safe}&gt;", f"<{safe}>")
        body = re.sub(r'(?i)\s(href|src)\s*=\s*"\s*(javascript|data|vbscript):[^"]*"', ' \\1="#"', body)
    except ImportError:
        body = "<pre>" + html.escape(md_text) + "</pre>"
    css = """
:root{--bg:#fff;--fg:#1d1f23;--mut:#5b616b;--line:#e3e5e8;--acc:#2f5bd3;--bad:#b42318;--warn:#b54708;--ok:#067647}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e6e7e9;--mut:#9aa0a8;--line:#2c3036;--acc:#7c9cff}}
body{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:26px}h2{margin-top:36px;border-bottom:1px solid var(--line);padding-bottom:6px}
table{border-collapse:collapse;width:100%;display:block;overflow-x:auto;font-size:13px;margin:10px 0}
th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{background:color-mix(in srgb,var(--line) 50%,transparent)}
blockquote{margin:12px 0;padding:10px 14px;border-left:4px solid var(--acc);background:color-mix(in srgb,var(--acc) 8%,transparent)}
code{font-size:12px}h4{margin-bottom:4px}
"""
    csp = ("<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
          "style-src 'unsafe-inline'; img-src 'self' data:\">")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'>{csp}<meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
            f"<style>{css}</style></head><body>{body}</body></html>")


def cmd_report(_a) -> None:
    d = run_dir()
    md_text, warnings = build_report(d)
    (d / "report.md").write_text(md_text, encoding="utf-8")
    cfg = load_ledger(d)["config"]
    (d / "report.html").write_text(md_to_html(md_text, f"QA Report {cfg.get('app_name','')}"), encoding="utf-8")
    try:
        sys.path.insert(0, str(ROOT))
        import report_html
        report_html.build(d)
    except Exception as ex:
        print(f"WARN rich HTML report failed ({ex}); plain report.html kept")
    rel = d.relative_to(ROOT.parent).as_posix()
    print(f"ok report -> {rel}/report.md and report.html")
    for x in warnings:
        print(f"WARN {x}")


# --------------------------------------------------------------------------- main
def main(argv=None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(prog="ledger.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("init").set_defaults(fn=cmd_init)
    sp.add_parser("brief").set_defaults(fn=cmd_brief)

    p = sp.add_parser("page"); p.add_argument("pid")
    for k in ("url", "title", "module", "status", "role", "note"):
        p.add_argument(f"--{k}")
    p.set_defaults(fn=cmd_page)

    p = sp.add_parser("feat"); p.add_argument("pid"); p.add_argument("name")
    p.add_argument("--status"); p.add_argument("--dims"); p.add_argument("--note")
    p.add_argument("--outcome", choices=("verified", "not-achieved", "unknown"))
    p.set_defaults(fn=cmd_feat)

    p = sp.add_parser("flow"); p.add_argument("action")
    p.add_argument("--from", dest="frm", required=True); p.add_argument("--to", required=True)
    p.add_argument("--data"); p.add_argument("--result"); p.add_argument("--assert", dest="asrt")
    p.add_argument("--ev")
    p.set_defaults(fn=cmd_flow)

    p = sp.add_parser("note"); p.add_argument("kind"); p.add_argument("text")
    p.set_defaults(fn=cmd_note)

    p = sp.add_parser("defect-new"); p.add_argument("title")
    p.set_defaults(fn=cmd_defect_new)

    sp.add_parser("status").set_defaults(fn=cmd_status)
    sp.add_parser("report").set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
