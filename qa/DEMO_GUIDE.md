# Demo guide: Adhoc QA Agent (GitHub Copilot + Playwright MCP)

Audience: manager + team. Length: 20-25 minutes (15 min live/semi-live, 5-10 min Q&A).

## 1. The one-sentence pitch

An autonomous exploratory QA tester that runs inside Copilot agent mode, drives a real browser, and produces an evidence-backed report. It looks for what the existing Playwright automation does **not** cover.

## 2. Story to tell (problem -> solution -> proof -> next)

| Part | Message | Time |
|---|---|---|
| Problem | Automation checks what we already thought of. Only 5% of AlertBus UI controls are targeted by a locator. Exploratory testing is manual and unrepeatable. | 2 min |
| Solution | Copilot agent + Playwright MCP + a Python ledger that keeps state on disk. | 3 min |
| Live | One focused charter, shown in real time. | 8 min |
| Proof | Coverage gap report, defects with evidence, honest report rules. | 5 min |
| Scale | Runs unattended in CI after every merge, summary to Slack. | 2 min |
| Ask | Pilot scope, Copilot token, runner. | 2 min |

## 3. Numbers you can quote (from the existing runs)

Source: [qa/runs/run-20261113-233321/coverage-gaps.md](runs/run-20261113-233321/coverage-gaps.md)

- 61 pages mapped, 560 distinct controls found.
- 29 controls (5%) have a framework locator; 219 only appear in test titles; 312 have no automation reference.
- 38 of 61 pages have zero locator coverage. All 7 Reports pages and nearly all Jobs pages are uncovered.
- First run found 3 defects with screenshots: login route 404 (Medium), print jobs failing with `SignatureNotFound` skipping 32 citations (Medium, environment), Events "All" filter mislabels results as reviewable (Low). See [qa/runs/run-20261113-155421/defects](runs/run-20261113-155421/defects).

Say the caveat yourself: matching is by accessible name, so gaps are "candidates to review", not proof. Also state that the current run is partial (features explored 8%, 2/25). Do not overstate coverage; the report generator itself refuses to.

## 4. Pre-demo checklist (do this the day before / 30 min before)

- [ ] VS Code open on this folder, Copilot Chat in agent mode, **Adhoc QA** agent selected.
- [ ] `.vscode/mcp.json`: playwright server shows **Running**. Chat > Manage Tool Approval: tick `playwright` so you are not clicking Allow on camera.
- [ ] Logged in once in the Chrome profile (`qa/.browser-profile`) so SSO/MFA is not needed live. Confirm by opening the QA site.
- [ ] `python3 qa/setup.py` prints no `FIX`/`RESTART` lines.
- [ ] QA site reachable: `qa-alertbus-dashboard.aws.buspatrol.com`.
- [ ] Generate a finished report to show as the fallback: run `python3 qa/ledger.py report` (or `/qa-report`) on the latest run, and open `report.html`. No `report.md`/`report.html` exists in `qa/runs` right now.
- [ ] Close/hide: `qa/.env.qa` (credentials), any tab with real violator data. Evidence screenshots can contain plates or personal data; review them before sharing on screen.
- [ ] Screen: font size up (Cmd +), Chrome window and VS Code side by side, notifications off.
- [ ] Record a 2-minute screen capture of a good charter run as a backup if the QA site is down or SSO misbehaves.

### Config choices for the demo (decide before you start)

[qa/qa.config.yaml](qa.config.yaml) currently has `payment_testing.enabled: true`, meaning the agent may make full sandbox payments **without asking**. For a live demo, set it to `false` or do not run `/qa-full`. Keep `environment: QA` and the production hosts list visible: it is your safety story.

## 5. Live demo script

Do not run `/qa-full` live. It takes hours (timebox 480 min). Use a short charter.

### Step 1 - Show the setup (2 min)

1. Open [README.md](../README.md) "What's inside" and point out three things: the agent file, the prompts (slash commands), and the ledger.
2. Open [qa/qa.config.yaml](qa.config.yaml): app URL, `production_hosts` (never touched), `approval_required_keywords` (delete, pay, approve, ...), `off_limits`.
3. Say: "Secrets are never in the prompt. The agent types the secret *name* and Playwright MCP substitutes and redacts the value."

### Step 2 - Safety gate (1 min)

Run in the terminal:

```bash
python3 qa/setup.py
python3 qa/ledger.py init
```

Talking point: `init` refuses to start if `base_url` is a production host. Optionally show it by temporarily pointing at a production host in a throwaway copy, then restore. Skip if short on time.

### Step 3 - Live charter (8 min)

In Copilot Chat, Adhoc QA agent:

```
/qa-charter Reports - try to make totals wrong
```

Narrate while it runs (the Chrome window is visible):

- It reads only the relevant section of `qa/knowledge/app-model.md`, not the whole framework.
- It goes straight to `/reports/...`, tries negative, boundary and data-consistency cases.
- Each action is logged on disk. In a second terminal, run:

```bash
python3 qa/ledger.py status
```

  Point out: coverage, dimensions (pos/neg/bnd/nav/data/role/ui), open defects, NEXT items. The model reads this 10-line summary instead of the full history. That is the token saving.
- If it hits a button matching an approval keyword, it **stops and asks**. If this happens, it is the best moment to show the safety design.

Fallback if the browser or SSO fails: switch to the recorded capture and continue at Step 4.

### Step 4 - Coverage gap report (3 min)

```bash
python3 qa/coverage.py report
```

Open [coverage-gaps.md](runs/run-20261113-233321/coverage-gaps.md). Show the "Coverage by page" table, then the "Gaps by module" list for Reports or Jobs. Message: "This tells the automation team where to add tests next."

### Step 5 - Defects and evidence (3 min)

Open one defect, for example [D-003](runs/run-20261113-155421/defects/D-003.yaml) (Events "All" filter mislabel) and its screenshot in `evidence/events-all-filter-mislabels-summary.png`. Show the structure: steps, expected + source, actual, reproducibility, severity rationale, evidence path.

Then open D-002: it is tagged `kind: environment`, which shows the agent separates product bugs from environment problems.

### Step 6 - The report and its honesty rules (2 min)

Open `report.html` (generated in the pre-demo step). Say:

- Sections A-I are generated by Python, not written by the model: tables and percentages cannot be hallucinated.
- Verdict is forced to **NOT READY** if a confirmed Critical defect is open.
- Verdict is downgraded if High defects, blocked or untouched items remain.
- Confirmed defects without evidence are flagged. "Fixed" without retest is flagged. Every percentage states its denominator.

### Step 7 - Scale-out in CI (2 min)

Show [.github/workflows/adhoc-qa.yml](../.github/workflows/adhoc-qa.yml) and [qa/ci/README-ci.md](ci/README-ci.md):

1. Merge to `main` -> diff of new/changed fields and locators.
2. Copilot CLI refreshes the app model.
3. Full-application run, new and changed fields tested first, payment/delete actions skipped and logged as `SKIPPED-APPROVAL`.
4. Artifact (`report.html`, defects, screenshots) + Slack summary.

## 6. Command cheat sheet

| Command | Purpose |
|---|---|
| `/qa-learn` | One-time: build `app-model.md` from the framework |
| `/qa-start` | New exploratory run |
| `/qa-charter <module> - <goal>` | Focused session on one module (best for demos) |
| `/qa-coverage` | Map UI vs automation gaps |
| `/qa-full` | Whole app: journeys, modules, cross-module (hours, multi-chat) |
| `/qa-continue` | Resume in a fresh chat from the ledger |
| `/qa-report` | Finish and build report |
| `python3 qa/ledger.py status` | 10-line progress view |
| `python3 qa/coverage.py report` | Coverage gap report |

## 7. Likely questions and answers

| Question | Answer |
|---|---|
| Does it replace our Playwright suite? | No. It complements it: finds untested areas and edge cases, and the gap report feeds new automated tests. |
| Is it safe on QA data? | It refuses production hosts, blocks non-allowed origins, stops before approve/delete/pay/send/export type actions, and only edits records it created with the `QA-AUTO-` prefix. Caveat: the origin block is a guardrail, not a security boundary. |
| Can it leak credentials? | The model sees only secret names. Values are substituted by the MCP server and redacted in responses. `.env.qa` is git-ignored. |
| How reliable are the findings? | Defects carry evidence, steps, expected source and repro count. Suspected and environment issues are labelled separately. A human still triages. |
| Cost? | Uses Copilot premium requests. A CI full run is about 10-20 sessions. Token saving: no screenshots sent to the model, no page snapshots by default, state on disk. A smaller model is enough for exploration. |
| What can't it do? | Browser-UI only. No DB or server logs, no load testing; API seen only via network traffic. Coverage is relative to what it discovered. |
| Why is coverage only 8% in the current run? | The run is mid-way (185 of 480 min used). Journeys and some modules are still pending, and the Event Processing and Fast Access Evidence hosts are outside the authorized `base_url`, so they are logged as blockers. |
| MFA/SSO? | Interactive mode: the agent asks you to finish sign-in once; the session persists in `qa/.browser-profile`. CI needs MFA-free test accounts, same as existing UI tests. |

## 8. Pitfalls to avoid on the day

- Do not start `/qa-full` or any payment flow live.
- Do not scroll through `qa/.env.qa` or `.browser-profile`.
- If the agent asks "Continue?", click Continue; do not apologise, explain it is the Copilot step limit and is configured in `.vscode/settings.json`.
- If it is mid-run when time is up, run `/qa-continue` in a new chat later; state is on disk, which is also a demo point.
- Do not claim the 3 defects are all product bugs: one is `environment`, one is Low severity.

## 9. Closing ask

Propose a 2-week pilot: run `/qa-charter` on Reports and Jobs (zero-coverage modules), enable the CI workflow on a schedule rather than every merge, and review the defects and gap report together. Success measure: number of confirmed defects and new automated tests created from the gap list.
