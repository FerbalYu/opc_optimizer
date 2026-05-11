# Autonomous Workflow

## Operating Rule
After the initial direction is set, work autonomously. Ask the user only for blockers involving credentials, irreversible actions, paid services, compliance/legal risk, or expensive-to-reverse product decisions.

## Loop
1. Plan the next smallest coherent unit.
2. Code the unit.
3. Test relevant behavior.
4. Review the diff for regressions, missing tests, UX issues, and scope drift.
5. Record suggestions separately from blockers.
6. Update `docs/PROGRESS.md` and repeat.

## Definition of Done
- Acceptance criteria in `DESIGN.md` are complete.
- Relevant tests/checks pass or documented blockers explain why they could not run.
- `docs/PROGRESS.md` reflects final state.
