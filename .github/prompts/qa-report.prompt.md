---
name: qa-report
description: Finish the current adhoc QA run and build the final report
agent: Adhoc QA
---
Run `python3 qa/ledger.py status` (`python` on Windows). Make sure every defect YAML you created is filled. Then fill `narrative.yaml` for the current run in one write (facts only), run `python3 qa/ledger.py report` (`python` on Windows), address any WARN that reflects a real gap, and reply with one line: verdict, open defect counts by severity, report path. Use `python3 qa/ledger.py brief` (`python` on Windows) if you need a summary before reporting. Only if the timebox is used up, do the report steps instead.
