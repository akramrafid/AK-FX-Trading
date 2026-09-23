# Phase 0 — Setup

**Objective:** Ensure all development tools, linters, external skills, and akstack templates are verified in place before project-specific requirements are written.

## Checklist

- [ ] Global coding discipline rules verified: `~/.gemini/GEMINI.md`
- [ ] Python 3.10+ runtime available for orchestrator CLI (`python --version`)
- [ ] Node.js 18+ runtime available (`node --version`)
- [ ] Frontend tooling verified for Product/Web and Hybrid: `python -m orchestrator.cli doctor --frontend`
- [ ] `ui-ux-pro-max` installed at an approved version (`npm i -g ui-ux-pro-max-cli@<version>` & `uipro init`)
- [ ] `design-system-skill` available (for projects with pre-existing brand assets)
- [ ] `Impeccable` installed (`npx impeccable install --providers=antigravity --scope=global`)
- [ ] `akstack` CLI verified: run `python -m orchestrator.cli lint`
- [ ] Project initialized:
  ```bash
  python -m orchestrator.cli init "My Project" --track Product/Web
  ```
- [ ] `agents/` present in root (all 42 role briefs + `TEAM.md`)
- [ ] Coordinator brief present: `agents/coordinator.md`
- [ ] Browser evidence kit copied: `playwright.config.ts`, `docs/qa/frontend-quality-checklist.md`
- [ ] Frontend CI workflow present for Product/Web and Hybrid: `.github/workflows/frontend-quality.yml`

See `integrations/EXTERNAL-TOOLS.md` for exact tool install and verification commands.

## Exit Criteria

`plan.md`, `ToDos.md`, `PROGRESS.md` exist. `agents/` directory is present and `python -m orchestrator.cli lint` passes with 0 errors. No product-specific feature code is written yet.

## Next Phase

`phases/PHASE-1-DISCOVERY.md`
