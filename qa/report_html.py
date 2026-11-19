#!/usr/bin/env python3
"""
Rich, self-contained HTML report for an Adhoc QA run (no external libraries or CDNs).

  python3 qa/report_html.py [run-folder]      (default: current run)
Called automatically by `python3 qa/ledger.py report` when present. Reads ledger.json, defects/*.yaml,
narrative.yaml, report.md (for the final verdict), coverage-summary.json and evidence/*.png.
All text from the app under test is HTML-escaped; scripts run only with a per-build CSP nonce.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import secrets
import sys
from collections import Counter, defaultdict
from pathlib import Path

QA = Path(__file__).resolve().parent
SEV = ["Critical", "High", "Medium", "Low"]
DONE = {"explored", "partial", "blocked", "na"}
STATUS_LABEL = {"discovered": "Discovered", "visited": "Visited", "partial": "Partial",
                "explored": "Explored", "blocked": "Blocked", "na": "N/A"}
DIMS = {"pos": "Positive", "neg": "Negative", "bnd": "Boundary", "nav": "Navigation/state",
        "data": "Data integrity", "role": "Roles", "ui": "UI"}
PLAN_PAGES = {"journeys", "changes", "cross"}


def e(s) -> str:
    return html.escape("" if s is None else str(s), quote=True)


def load_yaml(p: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def pct(a: int, b: int) -> int:
    return round(100 * a / b) if b else 0


def fmt_time(iso: str | None) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%d %b %Y %H:%M")
    except Exception:
        return e(iso or "")


def bar(parts: list[tuple[str, int]], total: int) -> str:
    if not total:
        return '<div class="bar empty"></div>'
    segs = "".join(f'<span class="seg s-{k}" style="width:{100 * v / total:.2f}%" title="{STATUS_LABEL.get(k, k)}: {v}"></span>'
                   for k, v in parts if v)
    return f'<div class="bar">{segs}</div>'


def chip(text: str, cls: str) -> str:
    return f'<span class="chip {cls}">{e(text)}</span>'


def build(run_dir: Path | None = None) -> Path:
    if run_dir is None:
        run_dir = QA / "runs" / (QA / "runs" / "CURRENT").read_text(encoding="utf-8").strip()
    d = Path(run_dir)
    led = json.loads((d / "ledger.json").read_text(encoding="utf-8"))
    cfg = led.get("config", {})
    narr = load_yaml(d / "narrative.yaml") if (d / "narrative.yaml").exists() else {}
    defects = []
    for p in sorted((d / "defects").glob("D-*.yaml")):
        x = load_yaml(p)
        x.setdefault("id", p.stem)
        defects.append(x)
    cov = json.loads((d / "coverage-summary.json").read_text()) if (d / "coverage-summary.json").exists() else None

    verdict = str(narr.get("verdict") or "").upper().strip()
    rep = d / "report.md"
    if rep.exists():
        m = re.search(r"Final QA recommendation: ([A-Z ]+)\*\*", rep.read_text(encoding="utf-8"))
        verdict = m.group(1).strip() if m else verdict
    verdict = verdict or "CONDITIONAL"
    vclass = {"NOT READY": "bad", "CONDITIONAL": "warn", "READY FOR REVIEW": "ok"}.get(verdict, "warn")

    pages = {k: v for k, v in led.get("pages", {}).items() if k not in PLAN_PAGES}
    feats = list(led.get("features", {}).values())
    notes = led.get("notes", [])
    flow = led.get("flow", [])
    inscope = [f for f in feats if f.get("status") != "na"]
    st = Counter(f.get("status") for f in inscope)
    pg_in = [p for p in pages.values() if p.get("status") != "na"]
    pg_vis = sum(p.get("status") in {"visited", "partial", "explored"} for p in pg_in)
    plan = [f for f in feats if f.get("page") in PLAN_PAGES or str(f.get("name", "")).startswith("Module:")]
    verified = sum(1 for f in feats if str(f.get("outcome", "")).lower() == "verified")
    open_d = [x for x in defects if str(x.get("status", "Open")).lower().startswith("open")]
    sev_open = Counter(x.get("severity") for x in open_d)
    blockers = [n for n in notes if n.get("kind") == "blocker"]
    mins = int(led.get("active_sec", 0) // 60)
    tb = cfg.get("timebox_minutes")

    # module rollup
    mod_of = {pid: (p.get("module") or "Unassigned") for pid, p in pages.items()}
    mods: dict[str, Counter] = defaultdict(Counter)
    mod_pages: dict[str, list] = defaultdict(list)
    for pid, p in pages.items():
        mod_pages[mod_of[pid]].append(p)
    for f in inscope:
        if f.get("page") in PLAN_PAGES:
            continue
        mods[mod_of.get(f.get("page"), f.get("page") or "Unassigned")][f.get("status", "discovered")] += 1

    nonce = secrets.token_urlsafe(16)
    H: list[str] = []
    w = H.append

    # ---------- header + verdict
    title = f"QA Report · {cfg.get('app_name', 'App')}"
    w(f'<header class="top"><div><div class="eyebrow">Adhoc QA testing report</div><h1>{e(cfg.get("app_name", "Application"))}</h1>'
      f'<div class="meta">{e(cfg.get("environment", "QA"))} · <a href="{e(cfg.get("base_url", ""))}">{e(cfg.get("base_url", ""))}</a> · '
      f'run <code>{e(led.get("run_id"))}</code> · started {fmt_time(led.get("started"))} · generated {dt.datetime.now().strftime("%d %b %Y %H:%M")}</div></div></header>')
    w(f'<section class="verdict {vclass}"><div class="v-label">Final QA recommendation</div><div class="v-value">{e(verdict)}</div>'
      f'<p>{e(narr.get("verdict_reason") or "")}</p>'
      '<p class="fine">Based only on the tested scope below. Not a guarantee of defect-free software or an automatic release authorization.</p></section>')

    # ---------- KPI tiles
    def tile(label, value, sub="", cls=""):
        return f'<div class="tile {cls}"><div class="t-label">{e(label)}</div><div class="t-value">{value}</div><div class="t-sub">{sub}</div></div>'
    sev_sub = " · ".join(f'<span class="sev-dot {s.lower()}"></span>{s[0]} {sev_open.get(s, 0)}' for s in SEV)
    w('<section class="tiles">')
    w(tile("Open defects", len(open_d), sev_sub, "bad" if sev_open.get("Critical") else ""))
    w(tile("Features explored", f'{pct(st["explored"], len(inscope))}%', f'{st["explored"]} of {len(inscope)} · {st["partial"]} partial · {st["blocked"]} blocked'))
    w(tile("Pages visited", f'{pct(pg_vis, len(pg_in))}%', f'{pg_vis} of {len(pg_in)} discovered pages'))
    w(tile("Plan covered", f'{sum(f.get("status") in DONE for f in plan)}/{len(plan)}', "journeys, modules and change items"))
    w(tile("Verified outcomes", verified, "flows that reached and confirmed their end state"))
    w(tile("Active testing", f'{mins}<small> min</small>', f'of {tb} min timebox' if tb else ""))
    if cov:
        w(tile("UI automation coverage", f'{pct(cov["with_locator"], cov["controls"])}%',
               f'{cov["with_locator"]} of {cov["controls"]} on-screen controls have a framework locator'))
    w(tile("Blockers", len(blockers), "see Blockers below", "warn" if blockers else ""))
    w('</section>')

    # ---------- executive summary
    rows = [("Scope", "scope"), ("Exclusions", "exclusions"), ("Overall outcome", "overall_outcome"),
            ("Highest-risk findings", "highest_risk_findings"), ("Major blockers", "major_blockers")]
    if any(narr.get(k) for _, k in rows):
        w('<section class="card"><h2>Executive summary</h2><dl class="kv">')
        for lbl, k in rows:
            if narr.get(k):
                w(f'<dt>{lbl}</dt><dd>{e(narr[k])}</dd>')
        w('</dl></section>')

    # ---------- journeys / plan
    if plan:
        w('<section class="card"><h2>Business journeys and plan items</h2><table><thead><tr><th>Item</th><th>Status</th><th>Outcome</th><th>Covered dimensions</th><th>Notes</th></tr></thead><tbody>')
        for f in sorted(plan, key=lambda f: ({"changes": 0, "journeys": 1, "cross": 3}.get(f.get("page"), 2), f.get("name", ""))):
            s = f.get("status", "discovered")
            out = str(f.get("outcome", "") or "")
            w(f'<tr><td>{e(f.get("name"))}</td><td>{chip(STATUS_LABEL.get(s, s), "st-" + s)}</td>'
              f'<td>{chip("Verified", "ok") if out.lower() == "verified" else e(out) or "—"}</td>'
              f'<td>{" ".join(chip(DIMS.get(x, x), "dim") for x in f.get("dims", [])) or "—"}</td>'
              f'<td class="muted">{e("; ".join(f.get("notes", []))[:300])}</td></tr>')
        w('</tbody></table></section>')

    # ---------- module coverage
    allmods = sorted(set(mods) | set(mod_pages))
    if allmods:
        w('<section class="card"><h2>Coverage by module</h2><div class="legend">'
          + "".join(f'<span><i class="seg s-{k}"></i>{STATUS_LABEL[k]}</span>' for k in ["explored", "partial", "blocked", "visited", "discovered"])
          + '</div><table class="mods"><thead><tr><th>Module</th><th>Pages visited</th><th>Features</th><th class="wide">Feature status</th></tr></thead><tbody>')
        for m in allmods:
            c = mods.get(m, Counter())
            tot = sum(c.values())
            mp = mod_pages.get(m, [])
            vis = sum(p.get("status") in {"visited", "partial", "explored"} for p in mp)
            w(f'<tr><td><b>{e(m)}</b></td><td>{vis}/{len(mp)}</td><td>{c["explored"]}/{tot} explored</td>'
              f'<td>{bar([(k, c[k]) for k in ["explored", "partial", "blocked", "visited", "discovered"]], tot)}</td></tr>')
        w('</tbody></table></section>')

    # ---------- dimension coverage
    if inscope:
        w('<section class="card"><h2>Test dimensions exercised</h2><div class="dims">')
        for k, lbl in DIMS.items():
            n = sum(k in f.get("dims", []) for f in inscope)
            w(f'<div class="dimrow"><span>{lbl}</span><div class="hbar"><span style="width:{pct(n, len(inscope))}%"></span></div><b>{pct(n, len(inscope))}%</b><small>{n}/{len(inscope)}</small></div>')
        w('</div><p class="fine">Share of in-scope features where each kind of testing was performed. Denominator: features discovered in this run.</p></section>')

    # ---------- defects
    w(f'<section class="card" id="defects"><h2>Defect register <span class="count">{len(defects)}</span></h2>')
    if defects:
        w('<div class="filters" role="group" aria-label="Filter defects"><button class="on" data-f="all">All</button>'
          + "".join(f'<button data-f="{s}">{s} ({sum(1 for x in defects if x.get("severity") == s)})</button>' for s in SEV)
          + '<input type="search" id="q" placeholder="Search defects…" aria-label="Search defects"></div>')
        for x in sorted(defects, key=lambda y: (SEV.index(y["severity"]) if y.get("severity") in SEV else 9, str(y.get("id")))):
            s = x.get("severity") or "Medium"
            ev_html = ""
            for evp in x.get("evidence") or []:
                name = Path(str(evp)).name
                if (d / "evidence" / name).exists() and name.lower().endswith((".png", ".jpg", ".jpeg")):
                    ev_html += f'<a href="evidence/{e(name)}" target="_blank"><img src="evidence/{e(name)}" alt="Evidence {e(name)}" loading="lazy"></a>'
                else:
                    ev_html += f'<code>{e(evp)}</code> '
            steps = "".join(f"<li>{e(t)}</li>" for t in (x.get("steps") or []) if str(t).strip())
            w(f'<details class="defect sev-{s.lower()}" data-sev="{e(s)}"><summary><span class="sev-dot {s.lower()}"></span>'
              f'<b>{e(x.get("id"))}</b> {e(x.get("title"))}<span class="sp"></span>{chip(s, "sev " + s.lower())}{chip(x.get("priority", ""), "dim")}'
              f'{chip(x.get("kind", ""), "dim")}{chip(x.get("status", "Open"), "dim")}</summary><div class="dbody">'
              + '<dl class="kv">' + "".join(f'<dt>{lbl}</dt><dd>{val}</dd>' for lbl, val in [
                  ("Module / page", " / ".join(e(v) for v in (x.get("module"), x.get("page")) if v)),
                  ("URL", f'<code>{e(x.get("url"))}</code>' if x.get("url") else ""),
                  ("Preconditions / role", " / ".join(e(v) for v in (x.get("preconditions"), x.get("role")) if v)),
                  ("Steps", f"<ol>{steps}</ol>" if steps else ""),
                  ("Expected", f'{e(x.get("expected"))} <span class="muted">(source: {e(x.get("expected_source") or "unstated")})</span>' if x.get("expected") else ""),
                  ("Actual", e(x.get("actual"))), ("Reproducibility", e(x.get("reproducibility"))),
                  ("Severity rationale", e(x.get("severity_rationale"))), ("Business impact", e(x.get("business_impact"))),
                  ("Recommendation", e(x.get("recommendation")))] if val) + '</dl>'
              f'{f"<div class=evidence>{ev_html}</div>" if ev_html else ""}</div></details>')
    else:
        w('<p class="muted">No defects recorded in this run.</p>')
    w('</section>')

    # ---------- blockers & risks
    if blockers:
        w('<section class="card"><h2>Blockers</h2><ul class="blockers">')
        for n in blockers:
            w(f'<li><time>{e(str(n.get("at", ""))[11:16])}</time>{e(n.get("text"))}</li>')
        w('</ul></section>')
    risks = [(l, narr.get(k)) for l, k in [("Business", "risk_business"), ("Data integrity", "risk_data"),
             ("Authorization", "risk_authorization"), ("Workflow & integration", "risk_workflow_integration"),
             ("Untested high-risk areas", "risk_untested_areas"), ("Environment", "risk_environment")] if narr.get(k)]
    acts = [(l, narr.get(k)) for l, k in [("Immediate", "action_immediate"), ("Investigate", "action_investigate"),
            ("Retest", "action_retest"), ("Remaining exploration", "action_remaining_exploration"),
            ("Access / environment", "action_blockers"), ("Next priorities", "action_next_priorities")] if narr.get(k)]
    if risks or acts:
        w('<section class="grid2">')
        if risks:
            w('<div class="card"><h2>Risk assessment</h2><dl class="kv">' + "".join(f"<dt>{l}</dt><dd>{e(v)}</dd>" for l, v in risks) + '</dl></div>')
        if acts:
            w('<div class="card"><h2>Recommended actions</h2><dl class="kv">' + "".join(f"<dt>{l}</dt><dd>{e(v)}</dd>" for l, v in acts) + '</dl></div>')
        w('</section>')

    # ---------- E2E flow timeline
    if flow:
        w('<section class="card"><h2>End-to-end flow</h2><ol class="timeline">')
        for s in flow:
            w(f'<li><div class="t-head"><b>{e(s.get("action"))}</b><time>{e(str(s.get("at", ""))[11:16])}</time></div>'
              f'<div class="muted"><code>{e(s.get("from"))}</code> → <code>{e(s.get("to"))}</code></div>'
              + (f'<div>Result: {e(s.get("result"))}</div>' if s.get("result") else "")
              + (f'<div>Assertion: {e(s.get("assert"))}</div>' if s.get("assert") else "") + '</li>')
        w('</ol></section>')

    # ---------- coverage gaps link + pages + activity
    if (d / "coverage-gaps.md").exists():
        w('<section class="card"><h2>UI vs automation coverage</h2>'
          f'<p>{cov["uncovered"] if cov else "?"} on-screen controls have no automation reference, and {cov["zero_coverage_pages"] if cov else "?"} pages have zero locator coverage. '
          'Details: <a href="coverage-gaps.md">coverage-gaps.md</a>.</p></section>')
    w('<section class="card"><details><summary><h2 class="inline">Pages discovered</h2> <span class="count">' + str(len(pages)) + '</span></summary>'
      '<table><thead><tr><th>Page</th><th>Module</th><th>URL</th><th>Status</th><th>Notes</th></tr></thead><tbody>')
    for p in sorted(pages.values(), key=lambda p: (p.get("module") or "", p.get("id", ""))):
        s = p.get("status", "discovered")
        w(f'<tr><td>{e(p.get("id"))}</td><td>{e(p.get("module"))}</td><td><code>{e(p.get("url"))}</code></td>'
          f'<td>{chip(STATUS_LABEL.get(s, s), "st-" + s)}</td><td class="muted">{e("; ".join(p.get("notes", []))[:240])}</td></tr>')
    w('</tbody></table></details></section>')
    acts_log = [n for n in notes if n.get("kind") in {"activity", "obs", "ambiguity", "env"}]
    if acts_log:
        w('<section class="card"><details><summary><h2 class="inline">Activity and observation log</h2> <span class="count">' + str(len(acts_log)) + '</span></summary><ul class="log">')
        for n in acts_log:
            w(f'<li><time>{e(str(n.get("at", ""))[11:16])}</time>{chip(n.get("kind"), "dim")}{e(n.get("text"))}</li>')
        w('</ul></details></section>')
    w('<footer>Limitations: browser-UI exploratory testing only; no database or server-log access; API behaviour observed only '
      'through browser traffic where checked; no load testing; percentages are relative to what was discovered in this run. '
      'Full text report: <a href="report.md">report.md</a>.</footer>')

    css = CSS
    js = JS
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src \'self\' file: data:; script-src \'nonce-{nonce}\'">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{css}</style></head>'
            f'<body><main>{"".join(H)}</main><script nonce="{nonce}">{js}</script></body></html>')
    out = d / "report.html"
    out.write_text(page, encoding="utf-8")
    return out


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--fg:#1b1f24;--mut:#5d6672;--line:#e3e6ea;--acc:#2f5bd3;
--ok:#0f7b45;--ok-bg:#e7f5ee;--warn:#9a5b00;--warn-bg:#fdf3e1;--bad:#b42318;--bad-bg:#fdecea;
--crit:#b42318;--high:#d9570a;--med:#b98900;--low:#5b6b7f;
--s-explored:#1f8a5b;--s-partial:#7fbf9f;--s-blocked:#d9570a;--s-visited:#9fb3d1;--s-discovered:#d5dbe3}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--fg:#e7e9ec;--mut:#9aa3ae;--line:#2b3037;--acc:#86a6ff;
--ok:#5fd39a;--ok-bg:#14291f;--warn:#f0b65a;--warn-bg:#2d2414;--bad:#ff8a7a;--bad-bg:#331a18;--s-discovered:#3a414b;--s-visited:#566a8a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1180px;margin:0 auto;padding:24px 16px 48px}a{color:var(--acc)}code{font:12px ui-monospace,Menlo,monospace;word-break:break-all}
.top h1{margin:2px 0 4px;font-size:28px}.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:var(--mut)}.meta{color:var(--mut);font-size:13px}
.verdict{margin:18px 0;padding:18px 20px;border-radius:12px;border:1px solid var(--line);border-left:6px solid}
.verdict.ok{background:var(--ok-bg);border-left-color:var(--ok)}.verdict.warn{background:var(--warn-bg);border-left-color:var(--warn)}.verdict.bad{background:var(--bad-bg);border-left-color:var(--bad)}
.v-label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--mut)}.v-value{font-size:26px;font-weight:700;margin:2px 0 6px}
.verdict.ok .v-value{color:var(--ok)}.verdict.warn .v-value{color:var(--warn)}.verdict.bad .v-value{color:var(--bad)}.verdict p{margin:4px 0}
.fine{font-size:12px;color:var(--mut)}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:16px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}.tile.bad{border-top:3px solid var(--bad)}.tile.warn{border-top:3px solid var(--warn)}
.t-label{font-size:12px;color:var(--mut)}.t-value{font-size:28px;font-weight:700;margin:2px 0}.t-value small{font-size:14px;font-weight:500;color:var(--mut)}.t-sub{font-size:12px;color:var(--mut)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px;overflow-x:auto}
.card h2{font-size:17px;margin:0 0 12px}h2.inline{display:inline;margin:0}.count{font-size:12px;background:var(--line);border-radius:10px;padding:1px 8px;margin-left:6px;vertical-align:middle}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}.grid2 .card{margin-bottom:0}.grid2{margin-bottom:16px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;color:var(--mut);font-weight:600}
td.muted,.muted{color:var(--mut)}th.wide{width:42%}
.kv{display:grid;grid-template-columns:minmax(120px,200px) 1fr;gap:6px 16px;margin:0}.kv dt{color:var(--mut);font-size:13px}.kv dd{margin:0}
.chip{display:inline-block;font-size:11px;padding:1px 8px;border-radius:10px;border:1px solid var(--line);margin:1px 3px 1px 0;white-space:nowrap}
.chip.ok{color:var(--ok);border-color:var(--ok)}.chip.dim{color:var(--mut)}
.chip.st-explored{background:var(--s-explored);color:#fff;border-color:transparent}.chip.st-partial{background:var(--s-partial);color:#0b2e1e;border-color:transparent}
.chip.st-blocked{background:var(--s-blocked);color:#fff;border-color:transparent}.chip.st-visited{background:var(--s-visited);color:#0e1a2e;border-color:transparent}
.chip.sev.critical{background:var(--crit);color:#fff;border-color:transparent}.chip.sev.high{background:var(--high);color:#fff;border-color:transparent}
.chip.sev.medium{background:var(--med);color:#fff;border-color:transparent}.chip.sev.low{background:var(--low);color:#fff;border-color:transparent}
.sev-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin:0 5px 0 0;vertical-align:middle}.sev-dot.critical{background:var(--crit)}.sev-dot.high{background:var(--high)}.sev-dot.medium{background:var(--med)}.sev-dot.low{background:var(--low)}
.bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--s-discovered);min-width:140px}.bar.empty{opacity:.4}
.seg{display:inline-block;height:100%}.s-explored{background:var(--s-explored)}.s-partial{background:var(--s-partial)}.s-blocked{background:var(--s-blocked)}.s-visited{background:var(--s-visited)}.s-discovered{background:var(--s-discovered)}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--mut);margin-bottom:8px}.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-2px}
.dims{display:grid;gap:8px}.dimrow{display:grid;grid-template-columns:150px 1fr 48px 56px;align-items:center;gap:10px;font-size:13px}.dimrow small{color:var(--mut)}
.hbar{height:10px;background:var(--line);border-radius:5px;overflow:hidden}.hbar span{display:block;height:100%;background:var(--acc)}
.filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.filters button{font:inherit;font-size:12px;padding:4px 10px;border-radius:14px;border:1px solid var(--line);background:transparent;color:var(--fg);cursor:pointer}
.filters button.on{background:var(--fg);color:var(--bg)}.filters input{margin-left:auto;font:inherit;font-size:13px;padding:4px 10px;border-radius:14px;border:1px solid var(--line);background:transparent;color:var(--fg);min-width:200px}
details.defect{border:1px solid var(--line);border-left:4px solid var(--low);border-radius:8px;margin-bottom:8px}
details.defect.sev-critical{border-left-color:var(--crit)}details.defect.sev-high{border-left-color:var(--high)}details.defect.sev-medium{border-left-color:var(--med)}
details.defect summary{display:flex;align-items:center;gap:6px;padding:10px 12px;cursor:pointer;flex-wrap:wrap}.sp{flex:1}
.dbody{padding:0 14px 14px}.evidence{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.evidence img{max-width:280px;max-height:180px;border:1px solid var(--line);border-radius:6px}
.blockers,.log{list-style:none;margin:0;padding:0}.blockers li,.log li{padding:6px 0;border-bottom:1px solid var(--line)}time{color:var(--mut);font-size:12px;margin-right:10px;font-variant-numeric:tabular-nums}
.timeline{list-style:none;margin:0;padding:0 0 0 18px;border-left:2px solid var(--line)}.timeline li{position:relative;padding:0 0 14px 12px}
.timeline li::before{content:"";position:absolute;left:-25px;top:5px;width:10px;height:10px;border-radius:50%;background:var(--acc)}.t-head{display:flex;gap:10px;align-items:baseline}
footer{color:var(--mut);font-size:12px;margin-top:24px}
@media (max-width:640px){.kv{grid-template-columns:1fr}.dimrow{grid-template-columns:110px 1fr 40px}.dimrow small{display:none}.filters input{margin-left:0;min-width:0;width:100%}}
@media print{body{background:#fff}.filters{display:none}details{display:block}details>*{display:block}}
"""

JS = """
(function(){var btns=document.querySelectorAll('.filters button'),q=document.getElementById('q'),f='all';
function apply(){var t=(q&&q.value||'').toLowerCase();document.querySelectorAll('details.defect').forEach(function(d){
var ok=(f==='all'||d.dataset.sev===f)&&(!t||d.textContent.toLowerCase().indexOf(t)>-1);d.style.display=ok?'':'none';});}
btns.forEach(function(b){b.addEventListener('click',function(){btns.forEach(function(x){x.classList.remove('on')});b.classList.add('on');f=b.dataset.f;apply();});});
if(q)q.addEventListener('input',apply);
window.addEventListener('beforeprint',function(){document.querySelectorAll('details').forEach(function(d){d.open=true});});})();
"""


if __name__ == "__main__":
    out = build(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"ok rich report -> {out}")
