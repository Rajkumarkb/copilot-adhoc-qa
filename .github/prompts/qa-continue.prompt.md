---
name: qa-continue
description: Resume the current adhoc QA run in a fresh chat (keeps token use low)
agent: Adhoc QA
---
Run `python3 qa/setup.py && python3 qa/ledger.py brief && python3 qa/ledger.py status` (use `python` and `;` on Windows). Act on any `FIX`/`RESTART` line as in /qa-start. Do the Login steps if not signed in (the browser profile usually keeps the session). Resume in this order: (1) `partial` plan items, (2) untouched plan items, (3) partial child features with the fewest covered dims, then unvisited pages. Stay on the current feature until it has a verified productive outcome or an exact blocker. Page visits and form mapping do not count as a completed E2E flow. Only if 'status' prints 'TIMEBOX USED UP', do the report steps instead.
Use `qa/knowledge/app-model.md` (not the framework files) as guidance: its routes, journeys and business rules; spend most of the time on its "Adhoc gaps".