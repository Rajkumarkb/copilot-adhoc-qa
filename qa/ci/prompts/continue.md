
## Task: continue the full-application run
Run `python3 qa/ledger.py brief && python3 qa/ledger.py status`. Do the Login steps only if you are not signed in (the browser profile usually keeps the session; check with one `browser_find`). Resume from the NEXT plan items in this order: `changes` (CHANGE …), `journeys`, `Module: …` items, then `cross` (Phase C), following `.github/prompts/qa-full.prompt.md` for how to test each kind. Keep cycling until the 40-action checkpoint, then end with one line.
