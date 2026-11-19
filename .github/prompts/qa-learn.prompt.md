---
name: qa-learn
description: One-time - learn the app's flows and rules from the automation framework and write a compact app model
agent: Adhoc QA
---
Goal: build `qa/knowledge/app-model.md`, a compact model of the app that later QA sessions read instead of the framework.

1. Run `python3 qa/scan_framework.py` (uses `framework_path` from `qa/qa.config.yaml`; `python` on Windows). Then read `qa/knowledge/framework-inventory.md`.
2. Open ONLY the most informative framework files, at most ~25: per module the smoke/critical/e2e specs, their page objects, and the API specs that assert business rules or permissions. Read just the test bodies (steps + assertions), not helpers or configs.
3. Hard rules: never open any `.env*`, key or credential file; never run the framework (no npm/npx/playwright/pytest); never call APIs; never copy credentials, tokens, emails, phone numbers, plates or other personal data into the model (partner/test-account role names are fine).
4. Write `qa/knowledge/app-model.md` in ONE write, max ~250 lines, exactly these sections:
   - `## Overview` - what the app does, modules, roles, base routes (<=15 lines)
   - `## Journeys` - the critical end-to-end flows as numbered steps, each with its source spec file
   - `## Module: <Name>` (one per module) with bullets: Routes · Key screens/controls · Business rules / expected results (tag each `[asserted: <spec file>]` or `[inferred]`) · Automated coverage (1-3 lines) · Adhoc gaps (not automated, skipped/fixme, negative/boundary cases missing, cross-module checks) · Safe test data notes
   - `## API to UI map` - endpoint -> screen/action, for interpreting browser network traffic
   - `## Do-not-touch` - actions with external side effects seen in the framework (notifications, webhooks, approvals on real data, bulk jobs)
5. Reply with one line: modules found, journeys found, file path, and remind me to review it and commit `qa/knowledge/app-model.md` so colleagues never need to run /qa-learn.
