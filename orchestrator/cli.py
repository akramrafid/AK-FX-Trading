"""
Command Line Interface (CLI) for akstack orchestration.
"""

import argparse
import json
import os
import sys

from .engine import OrchestratorEngine
from .graph import DependencyGraph
from .models import Task

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_RESET = "\033[0m"


def colorize(text: str, color: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"{color}{text}{COLOR_RESET}"


def _dump(payload) -> int:
    print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_status(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        return _dump(engine.status_json())

    status = engine.get_status()
    print()
    print(colorize(f"=== Akram-Stack: {status['project_name']} ===", COLOR_BOLD + COLOR_CYAN))
    print(f"Track: {colorize(status['track'], COLOR_BOLD)} | Active Phase: {colorize(f'Phase {status['active_phase']}', COLOR_YELLOW)}")
    if status.get("stop_active"):
        print(colorize("STOP file present — human handoff is active.", COLOR_RED))
    print()

    total = status["total_tasks"]
    comp = status["completed_tasks"]
    pct = (comp / total * 100) if total > 0 else 0
    print(f"Progress: [{comp}/{total}] {pct:.1f}% complete")

    print(f"  • Completed   : {colorize(str(comp), COLOR_GREEN)}")
    print(f"  • In Progress : {colorize(str(len(status['in_progress_tasks'])), COLOR_YELLOW)}")
    print(f"  • Pending     : {colorize(str(status['pending_tasks']), COLOR_DIM)}")
    print(f"  • Blocked     : {colorize(str(len(status['blocked_tasks'])), COLOR_RED)}")
    print()

    if status["in_progress_tasks"]:
        print(colorize("▶ Active In-Progress Tasks:", COLOR_YELLOW))
        for t in status["in_progress_tasks"]:
            senior = colorize("★ ", COLOR_YELLOW) if t.is_senior else ""
            print(f"  - {senior}{colorize(t.id, COLOR_BOLD)}: {t.title} (Owner: {t.owner})")
        print()

    if status["blocked_tasks"]:
        print(colorize("✖ Blocked Tasks (- [!]):", COLOR_RED))
        for t in status["blocked_tasks"]:
            print(f"  - {colorize(t.id, COLOR_BOLD)}: {t.title} (Owner: {t.owner})")
        print()

    next_t = status["next_task"]
    if next_t:
        senior = colorize("★ ", COLOR_YELLOW) if next_t.is_senior else ""
        print(colorize("➜ Next Runnable Task:", COLOR_GREEN))
        print(f"  ID    : {senior}{colorize(next_t.id, COLOR_BOLD)}")
        print(f"  Title : {next_t.title}")
        print(f"  Owner : {colorize(next_t.owner or 'Unassigned', COLOR_CYAN)}")
        if next_t.files:
            print(f"  Files : {', '.join(next_t.files)}")
        if next_t.verify:
            print(f"  Verify: {colorize(next_t.verify, COLOR_DIM)}")
    else:
        if status.get("all_complete"):
            print(colorize("[OK] All tasks in the ledger are COMPLETED!", COLOR_GREEN))
        else:
            print(colorize("Waiting on dependencies or human intervention.", COLOR_YELLOW))

    print()
    return 0


def cmd_next(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    waves = engine.get_next(phase=args.phase, parallel=args.parallel)
    if getattr(args, "json", False):
        payload = [[t.to_dict() for t in wave] for wave in waves]
        return _dump(payload)

    if not waves:
        print(colorize("No runnable tasks found for the selected criteria.", COLOR_YELLOW))
        return 0

    if not args.parallel:
        task = waves[0][0]
        _print_task(task)
        return 0

    print(colorize(f"Scheduled {len(waves)} conflict-free wave(s):", COLOR_BOLD + COLOR_CYAN))
    for idx, wave in enumerate(waves, 1):
        print(f"\n{colorize(f'=== Wave {idx} ({len(wave)} parallel task[s]) ===', COLOR_BOLD)}")
        for t in wave:
            senior = "★ " if t.is_senior else ""
            files_str = f" [Files: {', '.join(t.files)}]" if t.files else ""
            print(f"  • {senior}{colorize(t.id, COLOR_BOLD)}: {t.title} ({colorize(t.owner, COLOR_CYAN)}){colorize(files_str, COLOR_DIM)}")
    return 0


def _print_task(task: Task) -> None:
    senior = "★ " if task.is_senior else ""
    human = "HUMAN " if task.is_human else ""
    print(colorize(f"NEXT TASK: {senior}{human}{task.id} - {task.title}", COLOR_BOLD + COLOR_GREEN))
    print(f"Owner: {task.owner}")
    print(f"Files: {', '.join(task.files) if task.files else 'None specified'}")
    print(f"Do: {task.do}")
    print(f"Accept: {task.accept}")
    print(f"Verify: {task.verify}")


def cmd_packet(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    task_id = args.task_id
    if not task_id:
        waves = engine.get_next()
        if not waves:
            print(colorize("No runnable task to packetize.", COLOR_YELLOW))
            return 1
        task = waves[0][0]
    else:
        task = engine._find_task(task_id)
        if not task:
            print(colorize(f"Task {task_id} not found.", COLOR_RED))
            return 1
    packet = engine.build_packet(task)
    return _dump(packet)


def cmd_start(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.start_task(args.task_id)
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_complete(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.complete_task(
        task_id=args.task_id,
        run_verify=not args.no_verify,
        git_commit=not args.no_commit,
        verification_notes=args.notes or "",
    )
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_approve(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.approve_task(
        task_id=args.task_id,
        notes=args.notes,
        evidence=args.evidence or "",
        git_commit=not args.no_commit,
    )
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_fail(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.fail_task(task_id=args.task_id, error_msg=args.error)
    print(colorize(msg, COLOR_YELLOW if success else COLOR_RED))
    return 0 if success else 1


def cmd_reset(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.reset_task(args.task_id, reason=args.reason or "")
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_gate(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.run_gate(gate_id=args.gate_id, evidence=args.evidence or "", notes=args.notes or "")
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_finding(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.file_finding(
        gate_id=args.gate_id,
        title=args.title,
        owner=args.owner,
        severity=args.severity,
        file_path=args.file,
        issue=args.issue,
        fix=args.fix,
    )
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_handoff(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.handoff(args.task_id, args.blocked_on, args.why)
    print(colorize(msg, COLOR_YELLOW if success else COLOR_RED))
    return 0 if success else 1


def cmd_resume(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.resume(args.notes, git_commit=not args.no_commit)
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def cmd_question(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.question(args.task_id, args.ambiguity, args.risk, args.recommended)
    print(colorize(msg, COLOR_YELLOW if success else COLOR_RED))
    return 0 if success else 1


def cmd_lint(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    errors = engine.lint()
    if getattr(args, "json", False):
        return _dump({"ok": not errors, "errors": errors})
    print(colorize("Running akstack system lint...", COLOR_BOLD + COLOR_CYAN))
    if not errors:
        print(colorize("[OK] Lint clean! All tasks, owners, dependencies, and agent briefs are valid.", COLOR_GREEN))
        return 0
    print(colorize(f"Found {len(errors)} issue(s):", COLOR_RED))
    for err in errors:
        print(f"  [X] {err}")
    return 1


def cmd_doctor(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    report = engine.doctor(frontend=args.frontend)
    if getattr(args, "json", False):
        return _dump(report)
    print(colorize("akstack doctor", COLOR_BOLD + COLOR_CYAN))
    for check in report["checks"]:
        if check["ok"]:
            mark = colorize("OK", COLOR_GREEN)
        elif not check.get("required", True):
            mark = colorize("WARN", COLOR_YELLOW)
        else:
            mark = colorize("FAIL", COLOR_RED)
        print(f"  [{mark}] {check['name']}: {check['detail']}")
    if report["lint_errors"]:
        print(colorize("Lint issues:", COLOR_RED))
        for err in report["lint_errors"]:
            print(f"  [X] {err}")
    return 0 if report["ok"] else 1


def cmd_frontend_check(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    report = engine.frontend_check(args.area)
    if args.json:
        return _dump(report)
    print(colorize(f"Frontend contract: {args.area}", COLOR_BOLD + COLOR_CYAN))
    for check in report["checks"]:
        mark = colorize("OK", COLOR_GREEN) if check["ok"] else colorize("FAIL", COLOR_RED)
        optional = " (advisory)" if not check.get("required", True) else ""
        print(f"  [{mark}] {check['name']}{optional}: {check['detail']}")
    for warning in report["warnings"]:
        print(colorize(f"  [WARN] {warning}", COLOR_YELLOW))
    return 0 if report["ok"] else 1


def cmd_graph(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    tasks = engine.load_tasks()
    graph = DependencyGraph(tasks)
    if args.mermaid:
        print(graph.to_mermaid())
        return 0

    print(colorize("Task Dependency Topology:", COLOR_BOLD + COLOR_CYAN))
    for t in tasks:
        senior = "★ " if t.is_senior else ""
        deps_str = f" <- [{', '.join(t.deps)}]" if t.deps else ""
        status_symbol = {
            "PENDING": "[ ]",
            "IN_PROGRESS": "[~]",
            "COMPLETED": "[x]",
            "BLOCKED": "[!]",
        }.get(t.status.value, "[ ]")
        print(f"  {status_symbol} {senior}{t.id}: {t.title}{colorize(deps_str, COLOR_DIM)}")
    return 0


def cmd_init(engine: OrchestratorEngine, args: argparse.Namespace) -> int:
    success, msg = engine.init_project(project_name=args.name, track=args.track, force=args.force)
    print(colorize(msg, COLOR_GREEN if success else COLOR_RED))
    return 0 if success else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akstack",
        description="Akram-Stack (akstack) Programmatic AI Orchestrator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    p_status = subparsers.add_parser("status", help="Show project progress, active phase, and blockers")
    p_status.add_argument("--json", action="store_true", help="Machine-readable JSON")
    p_status.set_defaults(func=cmd_status)

    p_next = subparsers.add_parser("next", help="Find the next runnable task(s) in topological order")
    p_next.add_argument("--phase", type=int, help="Filter to a specific phase")
    p_next.add_argument("--parallel", action="store_true", help="Group runnable tasks into conflict-free parallel waves")
    p_next.add_argument("--json", action="store_true", help="Machine-readable JSON")
    p_next.set_defaults(func=cmd_next)

    p_packet = subparsers.add_parser("packet", help="Emit a full agent execution packet as JSON")
    p_packet.add_argument("task_id", nargs="?", help="Task ID (defaults to next runnable)")
    p_packet.set_defaults(func=cmd_packet)

    p_start = subparsers.add_parser("start", help="Mark a task as in-progress (- [~])")
    p_start.add_argument("task_id", help="Task ID (e.g. P1-T001)")
    p_start.set_defaults(func=cmd_start)

    p_complete = subparsers.add_parser("complete", help="Verify and mark task as completed (- [x])")
    p_complete.add_argument("task_id", help="Task ID (e.g. P1-T001)")
    p_complete.add_argument("--no-verify", action="store_true", help="Skip running the task Verify command")
    p_complete.add_argument("--no-commit", action="store_true", help="Skip automatic git commit")
    p_complete.add_argument("--notes", type=str, help="Additional verification notes for PROGRESS.md")
    p_complete.set_defaults(func=cmd_complete)

    p_approve = subparsers.add_parser("approve", help="Complete an explicit HUMAN task after stakeholder sign-off")
    p_approve.add_argument("task_id", help="Human task ID")
    p_approve.add_argument("--notes", required=True, help="Decision or approval notes")
    p_approve.add_argument("--evidence", help="Workspace-relative approval evidence file")
    p_approve.add_argument("--no-commit", action="store_true", help="Skip automatic git commit")
    p_approve.set_defaults(func=cmd_approve)

    p_fail = subparsers.add_parser("fail", help="Mark task as blocked (- [!]) and record error diagnosis")
    p_fail.add_argument("task_id", help="Task ID")
    p_fail.add_argument("--error", required=True, help="Failure explanation or error log")
    p_fail.set_defaults(func=cmd_fail)

    p_reset = subparsers.add_parser("reset", help="Reset a blocked/in-progress/completed task to pending")
    p_reset.add_argument("task_id", help="Task ID")
    p_reset.add_argument("--reason", default="", help="Why the task is being reset")
    p_reset.set_defaults(func=cmd_reset)

    p_gate = subparsers.add_parser("gate", help="Run a quality/security gate (e.g. P5-G1)")
    p_gate.add_argument("gate_id", help="Gate ID (e.g. P5-G1 or P5-G4-A11Y)")
    p_gate.add_argument("--evidence", required=False, help="Workspace-relative gate report; required to pass")
    p_gate.add_argument("--notes", default="", help="Gate decision notes")
    p_gate.set_defaults(func=cmd_gate)

    p_finding = subparsers.add_parser("finding", help="File a gate finding as a new -F task")
    p_finding.add_argument("gate_id", help="Gate ID to attach the finding to")
    p_finding.add_argument("--title", required=True, help="Short finding title")
    p_finding.add_argument("--owner", required=True, help="Owning implementation agent")
    p_finding.add_argument("--severity", choices=["Critical", "High", "Medium", "Low"], default="High")
    p_finding.add_argument("--file", default="—", help="File path of the finding")
    p_finding.add_argument("--issue", required=True, help="What is wrong")
    p_finding.add_argument("--fix", required=True, help="Required remediation")
    p_finding.set_defaults(func=cmd_finding)

    p_handoff = subparsers.add_parser("handoff", help="Record a human HANDOFF and create STOP")
    p_handoff.add_argument("task_id", help="Task ID")
    p_handoff.add_argument("--blocked-on", required=True, help="Credential, decision, or physical action needed")
    p_handoff.add_argument("--why", required=True, help="Why the agent cannot proceed")
    p_handoff.set_defaults(func=cmd_handoff)

    p_resume = subparsers.add_parser("resume", help="Resolve a human handoff and clear STOP")
    p_resume.add_argument("--notes", required=True, help="What resolved the handoff")
    p_resume.add_argument("--no-commit", action="store_true", help="Skip automatic git commit")
    p_resume.set_defaults(func=cmd_resume)

    p_question = subparsers.add_parser("question", help="Record a domain QUESTION (never guess)")
    p_question.add_argument("task_id", help="Task ID")
    p_question.add_argument("--ambiguity", required=True, help="What is underspecified")
    p_question.add_argument("--risk", required=True, help="Hard rule or irreversible risk")
    p_question.add_argument("--recommended", required=True, help="Recommended course pending sign-off")
    p_question.set_defaults(func=cmd_question)

    p_lint = subparsers.add_parser("lint", help="Verify task graph integrity, agent briefs, and file paths")
    p_lint.add_argument("--json", action="store_true")
    p_lint.set_defaults(func=cmd_lint)

    p_doctor = subparsers.add_parser("doctor", help="Check runtime, git, templates, and ledger health")
    p_doctor.add_argument("--json", action="store_true")
    p_doctor.add_argument("--frontend", action="store_true", help="Require frontend tooling and contract artifacts")
    p_doctor.set_defaults(func=cmd_doctor)

    p_frontend = subparsers.add_parser("frontend-check", help="Validate frontend design, growth, accessibility, and performance contracts")
    p_frontend.add_argument("--area", choices=["all", "design", "visual", "growth", "cro", "a11y", "accessibility", "performance", "perf"], default="all")
    p_frontend.add_argument("--json", action="store_true", help="Machine-readable JSON")
    p_frontend.set_defaults(func=cmd_frontend_check)

    p_graph = subparsers.add_parser("graph", help="Visualize dependency graph")
    p_graph.add_argument("--mermaid", action="store_true", help="Output Mermaid diagram syntax")
    p_graph.set_defaults(func=cmd_graph)

    p_init = subparsers.add_parser("init", help="Bootstrap a new project from templates")
    p_init.add_argument("name", help="Project name")
    p_init.add_argument("--track", choices=["Product/Web", "AI/ML", "Hybrid"], default="Product/Web")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing plan/ToDos/PROGRESS")
    p_init.set_defaults(func=cmd_init)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    engine = OrchestratorEngine()
    return args.func(engine, args)


if __name__ == "__main__":
    sys.exit(main())
