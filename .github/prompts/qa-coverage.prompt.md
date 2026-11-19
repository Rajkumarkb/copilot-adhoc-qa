---
name: qa-coverage
description: Map every screen of the app and report which UI controls/pages the automation framework does NOT cover
agent: Adhoc QA
---
Goal: a UI-vs-automation coverage gap report. This is a mapping session, not deep testing.

1. Run `python3 qa/setup.py` (act on FIX/RESTART as in /qa-start). If `python3 qa/ledger.py status` says there is no active run, run `python3 qa/ledger.py init`. Run `python3 qa/coverage.py status` to see which pages are already mapped; don't re-map them.
2. Do the Login steps.
3. Visit every page reachable from the navigation, module by module (use `qa/knowledge/app-model.md` routes if present): menus and sub-menus, tabs, and for list pages also the first row's detail page and any "New/Add" form (open it, don't submit). Never click ASK BEFORE controls.
4. On each page: one `browser_snapshot`, then ONE command listing every interactive control and table column in it as `role:name` exactly as in the snapshot:
   `python3 qa/coverage.py ui <page-id> --url <path> --module <Module> --controls "button:Execute; combobox:Partner; textbox:Start Date; columnheader:Plate; tab:History"`
   Skip the top navigation bar after the first page. Also log the page with `python3 qa/ledger.py page <page-id> --url <path> --module <Module> --status visited`.
5. At the ~40-action checkpoint, or when every module is mapped, run `python3 qa/coverage.py report` and reply with its one-line summary plus the 5 most important gaps (critical screens or fields with no automation). If modules remain unmapped, tell me to run /qa-coverage again in a new chat.
