
## Task: refresh the app model from the latest automation changes
Read `qa/knowledge/changes.md` (what changed in qa-automation since the app model was built; `framework-inventory.md` is already freshly generated).
- If `qa/knowledge/app-model.md` does NOT exist: build it by following steps 2-4 of `.github/prompts/qa-learn.prompt.md`.
- If it says "No framework or app changes detected": change nothing in the model and end with one line.
- Otherwise UPDATE `qa/knowledge/app-model.md` in place, keeping its format (max ~320 lines):
  1. For each change, open only the spec / page-object files it names (never `.env*`, never run anything).
  2. Update the affected `## Module:` sections: routes, key screens/controls (new/renamed/removed fields), business rules and expected results with `[asserted: <spec>]`, automated coverage, adhoc gaps. Add new modules/journeys; mark removed ones `[removed in <short sha>]` instead of deleting.
  3. Replace (or create, just above `## API to UI map`) a section `## Recent changes` with one line per change the agent must test:
     `- [NEW FIELD|CHANGED FIELD|REMOVED FIELD|NEW BEHAVIOUR|CHANGED RULE|NEW ROUTE|NEWLY SKIPPED|APP CHANGE] <Module>: <what> — test: <how to exercise it> (source: <file>)`
     Merge duplicates; ignore pure refactors that change nothing a user can see.
End with one line: number of changes recorded and modules touched.
