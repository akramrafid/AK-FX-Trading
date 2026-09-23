# AGENTS.md — working in this repository

This repo *is* akstack. Product work happens in clones after `akstack init`.

## Commands

```bash
python -m unittest discover -s tests -v
python -m orchestrator.cli --help
python -m orchestrator doctor
```

Python ≥ 3.10. Zero third-party dependencies.

## Layout

- `orchestrator/` — CLI engine (parser, DAG, gates, packets)
- `agents/` — 42 role briefs + `TEAM.md`
- `phases/` — Phase 0–6 specs
- `templates/` — plan / ToDos / PROGRESS / ADR / design-system / screen specs / measurement / SEO / QA
- `tests/` — orchestrator unit tests (must stay green)

## Rules

- Do not commit secrets. `STOP` is local and gitignored.
- Do not `git add .` from complete; the engine stages declared files only.
- Review-only roles never edit production code.
- Keep agent frontmatter `name:` equal to the filename stem (lint checks this).
- Task IDs: `P<n>-T<nnn>`, `P<n>-F<nn>`, `P<n>-C<nn>`, `P<n>-G<n>`, `P<n>-G<n>-SUFFIX` (`P5-G4-A11Y`, `P5-G0-ML`, `P5-G3-P`).
- Product/Web and Hybrid frontend work must pass `python -m orchestrator.cli frontend-check --area all` before the quality gates.
- Gate completion requires a workspace-relative `--evidence` report; use `approve` for HUMAN tasks.
- `Verify:` commands are one executable plus arguments; shell operators (`&&`, pipes, redirects) are rejected.
- The orchestrator serializes ledger/Git mutations with `.akstack.lock`; do not edit `ToDos.md` or `PROGRESS.md` concurrently by hand.
