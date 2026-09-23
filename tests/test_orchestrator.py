"""
Comprehensive automated unit tests for the akstack orchestration engine.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from orchestrator.engine import OrchestratorEngine
from orchestrator.graph import DependencyGraph
from orchestrator.models import GATE_ORDER, Task, TaskStatus, TaskType, Track
from orchestrator.parser import MarkdownParser


SAMPLE_TODOS = """
# Test Project — Task Ledger

## Phase 1 — Discovery

- [ ] **P1-T001** ★ Produce structured capability map
  - **Owner:** requirement-analyzer
  - **Deps:** —
  - **Files:** `plan.md`, `docs/capabilities.md`
  - **Do:** Analyze requirements
  - **Accept:** Capability matrix populated
  - **Verify:** `python -m unittest test_plan`

- [~] **P1-T002** 🧑 HUMAN Review domain rules
  - **Owner:** senior-product-manager
  - **Deps:** P1-T001
  - **Files:** `plan.md`
  - **Do:** Sign off on section 3
  - **Accept:** Human approval
  - **Verify:** manual review

## Phase 5 — Quality & Security

- [x] **P5-G0-ML** Model eval gate
  - **Owner:** senior-mlops-engineer
  - **Deps:** —
  - **Files:** —
  - **Do:** Confirm lineage
  - **Accept:** Metrics clear threshold
  - **Verify:** manual review

- [ ] **P5-G1** Test Gate
  - **Owner:** senior-qa-architect
  - **Deps:** P1-T002
  - **Files:** —
  - **Do:** Run test suite
  - **Accept:** Green tests
  - **Verify:** pytest

- [ ] **P5-G4-A11Y** Accessibility gate
  - **Owner:** senior-accessibility-engineer
  - **Deps:** P5-G1
  - **Files:** —
  - **Do:** WCAG audit
  - **Accept:** AA compliance
  - **Verify:** manual review
"""


class TestMarkdownParser(unittest.TestCase):

    def test_parse_sample_todos(self):
        tasks = MarkdownParser.parse_todos(SAMPLE_TODOS)
        self.assertEqual(len(tasks), 5)

        t1 = tasks[0]
        self.assertEqual(t1.id, "P1-T001")
        self.assertEqual(t1.title, "Produce structured capability map")
        self.assertEqual(t1.status, TaskStatus.PENDING)
        self.assertTrue(t1.is_senior)
        self.assertEqual(t1.owner, "requirement-analyzer")
        self.assertEqual(t1.files, ["plan.md", "docs/capabilities.md"])
        self.assertEqual(t1.deps, [])

        t2 = tasks[1]
        self.assertEqual(t2.id, "P1-T002")
        self.assertEqual(t2.status, TaskStatus.IN_PROGRESS)
        self.assertTrue(t2.is_human)
        self.assertEqual(t2.deps, ["P1-T001"])

        g0 = tasks[2]
        self.assertEqual(g0.id, "P5-G0-ML")
        self.assertEqual(g0.task_type, TaskType.GATE)
        self.assertEqual(g0.gate_key, "G0-ML")
        self.assertEqual(g0.status, TaskStatus.COMPLETED)

        g1 = tasks[3]
        self.assertEqual(g1.id, "P5-G1")
        self.assertEqual(g1.task_type, TaskType.GATE)

        a11y = tasks[4]
        self.assertEqual(a11y.id, "P5-G4-A11Y")
        self.assertEqual(a11y.task_type, TaskType.GATE)
        self.assertEqual(a11y.gate_key, "G4-A11Y")
        self.assertEqual(a11y.phase, 5)

    def test_update_status(self):
        sample_md = "- [ ] **P1-T001** Task 1\n- [ ] **P1-T002** Task 2\n"
        updated_md, ok = MarkdownParser.update_task_status(sample_md, "P1-T001", TaskStatus.IN_PROGRESS)
        self.assertTrue(ok)
        self.assertIn("- [~] **P1-T001**", updated_md)
        self.assertIn("- [ ] **P1-T002**", updated_md)

        completed_md, ok2 = MarkdownParser.update_task_status(updated_md, "P1-T001", TaskStatus.COMPLETED)
        self.assertTrue(ok2)
        self.assertIn("- [x] **P1-T001**", completed_md)

    def test_skip_verify(self):
        self.assertTrue(MarkdownParser.should_skip_verify("manual review"))
        self.assertTrue(MarkdownParser.should_skip_verify("—"))
        self.assertFalse(MarkdownParser.should_skip_verify("pytest"))

    def test_clean_verify_and_change_ids(self):
        tasks = MarkdownParser.parse_todos(
            "- [ ] **P2-C001** Update contract\n"
            "  - **Owner:** coordinator\n"
            "  - **Deps:** —\n"
            "  - **Files:** `plan.md`\n"
            "  - **Do:** update\n"
            "  - **Accept:** changed\n"
            "  - **Verify:** `python -m unittest discover -s tests`\n"
        )
        self.assertEqual(tasks[0].task_type, TaskType.CHANGE)
        self.assertEqual(tasks[0].verify, "python -m unittest discover -s tests")
        self.assertTrue(MarkdownParser.TASK_ID_PATTERN.fullmatch("P5-G4-CRO"))

    def test_parse_plan_track(self):
        plan = MarkdownParser.parse_plan(
            "# Widget — Plan\n\n## 0. Track\n\n**Hybrid** — decides agents\n\n"
            "## 3. Domain & Hard Rules\n\n1. Money is integer cents.\n"
        )
        self.assertEqual(plan.project_name, "Widget")
        self.assertEqual(plan.track, "Hybrid")
        self.assertTrue(any("integer" in r.lower() for r in plan.hard_rules))

    def test_track_parse(self):
        self.assertEqual(Track.parse("hybrid"), Track.HYBRID)
        self.assertEqual(Track.parse("AI/ML"), Track.AI_ML)
        self.assertEqual(Track.parse("web"), Track.PRODUCT_WEB)


class TestDependencyGraph(unittest.TestCase):

    def test_cycle_detection(self):
        tA = Task(id="A", title="A", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["C"])
        tB = Task(id="B", title="B", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["A"])
        tC = Task(id="C", title="C", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["B"])
        graph = DependencyGraph([tA, tB, tC])
        cycle = graph.detect_cycles()
        self.assertIsNotNone(cycle)
        self.assertIn("A", cycle)
        self.assertIn("B", cycle)
        self.assertIn("C", cycle)

    def test_runnable_tasks(self):
        t1 = Task(id="T1", title="T1", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.COMPLETED)
        t2 = Task(id="T2", title="T2", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["T1"])
        t3 = Task(id="T3", title="T3", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["T2"])
        graph = DependencyGraph([t1, t2, t3])
        runnable = graph.get_runnable_tasks()
        self.assertEqual(len(runnable), 1)
        self.assertEqual(runnable[0].id, "T2")

    def test_parallel_waves_disjoint_files(self):
        t1 = Task(id="T1", title="T1", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, files=["src/a.ts"])
        t2 = Task(id="T2", title="T2", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, files=["src/b.ts"])
        t3 = Task(id="T3", title="T3", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, files=["src/a.ts"])
        graph = DependencyGraph([t1, t2, t3])
        waves = graph.schedule_parallel_waves([t1, t2, t3])
        self.assertEqual(len(waves), 2)
        wave1_ids = [t.id for t in waves[0]]
        self.assertIn("T1", wave1_ids)
        self.assertIn("T2", wave1_ids)
        self.assertEqual(waves[1][0].id, "T3")

    def test_empty_files_not_parallel_safe(self):
        t1 = Task(id="T1", title="T1", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, files=["src/a.ts"])
        t2 = Task(id="T2", title="T2", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, files=[])
        graph = DependencyGraph([t1, t2])
        waves = graph.schedule_parallel_waves([t1, t2])
        self.assertEqual(len(waves), 2)

    def test_to_mermaid(self):
        t1 = Task(id="P1-T001", title="Setup", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.COMPLETED)
        t2 = Task(id="P1-T002", title="Build", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["P1-T001"])
        graph = DependencyGraph([t1, t2])
        mm = graph.to_mermaid()
        self.assertIn("flowchart TD", mm)
        self.assertIn("P1-T001 --> P1-T002", mm)

    def test_topological_order(self):
        t1 = Task(id="T1", title="T1", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING)
        t2 = Task(id="T2", title="T2", phase=1, task_type=TaskType.STANDARD, status=TaskStatus.PENDING, deps=["T1"])
        order = DependencyGraph([t2, t1]).topological_order()
        self.assertIsNotNone(order)
        self.assertEqual([t.id for t in order], ["T1", "T2"])


class TestOrchestratorEngineIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_root = Path(__file__).resolve().parent.parent
        shutil.copytree(self.repo_root / "templates", self.test_dir / "templates")
        shutil.copytree(self.repo_root / "agents", self.test_dir / "agents")
        shutil.copytree(self.repo_root / "phases", self.test_dir / "phases")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init_and_workflow(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        ok, msg = engine.init_project("TestApp", track="Hybrid")
        self.assertTrue(ok, msg)

        status = engine.get_status()
        self.assertEqual(status["project_name"], "TestApp")
        self.assertEqual(status["track"], "Hybrid")

        t_first = status["next_task"]
        self.assertIsNotNone(t_first)
        self.assertEqual(t_first.id, "P1-T001")
        ok, _ = engine.start_task(t_first.id)
        self.assertTrue(ok)

        status2 = engine.get_status()
        self.assertEqual(len(status2["in_progress_tasks"]), 1)

        ok, _ = engine.complete_task(t_first.id, run_verify=False, git_commit=False)
        self.assertTrue(ok)

        status3 = engine.get_status()
        self.assertEqual(status3["completed_tasks"], 1)
        self.assertEqual(status3["next_task"].id, "P1-T002")

        t_dummy = "- [ ] **P1-T999** Dummy\n  - **Owner:** senior-backend-engineer\n"
        with open(engine.todos_file, "a", encoding="utf-8") as handle:
            handle.write("\n" + t_dummy)

        ok, _ = engine.fail_task("P1-T999", "Failed test expectation")
        self.assertTrue(ok)
        status4 = engine.get_status()
        self.assertEqual(len(status4["blocked_tasks"]), 1)

        ok, _ = engine.reset_task("P1-T999", reason="fixed fixture")
        self.assertTrue(ok)
        self.assertEqual(engine._find_task("P1-T999").status, TaskStatus.PENDING)

    def test_init_refuses_overwrite(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        ok, _ = engine.init_project("Once", track="Product/Web")
        self.assertTrue(ok)
        ok, msg = engine.init_project("Twice", track="Product/Web")
        self.assertFalse(ok)
        self.assertIn("overwrite", msg.lower())
        ok, _ = engine.init_project("Twice", track="AI/ML", force=True)
        self.assertTrue(ok)
        self.assertEqual(engine.load_plan().track, "AI/ML")

    def test_init_from_empty_workspace_copies_framework_assets(self):
        empty = self.test_dir / "empty-project"
        empty.mkdir()
        engine = OrchestratorEngine(workspace_root=empty)
        ok, msg = engine.init_project("Copied", track="Hybrid")
        self.assertTrue(ok, msg)
        self.assertTrue((empty / "agents" / "coordinator.md").exists())
        self.assertTrue((empty / "phases" / "PHASE-3-DESIGN.md").exists())
        self.assertTrue((empty / "playwright.config.ts").exists())
        self.assertTrue((empty / ".github" / "workflows" / "frontend-quality.yml").exists())
        self.assertTrue((empty / "docs" / "analytics" / "measurement-plan.md").exists())
        self.assertTrue(engine.doctor()["ok"])

    def test_lint_system(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("LintTest", track="Product/Web")
        errors = engine.lint()
        self.assertEqual(errors, [])

    def test_start_rejects_unmet_deps_and_human(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Gates", track="Product/Web")
        ok, msg = engine.start_task("P1-T002")
        self.assertFalse(ok)
        self.assertIn("Unmet", msg)

        content = engine.todos_file.read_text(encoding="utf-8")
        for tid in ("P1-T001", "P1-T002", "P1-T003", "P1-T004", "P1-T005", "P1-T006"):
            content, _ = MarkdownParser.update_task_status(content, tid, TaskStatus.COMPLETED)
        engine.todos_file.write_text(content, encoding="utf-8")
        ok, msg = engine.start_task("P1-G1")
        self.assertFalse(ok)
        self.assertIn("HUMAN", msg)

    def test_stop_blocks_start(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Stop", track="Product/Web")
        engine.handoff("P1-T001", "credential", "need production API key")
        self.assertTrue(engine.stop_file.exists())
        ok, msg = engine.start_task("P1-T001")
        self.assertFalse(ok)
        self.assertIn("STOP", msg)

    def test_resume_clears_stop_with_note(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Resume", track="Product/Web")
        engine.handoff("P1-T001", "business decision", "pricing is not approved")
        ok, msg = engine.resume("Product owner approved the pricing decision", git_commit=False)
        self.assertTrue(ok, msg)
        self.assertFalse(engine.stop_file.exists())
        ok, msg = engine.resume("no-op", git_commit=False)
        self.assertTrue(ok, msg)

    def test_human_approval_requires_evidence(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Approval", track="Product/Web")
        content = engine.todos_file.read_text(encoding="utf-8")
        for tid in ("P1-T001", "P1-T002", "P1-T003", "P1-T004", "P1-T005", "P1-T006", "P1-T007", "P1-T008", "P1-T009"):
            content, _ = MarkdownParser.update_task_status(content, tid, TaskStatus.COMPLETED)
        engine.todos_file.write_text(content, encoding="utf-8")
        ok, msg = engine.approve_task("P1-G1", notes="Approved by product owner", git_commit=False)
        self.assertFalse(ok)
        self.assertIn("evidence", msg.lower())
        evidence = self.test_dir / "approval.md"
        evidence.write_text("approved", encoding="utf-8")
        ok, msg = engine.approve_task("P1-G1", notes="Approved by product owner", evidence="approval.md", git_commit=False)
        self.assertTrue(ok, msg)
        self.assertEqual(engine._find_task("P1-G1").status, TaskStatus.COMPLETED)

    def test_phase_skipping_is_rejected(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Order", track="Product/Web")
        content = engine.todos_file.read_text(encoding="utf-8")
        content += """

## Phase 4 — Build

- [ ] **P4-T001** Build too early
  - **Owner:** senior-frontend-engineer
  - **Deps:** —
  - **Files:** `src/app.tsx`
  - **Do:** build
  - **Accept:** works
  - **Verify:** manual review
"""
        engine.todos_file.write_text(content, encoding="utf-8")
        ok, msg = engine.start_task("P4-T001")
        self.assertFalse(ok)
        self.assertIn("Phase 1", msg)

    def test_frontend_contract(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Frontend", track="Product/Web")
        (self.test_dir / "design-system" / "MASTER.md").write_text(
            "Color Typography Spacing Motion component Breakpoint\nNo placeholders.", encoding="utf-8"
        )
        (self.test_dir / "docs" / "design" / "home.md").write_text(
            "Visual Direction\nResponsive States\nInteraction States\nAccessibility\nInstrumentation", encoding="utf-8"
        )
        (self.test_dir / "docs" / "discovery").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "docs" / "discovery" / "funnel.md").write_text("Acquisition to activation funnel.", encoding="utf-8")
        (self.test_dir / "docs" / "analytics" / "measurement-plan.md").write_text("North-Star\nFunnel\nEvent Contract\nExperiment", encoding="utf-8")
        (self.test_dir / "docs" / "seo" / "technical-seo.md").write_text("Public Route\nMetadata\nSitemap\nJSON-LD", encoding="utf-8")
        (self.test_dir / "docs" / "design" / "accessibility-spec.md").write_text("Automated\nManual\nDecision", encoding="utf-8")
        (self.test_dir / "docs" / "design" / "component-traceability.md").write_text("Route to component and token mapping.", encoding="utf-8")
        (self.test_dir / "docs" / "performance" / "report.md").write_text("Metrics\nReview\nDecision", encoding="utf-8")
        report = engine.frontend_check("all")
        self.assertTrue(report["ok"], report["errors"])

    def test_frontend_contract_blocks_component_drift(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("FrontendDrift", track="Product/Web")
        (self.test_dir / "design-system" / "MASTER.md").write_text(
            "Color Typography Spacing Motion component Breakpoint", encoding="utf-8"
        )
        (self.test_dir / "docs" / "design" / "home.md").write_text(
            "Visual Direction Responsive States Interaction States Accessibility Instrumentation", encoding="utf-8"
        )
        (self.test_dir / "docs" / "design" / "component-traceability.md").write_text("Mapped", encoding="utf-8")
        (self.test_dir / "src").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "src" / "Button.tsx").write_text("export const Button = () => <button style={{color: '#fff'}} />", encoding="utf-8")
        report = engine.frontend_check("design")
        self.assertFalse(report["ok"])
        self.assertTrue(any("hardcoded hex" in error for error in report["errors"]))

    def test_gate_evidence_rejects_placeholder_report(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Evidence", track="Product/Web")
        report = self.test_dir / "report.md"
        report.write_text("# Report\n{{fill this in}}", encoding="utf-8")
        paths, error = engine._safe_evidence("report.md")
        self.assertEqual(paths, [])
        self.assertIn("placeholders", error)

    def test_frontend_gate_sequence_requires_contracts(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("FrontendGates", track="Product/Web")
        ledger = """# FrontendGates — Task Ledger

## Phase 5 — Quality

- [x] **P5-T001** Build complete
  - **Owner:** senior-frontend-engineer
  - **Deps:** —
  - **Files:** `src/app.tsx`
  - **Do:** build
  - **Accept:** works
  - **Verify:** manual review

- [x] **P5-G1** Tests
  - **Owner:** senior-qa-architect
  - **Deps:** P5-T001
  - **Files:** —
  - **Do:** test
  - **Accept:** green
  - **Verify:** manual review
- [x] **P5-G2** Code review
  - **Owner:** code-reviewer
  - **Deps:** P5-G1
  - **Files:** —
  - **Do:** review
  - **Accept:** clean
  - **Verify:** manual review
- [x] **P5-G3** Security
  - **Owner:** senior-security-engineer
  - **Deps:** P5-G2
  - **Files:** —
  - **Do:** review
  - **Accept:** clean
  - **Verify:** manual review
- [x] **P5-G3-P** Privacy
  - **Owner:** senior-privacy-engineer
  - **Deps:** P5-G3
  - **Files:** —
  - **Do:** review
  - **Accept:** clean
  - **Verify:** manual review
- [ ] **P5-G4** Visual
  - **Owner:** visual-qa
  - **Deps:** P5-G3-P
  - **Files:** —
  - **Do:** review
  - **Accept:** clean
  - **Verify:** manual review
- [ ] **P5-G4-CRO** Growth
  - **Owner:** growth-cro-engineer
  - **Deps:** P5-G4
  - **Files:** —
  - **Do:** review
  - **Accept:** clean
  - **Verify:** manual review
"""
        engine.todos_file.write_text(ledger, encoding="utf-8")
        (self.test_dir / "design-system" / "MASTER.md").write_text("Color Typography Spacing Motion component Breakpoint", encoding="utf-8")
        (self.test_dir / "docs" / "design" / "home.md").write_text(
            "Visual Direction Responsive States Interaction States Accessibility Instrumentation", encoding="utf-8"
        )
        (self.test_dir / "docs" / "design" / "component-traceability.md").write_text("mapped", encoding="utf-8")
        (self.test_dir / "docs" / "qa" / "visual-report.md").write_text("visual pass", encoding="utf-8")
        (self.test_dir / "docs" / "analytics" / "measurement-plan.md").write_text("North-Star Funnel Event Contract Experiment", encoding="utf-8")
        (self.test_dir / "docs" / "seo" / "technical-seo.md").write_text("Public Route Metadata Sitemap JSON-LD", encoding="utf-8")
        (self.test_dir / "docs" / "discovery").mkdir(parents=True, exist_ok=True)
        (self.test_dir / "docs" / "discovery" / "funnel.md").write_text("funnel", encoding="utf-8")
        (self.test_dir / "docs" / "analytics" / "cro-report.md").write_text("cro pass", encoding="utf-8")

        ok, msg = engine.run_gate("P5-G4", evidence="docs/qa/visual-report.md")
        self.assertTrue(ok, msg)
        ok, msg = engine.run_gate("P5-G4-CRO", evidence="docs/analytics/cro-report.md")
        self.assertTrue(ok, msg)

    def test_shell_operators_are_rejected(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        command, error = engine._parse_command("python -m unittest && echo unsafe")
        self.assertIsNone(command)
        self.assertIn("shell operators", error)

    def test_gate_cannot_be_completed_with_complete_command(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("GateType", track="Product/Web")
        ok, msg = engine.complete_task("P1-G1", run_verify=False, git_commit=False)
        self.assertFalse(ok)
        self.assertIn("approve", msg.lower())

    def test_packet_json(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Packet", track="Hybrid")
        task = engine.get_status()["next_task"]
        packet = engine.build_packet(task)
        self.assertEqual(packet["task_id"], "P1-T001")
        self.assertEqual(packet["owner"], "requirement-analyzer")
        self.assertIn("plan.md", packet["read_first"])
        json.dumps(packet)

    def test_gate_blocks_on_findings_and_order(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Secure", track="Product/Web")
        ledger = """# Secure — Task Ledger

## Phase 5 — Quality & Security

- [x] **P5-T001** Implement feature
  - **Owner:** senior-backend-engineer
  - **Deps:** —
  - **Files:** `src/app.ts`
  - **Do:** Build it
  - **Accept:** Works
  - **Verify:** manual review

- [ ] **P5-G1** Test Gate
  - **Owner:** senior-qa-architect
  - **Deps:** P5-T001
  - **Files:** —
  - **Do:** Tests
  - **Accept:** Green
  - **Verify:** manual review

- [ ] **P5-G2** Code review
  - **Owner:** code-reviewer
  - **Deps:** P5-G1
  - **Files:** —
  - **Do:** Review
  - **Accept:** Clean
  - **Verify:** manual review
"""
        engine.todos_file.write_text(ledger, encoding="utf-8")
        ok, msg = engine.run_gate("P5-G2")
        self.assertFalse(ok)
        self.assertIn("P5-G1", msg)

        evidence = self.test_dir / "docs" / "qa" / "test-report.md"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text("tests passed", encoding="utf-8")
        ok, msg = engine.run_gate("P5-G1", evidence="docs/qa/test-report.md")
        self.assertTrue(ok, msg)

        ok, fid_msg = engine.file_finding(
            gate_id="P5-G2",
            title="Swallowed error",
            owner="senior-backend-engineer",
            severity="High",
            file_path="src/app.ts",
            issue="empty catch",
            fix="surface the error",
        )
        self.assertTrue(ok, fid_msg)
        self.assertIsNotNone(engine._find_task("P5-F01"))

        ok, msg = engine.run_gate("P5-G2")
        self.assertFalse(ok)
        self.assertIn("open finding", msg.lower())

        ok, msg = engine.start_task("P5-F01")
        self.assertTrue(ok, msg)
        ok, msg = engine.complete_task("P5-F01", run_verify=True, git_commit=False)
        self.assertTrue(ok, msg)
        ok, msg = engine.run_gate("P5-G2", evidence="docs/qa/test-report.md")
        self.assertTrue(ok, msg)

    def test_g0_ml_skipped_on_web_track(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("WebOnly", track="Product/Web")
        ledger = """# WebOnly — Task Ledger

## Phase 5

- [x] **P5-T001** Done
  - **Owner:** senior-backend-engineer
  - **Deps:** —
  - **Files:** `src/a.ts`
  - **Do:** x
  - **Accept:** y
  - **Verify:** manual review

- [ ] **P5-G0-ML** ML eval
  - **Owner:** senior-mlops-engineer
  - **Deps:** P5-T001
  - **Files:** —
  - **Do:** eval
  - **Accept:** threshold
  - **Verify:** manual review
"""
        engine.todos_file.write_text(ledger, encoding="utf-8")
        ok, msg = engine.run_gate("P5-G0-ML")
        self.assertTrue(ok, msg)
        self.assertIn("skipped", msg.lower())
        self.assertEqual(engine._find_task("P5-G0-ML").status, TaskStatus.COMPLETED)

    def test_doctor(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("Doc", track="Product/Web")
        report = engine.doctor()
        self.assertTrue(report["ok"], report["lint_errors"])

    def test_status_json_serializable(self):
        engine = OrchestratorEngine(workspace_root=self.test_dir)
        engine.init_project("JSON", track="Product/Web")
        payload = engine.status_json()
        json.dumps(payload)
        self.assertEqual(payload["next_task"]["id"], "P1-T001")

    def test_gate_order_constant(self):
        self.assertIn("G3-P", GATE_ORDER)
        self.assertIn("G4-CRO", GATE_ORDER)
        self.assertIn("G4-A11Y", GATE_ORDER)
        self.assertLess(GATE_ORDER.index("G3"), GATE_ORDER.index("G3-P"))
        self.assertLess(GATE_ORDER.index("G4"), GATE_ORDER.index("G4-CRO"))

    def test_agent_roster_count(self):
        briefs = [p for p in (self.repo_root / "agents").glob("*.md") if p.name != "TEAM.md"]
        self.assertEqual(len(briefs), 42)
        for brief in briefs:
            text = brief.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---"), brief.name)
            self.assertIn(f"name: {brief.stem}", text)


if __name__ == "__main__":
    unittest.main()
