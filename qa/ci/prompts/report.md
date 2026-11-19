
## Task: write the final report for this CI run
Do the steps of `.github/prompts/qa-report.prompt.md`. In `narrative.yaml`:
- `scope`: "Automated post-merge full-application adhoc run (GitHub Actions)" plus which CHANGE items, journeys and modules were covered.
- `exclusions`: everything skipped as `SKIPPED-APPROVAL`, plus plan items not reached.
- `major_blockers`: any `LOGIN-FAILED` or environment blockers from the ledger notes.
- Be strictly factual about what this run actually did; it is unattended, so nothing was approved by a human.
End with one line: verdict and open defect counts.
