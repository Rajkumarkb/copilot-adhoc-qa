# Adhoc QA agent in GitHub Actions

Every merge to `main` in **qa-automation** runs `.github/workflows/adhoc-qa.yml`:

1. **Detect changes**: `qa/ci/diff_inventory.py` rescans the framework at HEAD and at the commit the
   app model was built from (`qa/knowledge/model-base.txt`, else the previous main commit). It lists
   new and changed **fields/locators**, tests, assertions, routes, APIs, skipped tests and changed files
   in `qa/knowledge/changes.md`.
2. **Refresh the flow logic**: a Copilot CLI session updates `qa/knowledge/app-model.md` (modules,
   fields, rules, journeys) and writes a `## Recent changes` list of what to test.
3. **Full-application adhoc run**: the first session registers the plan in the ledger, in this order:
   CHANGE items, journeys including payment flows, every module, then cross-module checks. It logs
   in and tests **new and changed fields first**. Further sessions run (`continue`, about 40 browser
   actions each) until the plan is covered, the CI timebox is used, login fails or progress stalls.
4. **Report**: `report.md` and `report.html`, defects, screenshots, the updated app model and the
   Copilot transcripts are uploaded as the run artifact `adhoc-qa-<n>`, and a summary goes to Slack.

The agent runs unattended. It never clicks approval, payment or delete actions; it skips them and
logs them as `SKIPPED-APPROVAL` blockers. It never runs git, npm, npx, curl, gh or the framework.

## One-time setup

1. **Commit the agent into the qa-automation repo root:**
   - `.github/agents`, `.github/prompts` and `.github/workflows/adhoc-qa.yml`
   - `qa/` (including `qa/ci/` and `qa/knowledge/app-model.md`)
   - `.vscode/`
   - the `.gitignore` lines below
2. **Copilot token:** create a fine-grained personal access token with the **Copilot Requests**
   permission, owned by a user with a Copilot seat. Your org must allow Copilot CLI. Save it as the
   repository secret `COPILOT_GITHUB_TOKEN`.
3. **Login secrets:** in the workflow `env:`, point `QA_USER_EMAIL` and `QA_USER_PASS` at the **same
   repository secrets your existing UI test workflow uses**. The names on the left must match
   `username_secret` and `password_secret` in `qa/qa.config.yaml`.
4. **Slack:** add the repository secret `SLACK_WEBHOOK_URL` (a new webhook, not the old exposed one).
5. **Runner:** if your existing UI tests use a self-hosted runner to reach QA, set the repository
   variable `QA_RUNNER` to its label. Otherwise `ubuntu-latest` is used. It needs Google Chrome.
6. **Optional repository variables:**
   - `COPILOT_MODEL`: the model for the sessions
   - `QA_CI_TIMEBOX`: active minutes; default 300, and GitHub-hosted jobs stop at 6 h
   - `QA_MAX_SESSIONS`: default 20
   - `COPILOT_CLI_VERSION`: pin the CLI version
7. **Test it:** go to **Actions → Adhoc QA agent → Run workflow**.

`.gitignore` additions:
```
qa/runs/
qa/knowledge/changes.md
qa/knowledge/model-base.next
```

## Keeping the model current

Each CI run refreshes the model in its own workspace and puts `app-model.md` and `model-base.next` in
the artifact. The repo copy isn't changed. Until you commit a newer model, every run sees **all**
changes since `model-base.txt`.

To commit a newer model, take `app-model.md` and `model-base.next` from a good run's artifact and
commit them as:
- `qa/knowledge/app-model.md`
- `qa/knowledge/model-base.txt`

Changes under `qa/knowledge/` don't trigger a new run.

## Phase 2: trigger from the AlertBus app repo

Add this workflow to the app repo. It needs a PAT secret `QA_DISPATCH_TOKEN` with
**Contents: read & write** on `qa-automation`.

```yaml
name: Trigger Adhoc QA
on:
  push:
    branches: [main]
jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 2 }
      - env:
          GH_TOKEN: ${{ secrets.QA_DISPATCH_TOKEN }}
        run: |
          git diff --name-only HEAD~1 HEAD | head -300 | python3 -c "import json,sys,os;print(json.dumps({'event_type':'alertbus-app-merged','client_payload':{'changed_files':[l.strip() for l in sys.stdin if l.strip()],'app_sha':os.environ['GITHUB_SHA']}}))" > body.json
          gh api repos/BusPatrol/qa-automation/dispatches --input body.json
```

The QA run then lists the changed app files under "AlertBus app files changed" in `changes.md`, and
the agent maps them to modules and fields to test first.

## Costs and limits

- Every session uses Copilot premium requests. A full run is typically 10–20 sessions.
- Runs are queued one at a time (`concurrency`). If several merges land during a run, only the
  newest waits.
- CI login must work without MFA, as it does for your existing UI tests. If sign-in fails, the run
  stops early, and Slack shows `LOGIN-FAILED`.
