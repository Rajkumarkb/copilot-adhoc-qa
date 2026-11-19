#!/usr/bin/env python3
"""
CI helper for the Adhoc QA agent (GitHub Actions). Never prints secret values.

  python3 qa/ci/ci_state.py prepare    write CI browser/MCP config + secrets file into $RUNNER_TEMP,
                                       set framework_path ".", login_mode auto, CI timebox
  python3 qa/ci/ci_state.py state      CONTINUE | DONE | STOP  <reason>   (decides the session loop)
  python3 qa/ci/ci_state.py summary    Slack message JSON for the current run
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

QA = Path(__file__).resolve().parent.parent
TMP = Path(os.environ.get("RUNNER_TEMP") or "/tmp")
CONFIG = QA / "qa.config.yaml"
PLAN_PAGES = {"journeys", "changes", "cross"}
DONE_STATUSES = {"explored", "blocked", "na"}


def set_key(text: str, key: str, value: str) -> str:
    rx = re.compile(rf"^({re.escape(key)}\s*:\s*)[^#\n]*", re.M)
    return rx.sub(lambda m: m.group(1) + value + "  ", text, count=1) if rx.search(text) else text + f"\n{key}: {value}\n"


def prepare() -> None:
    cfg = CONFIG.read_text(encoding="utf-8")
    # 1. secrets file outside the workspace (agent never needs to read it; Playwright MCP masks values)
    names = list(dict.fromkeys(re.findall(
        r'^\s*(?:-\s*)?(?:username_secret|password_secret)\s*:\s*["\']?([A-Za-z_]\w*)', cfg, re.M)))
    missing = [n for n in names if not os.environ.get(n)]
    if not names or missing:
        sys.exit(f"Missing CI secrets for login: {', '.join(missing or ['(no roles in qa.config.yaml)'])}. "
                 "Map them in the workflow's 'env:' from your repository secrets.")
    env_file = TMP / "qa.env"
    env_file.write_text("".join(f"{n}={os.environ[n]}\n" for n in names), encoding="utf-8")
    os.chmod(env_file, 0o600)
    # 2. CI browser config: headless, real Chrome, profile kept between sessions of this job
    pw = json.loads((QA / "playwright-mcp.json").read_text(encoding="utf-8"))
    b = pw.setdefault("browser", {})
    b.update({"isolated": False, "userDataDir": str(TMP / "qa-browser-profile")})
    b.setdefault("launchOptions", {}).update({"headless": True, "chromiumSandbox": False})
    pw["outputDir"] = str(QA / "runs" / "_mcp-output")
    (TMP / "playwright-mcp.ci.json").write_text(json.dumps(pw, indent=1), encoding="utf-8")
    ver = os.environ.get("QA_PLAYWRIGHT_MCP_VERSION", "0.0.83")
    mcp = {"mcpServers": {"playwright": {
        "type": "local", "command": "npx", "tools": ["*"],
        "args": ["-y", f"@playwright/mcp@{ver}", "--config", str(TMP / "playwright-mcp.ci.json"),
                 "--secrets", str(env_file)]}}}
    (TMP / "mcp.json").write_text(json.dumps(mcp, indent=1), encoding="utf-8")
    # 3. CI overrides in the (throwaway) checkout's config
    cfg = set_key(cfg, "framework_path", '"."')
    cfg = set_key(cfg, "login_mode", '"auto"')
    cfg = set_key(cfg, "timebox_minutes", os.environ.get("QA_TIMEBOX", "300"))
    CONFIG.write_text(cfg, encoding="utf-8")
    print(f"ok prepared CI config | login secrets: {', '.join(names)} | timebox {os.environ.get('QA_TIMEBOX', '300')} min")


def ledger():
    cur = QA / "runs" / "CURRENT"
    if not cur.exists():
        return None, None
    d = QA / "runs" / cur.read_text(encoding="utf-8").strip()
    return d, json.loads((d / "ledger.json").read_text(encoding="utf-8"))


def state() -> None:
    d, led = ledger()
    if not led:
        print("STOP no active run"); return
    notes = led.get("notes", [])
    login = [n["text"] for n in notes if n["kind"] == "blocker" and n["text"].upper().startswith("LOGIN-FAILED")]
    if login:
        print(f"STOP {login[-1]}"); return
    plan = [f for f in led["features"].values() if f["page"] in PLAN_PAGES or f["name"].startswith("Module:")]
    if not plan:
        print("STOP no plan was registered in the ledger"); return
    tb = int(led["config"].get("timebox_minutes") or 0)
    used = int(led.get("active_sec", 0) // 60)
    left = [f for f in plan if f["status"] not in DONE_STATUSES]
    # stall guard: the ledger must change between sessions
    fp_file = TMP / "qa-ledger-fingerprint"
    outcomes = sum(f.get("outcome") == "verified" for f in plan)
    dims_done = sum(len(f.get("dims", [])) for f in plan)
    fp = f"{outcomes}|{dims_done}|{sum(f['status'] in DONE_STATUSES for f in plan)}|{len(led['flow'])}"
    stalls = 0
    if fp_file.exists():
        old, n = fp_file.read_text().split("\n")[:2]
        stalls = int(n) + 1 if old == fp else 0
    fp_file.write_text(f"{fp}\n{stalls}")
    if stalls >= 2:
        print("STOP no progress in the last 2 sessions"); return
    if tb and used >= tb:
        print(f"DONE timebox used ({used}/{tb} min), {len(left)} plan items left"); return
    if not left:
        print(f"DONE all {len(plan)} plan items covered ({used} min)"); return
    print(f"CONTINUE {len(left)}/{len(plan)} plan items left, {used}/{tb or '-'} min")


def summary() -> None:
    d, led = ledger()
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    sha = (os.environ.get("GITHUB_SHA") or "")[:8]
    if not led:
        text = f":warning: Adhoc QA could not start (commit {sha}). <{run_url}|Workflow run>"
    else:
        verdict = "NO REPORT"
        rep = d / "report.md"
        if rep.exists():
            m = re.search(r"Final QA recommendation: ([A-Z ]+)\*\*", rep.read_text(encoding="utf-8"))
            verdict = m.group(1).strip() if m else verdict
        sev = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        confirmed = 0
        try:
            import yaml
            for p in (d / "defects").glob("D-*.yaml"):
                x = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if str(x.get("status", "Open")).lower().startswith("open") and x.get("severity") in sev:
                    sev[x["severity"]] += 1
                    confirmed += x.get("kind") == "confirmed"
        except Exception:
            pass
        plan = [f for f in led["features"].values() if f["page"] in PLAN_PAGES or f["name"].startswith("Module:")]
        covered = sum(f["status"] in DONE_STATUSES for f in plan)
        login = next((n["text"] for n in led["notes"] if n["text"].upper().startswith("LOGIN-FAILED")), "")
        icon = {"NOT READY": ":red_circle:", "CONDITIONAL": ":large_yellow_circle:",
                "READY FOR REVIEW": ":large_green_circle:"}.get(verdict, ":white_circle:")
        text = (f"{icon} *Adhoc QA — {led['config'].get('app_name', 'App')}* · commit `{sha}` "
                f"by {os.environ.get('GITHUB_ACTOR', '?')}\n"
                f"*Verdict:* {verdict} · *Open defects:* " + ", ".join(f"{k} {v}" for k, v in sev.items())
                + f" ({confirmed} confirmed)\n"
                f"*Plan covered:* {covered}/{len(plan)} journeys/modules · "
                f"{int(led.get('active_sec', 0) // 60)} min active testing"
                + (f"\n:warning: {login}" if login else "")
                + f"\n<{run_url}|Report & evidence (workflow artifacts)>")
    print(json.dumps({"text": text}))


if __name__ == "__main__":
    {"prepare": prepare, "state": state, "summary": summary}.get(
        sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
