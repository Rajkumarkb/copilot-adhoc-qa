---
name: qa-full
description: Full-application adhoc QA - every business journey end-to-end, then every module, then cross-module checks (spans several chats via /qa-continue)
agent: Adhoc QA
---
1. Run `python3 qa/setup.py` (use `python` on Windows). If it prints `FIX` lines, show me exactly those and stop; if `RESTART`, ask me to restart the playwright server and wait. Then run `python3 qa/ledger.py init` (STOP -> tell me the fix and stop).
2. Build the plan in the ledger (this is what lets /qa-continue resume in later chats). Read `qa/knowledge/app-model.md` once: Overview, Journeys, and each `## Module:` heading with its Adhoc gaps. If it doesn't exist, use the app's top navigation menus as the module list. Then register, journeys first, in ONE terminal call joined with `&&`:
  - every journey: `python3 qa/ledger.py feat journeys "J<n> <journey name>" --note "<source spec>"`
  - always include the 5 payment flows from `payment_testing.flows` in qa/qa.config.yaml, one feature each: `python3 qa/ledger.py feat journeys "JPAY-P<n> <flow summary>" --note "FULL payment only; see agent Payments rules"`
  - every module, highest business risk first (citation lifecycle/approval/affirmation, legal/payments, reports, events, evidence, admin/roles, jobs, auth last): `python3 qa/ledger.py feat <module-slug> "Module: <Module name>" --note "gaps: <short list>"`
  - `python3 qa/ledger.py note activity "FULL RUN plan: <n> journeys, <m> modules"`
3. Do the Login steps.
4. Phase A - business flows. For each journey, in order:
  - Run it end-to-end on the happy path, logging every transition with `flow`. Execute the productive action and verify the persisted outcome; merely opening the form/detail is not completion. For QA-owned records, create them with the configured prefix and verify the same record again in list/detail/report. Search and report actions are safe read/query operations unless they export or send externally.
  - At every hand-off between modules, verify the data carries over correctly. Examples: the event becomes a citation, queue counts change, the record shows in search and detail, report totals include it.
  - Then run one negative variant at the riskiest step: invalid input, back/refresh mid-flow, double submit, or a role without access.
  - Mark the `J<n>` feature `explored` only after the outcome is verified; otherwise `partial` with dims, the exact remaining action, and blocker. `partial` is not complete.
  - If a step needs approval because it is irreversible, external, bulk, a payment, or changes shared/pre-existing data, ask me. If I say skip, `note blocker`, then continue the surrounding journey, including every safe QA-owned, read-only, list/detail, query, and validation step. Do not abandon the whole journey because one control is unsafe.
5. Phase B - modules. Take the `Module:` items in plan order. Give each one about (timebox divided by number of modules) of active time:
  - Go straight to its routes.
  - Challenge its business rules and Adhoc gaps across the dims (pos, neg, bnd, nav, data, role, ui).
  - Log its pages, and its features as `feat <module-slug> "<feature>"`.
  - Mark the `Module: X` item `explored` only when its meaningful state-changing path or conclusive N/A has been verified; otherwise leave it `partial`, then complete that partial before moving on unless the next step is specifically blocked.
6. Phase C - cross-module consistency: the same counts and totals across Home queues, Events, Citations/Legal and Reports for the same partner and dates; deep links between modules and back; and role access across modules, if more than one role is configured.
7. Checkpoint as usual (I'll continue with /qa-continue, which resumes from the NEXT plan items). Before checkpointing, complete the current productive outcome or stop at a clearly logged blocker; do not checkpoint merely because many pages were visited. Finish when every plan item is explored, blocked or na, or when `status` prints `TIMEBOX USED UP`: `partial` is unfinished and must remain reported as a gap. Re-run J1 as a sanity check, then tell me to run /qa-report. Don't write the report yourself.