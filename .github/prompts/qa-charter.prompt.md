---
name: qa-charter
description: Focused exploratory session on ONE module (e.g. /qa-charter Reports - try to make totals wrong)
agent: Adhoc QA
argument-hint: "<module> [- goal]"
---
Run a focused, charter-based session. The text after /qa-charter is the module and an optional goal; if no goal is given, use: "find defects the automation does not cover".

1. Run `python3 qa/setup.py` and act on any `FIX`/`RESTART` line as in /qa-start. Then run `python3 qa/ledger.py init` (use `python` on Windows) unless a run is already active for this charter, then `python3 qa/ledger.py note activity "Charter: <module> - <goal>"`.
2. From `qa/knowledge/app-model.md` read only `## Overview`, `## Journeys` and the matching `## Module:` section (find line numbers with `grep -n "^## " qa/knowledge/app-model.md`, then read that range). If the file doesn't exist, tell me to run /qa-learn once, and continue without it if I say so.
3. Do the Login steps, then go straight to the module's routes. Run its journey once as a quick sanity check, then spend the session on the module's **Adhoc gaps** and on challenging its **Business rules** (negative, boundary, navigation/state, data consistency with other modules, role checks). Stay inside this module except to verify cross-module data.
4. Follow all agent rules (safety, ledger logging, token discipline, checkpoints). Don't write the report; I'll run /qa-report.
