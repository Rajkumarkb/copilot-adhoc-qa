#!/usr/bin/env python3
"""
Read-only scanner for an existing test-automation framework (UI + API).
Writes a compact, redacted inventory to qa/knowledge/framework-inventory.md so the
Adhoc QA agent can learn the app's flows without reading every file (token saving).

Usage:  python3 qa/scan_framework.py [/path/to/framework] [--out FILE.md] [--json FILE.json]
        (default path: framework_path in qa.config.yaml; --json is used by qa/ci/diff_inventory.py)

Never opens .env*, key/cert files or anything named like secret/credential.
Never runs the framework. Redacts emails, long tokens, webhook URLs and password-like lines.
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "knowledge" / "framework-inventory.md"

SKIP_DIRS = {"node_modules", ".git", "dist", "build", "out", "test-results", "playwright-report",
             "coverage", ".venv", "venv", "__pycache__", ".idea", ".vscode", "target", ".gradle",
             "screenshots", "videos", "downloads", "logs", "tmp", ".cache", "allure-results",
             "allure-report", "blob-report", "html-report", "junit-report"}
SKIP_FILE_RE = re.compile(r"(^\.env)|(\.(pem|key|crt|p12|pfx|jks|lock|png|jpg|jpeg|gif|mp4|zip|pdf|xlsx|csv)$)"
                          r"|secret|credential|password|token", re.I)
CODE_EXT = {".ts", ".tsx", ".js", ".mjs", ".cjs", ".py", ".java", ".kt", ".cs", ".feature", ".rb"}
DATA_EXT = {".json", ".yaml", ".yml"}
MAX_FILE_BYTES = 400_000

# --- redaction --------------------------------------------------------------
RED = [
    (re.compile(r"https://hooks\.slack\.com/\S+"), "<slack-webhook>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "<email>"),
    (re.compile(r"\b(eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,})\b"), "<jwt>"),
    (re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"), "<token>"),
]
SECRETY_LINE = re.compile(r"(pass(word)?|secret|token|api[_-]?key|authorization|bearer|cookie)\s*[:=]", re.I)


def red(s: str) -> str:
    for rx, rep in RED:
        s = rx.sub(rep, s)
    return s.strip()


# --- extraction patterns ----------------------------------------------------
P_TITLE = re.compile(r"""\b(?:test|it|describe|test\.describe|context|Scenario(?: Outline)?|Feature)\s*(?:\.(?:only|skip|fixme|serial|parallel))?\s*[(:]\s*['"`]([^'"`\n]{3,160})""")
P_PYTEST = re.compile(r"^\s*def (test_\w+)", re.M)
P_JAVA = re.compile(r"@Test[\s\S]{0,200}?\b(?:public\s+)?void\s+(\w+)\s*\(")
P_SKIP = re.compile(r"""\b(?:test|it|describe)\.(?:skip|fixme)\s*\(\s*['"`]([^'"`\n]{3,160})|\bxit\s*\(\s*['"`]([^'"`\n]{3,160})|@(?:skip|ignore|Disabled|wip)\b""", re.I)
P_TAG = re.compile(r"@(smoke|regression|sanity|e2e|critical|p[0-3]|api|ui|negative|flaky)\b", re.I)
P_GOTO = re.compile(r"""\.goto\(\s*[`'"]([^`'"]{1,160})""")
P_URLRX = re.compile(r"""toHaveURL\(\s*(/(?:\\/|[^/\n]){1,160}/[gimsuy]*|[`'"][^`'"\n]{1,160})""")
P_API = re.compile(r"""\b(?:request|apiContext|api|client|axios|http|requests|session)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[`'"f]*([^`'",)\n]{2,160})""", re.I)
P_PATH = re.compile(r"""[`'"](/(?:api|v\d)[/\w{}$.:-]*)[`'"]""")
P_CLASS = re.compile(r"\bclass\s+(\w+)")
P_METHOD = re.compile(r"^\s*(?:async\s+|public\s+|private\s+|protected\s+|def\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*[\w<>\[\], |]+)?\s*[{:]", re.M)
P_EXPECT_TXT = re.compile(r"""(toHaveText|toContainText|toHaveValue|toBe|toEqual|toHaveCount|toHaveStatus|assertEqual|assert_equal|assertThat)\s*\(\s*([^)\n]{1,120})\)""")
P_STATUS = re.compile(r"""(?:status\(\)\)?\.toBe|status_code\s*==|statusCode\)?\.toBe|toHaveStatus)\s*\(?\s*(\d{3})""")
# UI fields / locators (Playwright TS+Py, Cypress, Selenium) - used to detect new or changed fields
P_FIELDS = [
    (re.compile(r"""get_?[Bb]y_?[Ll]abel\(\s*['"`]([^'"`\n]{1,80})"""), "label"),
    (re.compile(r"""get_?[Bb]y_?[Pp]laceholder\(\s*['"`]([^'"`\n]{1,80})"""), "placeholder"),
    (re.compile(r"""get_?[Bb]y_?[Tt]est_?[Ii]d\(\s*['"`]([^'"`\n]{1,80})"""), "testid"),
    (re.compile(r"""get_?[Bb]y_?[Rr]ole\(\s*['"`](\w+)['"`]\s*,\s*\{?[^)]{0,80}?name\s*[:=]\s*(?:['"`]([^'"`\n]{1,80})|/([^/\n]{1,80})/)"""), "role"),
    (re.compile(r"""(?:\.locator|cy\.get|\$\$?|find_element|querySelector)\(\s*['"`]([^'"`\n]{2,120})"""), "css"),
    (re.compile(r"""By\.(?:id|name|cssSelector|xpath|linkText)\(\s*"([^"\n]{1,120})"""), "by"),
]
MAX_FIELDS = 60
METHOD_STOP = {"if", "for", "while", "switch", "catch", "function", "constructor", "return", "describe", "test", "it",
               "expect", "beforeEach", "afterEach", "beforeAll", "afterAll", "super", "async"}


def walk(base: Path):
    for dp, dns, fns in os.walk(base):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")
                  and (Path(dp) / d).resolve() != ROOT  # skip this agent's own qa/ folder
                  and not ((Path(dp) / d / "ledger.py").exists() and (Path(dp) / d / "qa.config.yaml").exists())]
        for fn in fns:
            if SKIP_FILE_RE.search(fn):
                continue
            p = Path(dp) / fn
            if p.suffix.lower() in CODE_EXT | DATA_EXT or fn == "package.json":
                try:
                    if p.stat().st_size <= MAX_FILE_BYTES:
                        yield p
                except OSError:
                    pass


def kind_of(rel: str) -> str:
    r = rel.lower()
    if re.search(r"(^|/)(api|apis|services?)(/|$)|\.api\.|api[-_]?test", r):
        return "api"
    if re.search(r"(^|/)(pages?|page-?objects?|po|screens?|components?)(/|$)|page\.(ts|js|py|java)$", r):
        return "page"
    if re.search(r"\.(spec|test|e2e)\.|(^|/)(tests?|specs?|e2e|features?)(/|$)|_test\.py$|test_\w+\.py$|\.feature$", r):
        return "spec"
    if re.search(r"(^|/)(fixtures?|data|test-?data|testdata)(/|$)", r):
        return "data"
    if re.search(r"config|playwright\.|cypress\.|wdio\.|jest\.|pytest\.ini|conftest", r):
        return "config"
    return "other"


def module_of(rel: str) -> str:
    parts = [p for p in Path(rel).parts[:-1]
             if p.lower() not in {"src", "tests", "test", "specs", "spec", "e2e", "ui", "api", "pages",
                                  "page-objects", "pageobjects", "features", "qa", "alertbus"}]
    return parts[-1] if parts else Path(rel).stem.split(".")[0]


def fields_of(text: str) -> list[str]:
    out: list[str] = []
    for rx, kind in P_FIELDS:
        for m in rx.finditer(text):
            if kind == "role":
                v = f"{m.group(1)}:{m.group(2) or m.group(3)}"
            else:
                v = m.group(1)
            v = red(v)
            if v and f"{kind} {v}" not in out:
                out.append(f"{kind} {v}")
            if len(out) >= MAX_FIELDS:
                return out
    return out


def main() -> None:
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--json", dest="json_out")
    a = ap.parse_args()
    out_md = Path(a.out)
    fw = a.path
    if not fw:
        try:
            env_path = ROOT / ".env.qa"
            env_values = {}
            if env_path.exists():
                for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
                    if match:
                        value = match.group(2).strip().strip("'\"")
                        env_values[match.group(1)] = value
            if env_values.get("QA_AUTOMATION_PATH"):
                fw = env_values["QA_AUTOMATION_PATH"]
            m = re.search(r'^framework_path\s*:\s*["\']?([^"\'#\n]+?)["\']?\s*(?:#.*)?$',
                          (ROOT / "qa.config.yaml").read_text(encoding="utf-8"), re.M)
            if not fw:
                fw = m.group(1).strip() if m else None
        except OSError:
            fw = None
    if not fw or fw.startswith("/path/to"):
        sys.exit("Give the framework path: python3 qa/scan_framework.py /path/to/framework "
                 "(or set QA_AUTOMATION_PATH in qa/.env.qa / framework_path in qa/qa.config.yaml)")
    p = Path(os.path.expanduser(fw))
    base = (p if p.is_absolute() else ROOT.parent / p).resolve()
    if not base.is_dir():
        sys.exit(f"Not a folder: {base}")

    files = list(walk(base))
    by_kind: dict[str, list[str]] = defaultdict(list)
    titles: dict[str, list[str]] = defaultdict(list)
    skipped: list[str] = []
    tags = Counter()
    routes = Counter()
    apis = Counter()
    statuses = Counter()
    page_objs: dict[str, list[str]] = {}
    fields: dict[str, list[str]] = {}
    expects: dict[str, list[str]] = defaultdict(list)
    scripts: list[str] = []
    data_files: list[str] = []

    for p in files:
        rel = p.relative_to(base).as_posix()
        k = kind_of(rel)
        by_kind[k].append(rel)
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if p.name == "package.json":
            for m in re.finditer(r'"([\w:.\-]+)"\s*:\s*"((?:npx |npm |playwright|cross-env|jest|cypress|wdio|node)[^"]*)"', txt):
                scripts.append(f"{m.group(1)}: {red(m.group(2))[:140]}")
            continue
        if p.suffix.lower() in DATA_EXT:
            if k == "data":
                data_files.append(rel)
            continue
        safe_lines = "\n".join(l for l in txt.splitlines() if not SECRETY_LINE.search(l))
        for m in P_TITLE.finditer(safe_lines):
            titles[rel].append(red(m.group(1)))
        for m in P_PYTEST.finditer(safe_lines):
            titles[rel].append(m.group(1))
        for m in P_JAVA.finditer(safe_lines):
            titles[rel].append(m.group(1))
        for m in P_SKIP.finditer(safe_lines):
            skipped.append(f"{rel}: {red(m.group(1) or m.group(2) or m.group(0))}")
        tags.update(t.lower() for t in P_TAG.findall(safe_lines))
        for m in P_GOTO.finditer(safe_lines):
            routes[red(m.group(1))] += 1
        for m in P_URLRX.finditer(safe_lines):
            routes["expect URL " + red(m.group(1))] += 1
        for m in P_API.finditer(safe_lines):
            apis[f"{m.group(1).upper()} {red(m.group(2))}"] += 1
        for m in P_PATH.finditer(safe_lines):
            apis[f"PATH {red(m.group(1))}"] += 1
        statuses.update(P_STATUS.findall(safe_lines))
        f = fields_of(safe_lines)
        if f:
            fields[rel] = f
        if k == "page":
            cls = P_CLASS.findall(safe_lines)
            meths = [m for m in P_METHOD.findall(safe_lines) if m not in METHOD_STOP and not m.startswith("_")]
            page_objs[rel] = [", ".join(cls[:3]) or Path(rel).stem, ", ".join(dict.fromkeys(meths).keys())[:400]]
        if k in {"spec", "api"}:
            for m in P_EXPECT_TXT.finditer(safe_lines):
                v = red(m.group(2))
                if any(c.isalpha() or c.isdigit() for c in v) and len(expects[rel]) < 8:
                    expects[rel].append(f"{m.group(1)}({v})")

    mods: dict[str, list[str]] = defaultdict(list)
    for rel in titles:
        mods[module_of(rel)].append(rel)

    L: list[str] = []
    w = L.append
    w(f"# Framework inventory (auto-generated, redacted)\n")
    w(f"Source: `{base.name}` · files scanned: {len(files)} · "
      + " · ".join(f"{k}: {len(v)}" for k, v in sorted(by_kind.items())))
    w("Never run this framework from the QA agent. Never open its .env files.\n")
    if scripts:
        w("## Run scripts (package.json)")
        for s in scripts[:30]:
            w(f"- {s}")
        w("")
    w("## Test tags")
    w(", ".join(f"{t}={n}" for t, n in tags.most_common(15)) or "none found")
    w("")
    w("## Tests by module (titles)")
    for mod in sorted(mods):
        n = sum(len(titles[r]) for r in mods[mod])
        w(f"### {mod} ({n} tests)")
        for rel in sorted(mods[mod]):
            t = list(dict.fromkeys(titles[rel]))
            w(f"- `{rel}`: " + " | ".join(t[:25]) + (" | …" if len(t) > 25 else ""))
        w("")
    w("## Skipped / fixme / disabled (risk areas for adhoc)")
    for s in skipped[:60] or ["none found"]:
        w(f"- {s}")
    w("")
    w("## UI routes seen")
    for r, n in routes.most_common(80):
        w(f"- {r} ({n})")
    if not routes:
        w("- none found")
    w("")
    w("## API calls / endpoints seen")
    for api_name, n in apis.most_common(120):
        w(f"- {api_name} ({n})")
    if not apis:
        w("- none found")
    if statuses:
        w(f"\nAsserted HTTP statuses: " + ", ".join(f"{s}×{n}" for s, n in statuses.most_common()))
    w("")
    w("## Page objects (class: methods)")
    for rel, (cls, meths) in sorted(page_objs.items())[:80]:
        w(f"- `{rel}` {cls}: {meths}")
        if fields.get(rel):
            w(f"  - fields: " + "; ".join(fields[rel][:25]) + (" …" if len(fields[rel]) > 25 else ""))
    if not page_objs:
        w("- none found")
    w("")
    w("## Assertion samples (oracle hints, per spec)")
    for rel, ex in sorted(expects.items())[:80]:
        w(f"- `{rel}`: " + "; ".join(ex))
    w("")
    w("## Test data files (open only if needed; may contain PII)")
    for d in sorted(data_files)[:60] or ["none found"]:
        w(f"- {d}")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(L) + "\n", encoding="utf-8")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({
            "tests": {r: list(dict.fromkeys(t)) for r, t in titles.items()},
            "skipped": sorted(set(skipped)), "routes": sorted(routes), "apis": sorted(apis),
            "page_objects": {r: {"classes": c, "methods": m} for r, (c, m) in page_objs.items()},
            "fields": fields, "expects": dict(expects), "modules": {m: sorted(v) for m, v in mods.items()},
        }, indent=1), encoding="utf-8")
    total = sum(len(v) for v in titles.values())
    print(f"ok inventory -> {out_md} | {len(files)} files, {total} tests, "
          f"{len(mods)} modules, {len(routes)} routes, {len(apis)} api refs, {len(skipped)} skipped, "
          f"{len(page_objs)} page objects, {sum(len(v) for v in fields.values())} fields")


if __name__ == "__main__":
    main()
