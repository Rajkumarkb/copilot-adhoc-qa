---
name: qa-start
description: Start a new adhoc QA run against the configured QA environment
agent: Adhoc QA
---
Run `python3 qa/setup.py` (use `python` on Windows). If it prints `FIX` lines, show me exactly those lines and stop. If it prints `RESTART`, ask me to restart the playwright server and wait for my reply.
Run `python3 qa/ledger.py init` (use `python` on Windows). If it prints STOP, tell me the one thing to fix and stop.
Otherwise the printed brief is your scope and rules. Do the Login steps (ask me to finish sign-in in the Chrome window if MFA appears, and wait for my reply). Then work through the whole Workflow: discover → one E2E positive flow → aggressive exploration, logging everything with the ledger. Don't stop after discovery, and don't write the report; I'll run /qa-report. Use `qa/knowledge/app-model.md` (not the framework files) as guidance: its routes, journeys and business rules; spend most of the time on its "Adhoc gaps".