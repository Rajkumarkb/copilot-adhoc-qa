
## Task: start the full-application run (the workflow already ran `ledger.py init`)
1. Run `python3 qa/ledger.py brief`.
2. Build the plan in ONE terminal call joined with `&&` (this is how later sessions resume):
   - FIRST, every line of `## Recent changes` in `qa/knowledge/app-model.md`: `python3 qa/ledger.py feat changes "CHANGE <Module>: <what>" --note "<test hint>"`
   - then everything from step 2 of `.github/prompts/qa-full.prompt.md` (journeys incl. payment flows, then every module in risk order) — read that file for the exact commands
   - then `python3 qa/ledger.py feat cross "Phase C cross-module consistency"`
   - then `python3 qa/ledger.py note activity "CI FULL RUN commit <commit from Run context>: <c> changes, <n> journeys, <m> modules"`
3. Do the Login steps.
4. Test in plan order and keep cycling until the 40-action checkpoint:
   - CHANGE items first. For a new or changed field: find it on screen, check the label, required vs optional, valid value saves and shows in list/detail/report, invalid and boundary values (empty, min/max length ±1, format, special/Unicode, 0/negative for numbers, past/future dates), persistence after refresh, and behaviour for a role without access. For a changed rule or behaviour: reproduce the new expected result and its negative case. Removed field: confirm it is really gone everywhere and nothing broke. Mark each `explored`/`partial` with dims.
   - Then Phase A (journeys) and Phase B (modules) exactly as in `.github/prompts/qa-full.prompt.md`, then Phase C.
