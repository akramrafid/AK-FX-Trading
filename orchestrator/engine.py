"""
Core orchestration engine executing akstack commands and workflows.
"""

import datetime
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .frontend import FrontendContractChecker
from .graph import DependencyGraph
from .models import GATE_ORDER, SPECIAL_OWNERS, Task, TaskStatus, TaskType, Track
from .parser import MarkdownParser


class OrchestratorEngine:
    """Core execution engine for managing tasks, verification, and git synchronization."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (Path(workspace_root) if workspace_root else Path.cwd()).resolve()
        source_root = Path(__file__).resolve().parent.parent
        asset_roots = (source_root, Path(sys.prefix) / "share" / "akstack")
        self.asset_root = next((root for root in asset_roots if (root / "templates").exists()), source_root)
        self.todos_file = self.workspace_root / "ToDos.md"
        self.plan_file = self.workspace_root / "plan.md"
        self.progress_file = self.workspace_root / "PROGRESS.md"
        self.agents_dir = self._asset_path("agents")
        self.phases_dir = self._asset_path("phases")
        self.templates_dir = self._asset_path("templates")
        self.stop_file = self.workspace_root / "STOP"
        self.lock_file = self.workspace_root / ".akstack.lock"

    def _asset_path(self, name: str) -> Path:
        workspace_path = self.workspace_root / name
        return workspace_path if workspace_path.exists() else self.asset_root / name

    def load_tasks(self) -> List[Task]:
        """Load and parse all tasks from ToDos.md."""
        target_file = self.todos_file
        if not target_file.exists():
            template_file = self.templates_dir / "ToDos.template.md"
            if template_file.exists():
                target_file = template_file
            else:
                return []
        content = target_file.read_text(encoding="utf-8")
        return MarkdownParser.parse_todos(content)

    def load_plan(self):
        """Load and parse plan.md."""
        target_file = self.plan_file
        if not target_file.exists():
            template_file = self.templates_dir / "plan.template.md"
            if template_file.exists():
                target_file = template_file
            else:
                return None
        content = target_file.read_text(encoding="utf-8")
        return MarkdownParser.parse_plan(content)

    def _find_task(self, task_id: str) -> Optional[Task]:
        return next((t for t in self.load_tasks() if t.id == task_id), None)

    def _write_todos(self, content: str) -> None:
        self._atomic_write(self.todos_file, content)

    def _append_progress(self, entry: str) -> None:
        current = self.progress_file.read_text(encoding="utf-8") if self.progress_file.exists() else ""
        updated = current + (entry if entry.startswith("\n") else "\n" + entry)
        self._atomic_write(self.progress_file, updated)

    def _atomic_write(self, path: Path, content: str) -> None:
        """Write and replace a file atomically so a killed process cannot truncate it."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    @contextmanager
    def _workspace_lock(self, timeout: float = 30.0) -> Iterator[None]:
        """Serialize ledger and git-index mutations across agent processes."""
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        with open(self.lock_file, "a+", encoding="ascii") as handle:
            handle.seek(0)
            if not handle.read(1):
                handle.seek(0)
                handle.write("0")
                handle.flush()
            if os.name == "nt":
                import msvcrt

                deadline = time.monotonic() + timeout
                while True:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Timed out waiting for .akstack.lock")
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _active_phase(self, tasks: List[Task]) -> int:
        incomplete = [task.phase for task in tasks if task.status != TaskStatus.COMPLETED]
        return min(incomplete) if incomplete else (max((task.phase for task in tasks), default=0))

    def _phase_prerequisites(self, tasks: List[Task], phase: int) -> List[Task]:
        return [task for task in tasks if task.phase < phase and task.status != TaskStatus.COMPLETED]

    def _required_gate_keys(self, track: str) -> List[str]:
        keys: List[str] = []
        if track in (Track.AI_ML.value, Track.HYBRID.value):
            keys.append("G0-ML")
        keys.extend(("G1", "G2", "G3", "G3-P"))
        if track in (Track.PRODUCT_WEB.value, Track.HYBRID.value):
            keys.extend(("G4", "G4-CRO", "G4-A11Y"))
        keys.extend(("G5", "G6"))
        return keys

    def _parse_command(self, command: str) -> Tuple[Optional[List[str]], str]:
        """Parse a Verify command without invoking a shell."""
        value = MarkdownParser.clean_verify(command)
        if MarkdownParser.should_skip_verify(value):
            return None, "manual verification"
        if not value:
            return None, "empty verification command"
        if re.search(r"(?:&&|\|\||[|;<>])", value):
            return None, "shell operators are not allowed in Verify; use one executable with arguments"
        try:
            parts = shlex.split(value, posix=os.name != "nt")
        except ValueError as exc:
            return None, f"invalid Verify command quoting: {exc}"
        parts = [part.strip('"') for part in parts if part]
        if not parts:
            return None, "empty verification command"
        return parts, ""

    def _run_command(self, command: str, timeout: int = 300) -> Tuple[bool, str]:
        parts, error = self._parse_command(command)
        if parts is None:
            if error == "manual verification":
                return True, "Manual verification recorded."
            return False, error
        try:
            result = subprocess.run(
                parts,
                cwd=str(self.workspace_root),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            return False, f"executable not found: {parts[0]}"
        except subprocess.TimeoutExpired:
            return False, f"verification command timed out after {timeout}s: {command}"
        except OSError as exc:
            return False, f"verification execution error: {exc}"
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return False, f"exit code {result.returncode}: {detail}"
        return True, f"Command `{MarkdownParser.clean_verify(command)}` passed (exit code 0)."

    def _safe_evidence(self, evidence: str) -> Tuple[List[Path], str]:
        paths: List[Path] = []
        if not evidence.strip():
            return paths, "provide --evidence <workspace-relative report>"
        root = self.workspace_root.resolve()
        for raw in evidence.split(","):
            candidate = Path(raw.strip())
            if not candidate.is_absolute():
                candidate = self.workspace_root / candidate
            candidate = candidate.resolve()
            try:
                inside = os.path.commonpath((str(root), str(candidate))) == str(root)
            except ValueError:
                inside = False
            if not inside:
                return [], f"evidence path must be inside workspace: {raw.strip()}"
            if not candidate.is_file():
                return [], f"evidence file does not exist: {raw.strip()}"
            if candidate.stat().st_size == 0:
                return [], f"evidence file is empty: {raw.strip()}"
            if candidate.suffix.lower() in {".md", ".txt", ".json", ".html", ".yaml", ".yml"}:
                evidence_text = candidate.read_text(encoding="utf-8", errors="replace")
                if FrontendContractChecker.PLACEHOLDER.search(evidence_text):
                    return [], f"evidence file contains unresolved placeholders: {raw.strip()}"
            paths.append(candidate)
        return paths, ""

    def _commit_metadata(self, extra_paths: Optional[List[Path]] = None) -> Tuple[bool, str]:
        paths = [self.todos_file, self.progress_file]
        if extra_paths:
            paths.extend(extra_paths)
        return self._commit_paths(paths, "akstack: record orchestration state")

    def _commit_paths(self, paths: List[Path], message: str) -> Tuple[bool, str]:
        if not self._is_git_repo():
            return True, "no git repository; skipped commit"
        if not shutil.which("git"):
            return False, "git is not on PATH"
        root = self.workspace_root.resolve()
        relative: List[str] = []
        seen = set()
        for path in paths:
            try:
                rel = path.resolve().relative_to(root).as_posix()
            except ValueError:
                return False, f"cannot stage path outside workspace: {path}"
            if rel not in seen and path.exists():
                relative.append(rel)
                seen.add(rel)
        if not relative:
            return True, "nothing to commit"
        allowed = set(relative)
        staged_before = self._staged_paths()
        unexpected_before = [path for path in staged_before if not self._path_allowed(path, allowed)]
        if unexpected_before:
            return False, (
                "refusing to commit because unrelated files are already staged: "
                + ", ".join(unexpected_before)
            )
        try:
            add = subprocess.run(
                ["git", "add", "--"] + relative,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
            )
            if add.returncode != 0:
                return False, (add.stderr or add.stdout).strip()
            staged_after = self._staged_paths()
            unexpected_after = [path for path in staged_after if not self._path_allowed(path, allowed)]
            if unexpected_after:
                return False, (
                    "refusing to commit outside declared scope: "
                    + ", ".join(unexpected_after)
                )
            commit = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
            )
            if commit.returncode != 0:
                combined = (commit.stderr or commit.stdout).strip()
                if "nothing to commit" in combined.lower():
                    return True, "nothing to commit"
                return False, combined
            return True, "committed"
        except OSError as exc:
            return False, str(exc)

    def _staged_paths(self) -> List[str]:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z"],
            cwd=str(self.workspace_root),
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        return [path.replace("\\", "/") for path in result.stdout.decode("utf-8", errors="replace").split("\0") if path]

    @staticmethod
    def _path_allowed(path: str, allowed: set) -> bool:
        return any(path == item or path.startswith(item.rstrip("/") + "/") for item in allowed)

    def _scope_violations(self, task: Task) -> List[str]:
        """Return dirty paths outside a task's declared Files: boundary."""
        if not self._is_git_repo() or not shutil.which("git"):
            return []
        allowed = {"ToDos.md", "PROGRESS.md"}
        allowed.update(file_path.replace("\\", "/").strip("/") for file_path in task.files if file_path.strip())
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z"],
            cwd=str(self.workspace_root),
            capture_output=True,
        )
        if result.returncode != 0:
            return []
        violations: List[str] = []
        for record in result.stdout.decode("utf-8", errors="replace").split("\0"):
            if len(record) < 4:
                continue
            path = record[3:].replace("\\", "/")
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[-1]
            if not self._path_allowed(path, allowed):
                violations.append(path)
        return violations

    def _tag_phase(self, phase: int) -> Tuple[bool, str]:
        if not self._is_git_repo():
            return True, "no git repository; skipped tag"
        tag = f"phase-{phase}-complete"
        existing = subprocess.run(["git", "tag", "--list", tag], cwd=str(self.workspace_root), capture_output=True, text=True)
        if existing.stdout.strip() == tag:
            return True, f"tag {tag} already exists"
        result = subprocess.run(["git", "tag", tag], cwd=str(self.workspace_root), capture_output=True, text=True)
        if result.returncode != 0:
            return False, (result.stderr or result.stdout).strip()
        return True, f"tagged {tag}"

    def frontend_check(self, area: str = "all") -> Dict[str, Any]:
        """Run the framework-agnostic frontend handoff checks."""
        return FrontendContractChecker(self.workspace_root).run(area)

    def _now(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def _stop_active(self) -> bool:
        return self.stop_file.exists()

    def get_status(self) -> Dict[str, Any]:
        """Compute full health and progress metrics for the current project."""
        tasks = self.load_tasks()
        plan = self.load_plan()

        by_status = {
            TaskStatus.PENDING: 0,
            TaskStatus.IN_PROGRESS: 0,
            TaskStatus.COMPLETED: 0,
            TaskStatus.BLOCKED: 0,
        }
        by_phase: Dict[int, Dict[str, int]] = {}
        blocked_tasks: List[Task] = []
        in_progress_tasks: List[Task] = []

        for task in tasks:
            by_status[task.status] += 1
            if task.phase not in by_phase:
                by_phase[task.phase] = {"total": 0, "completed": 0, "blocked": 0, "in_progress": 0, "pending": 0}
            by_phase[task.phase]["total"] += 1
            if task.status == TaskStatus.COMPLETED:
                by_phase[task.phase]["completed"] += 1
            elif task.status == TaskStatus.BLOCKED:
                by_phase[task.phase]["blocked"] += 1
                blocked_tasks.append(task)
            elif task.status == TaskStatus.IN_PROGRESS:
                by_phase[task.phase]["in_progress"] += 1
                in_progress_tasks.append(task)
            else:
                by_phase[task.phase]["pending"] += 1

        active_phase = 0
        all_complete = bool(tasks) and by_status[TaskStatus.COMPLETED] == len(tasks)
        if tasks:
            for phase in sorted(by_phase.keys()):
                stats = by_phase[phase]
                if stats["completed"] < stats["total"]:
                    active_phase = phase
                    break
            if all_complete:
                active_phase = max(by_phase.keys())

        graph = DependencyGraph(tasks)
        cycles = graph.detect_cycles()
        runnable = graph.get_runnable_tasks(phase=active_phase if active_phase else None)

        return {
            "project_name": plan.project_name if plan else "Unknown Project",
            "track": plan.track if plan else Track.PRODUCT_WEB.value,
            "total_tasks": len(tasks),
            "completed_tasks": by_status[TaskStatus.COMPLETED],
            "pending_tasks": by_status[TaskStatus.PENDING],
            "in_progress_tasks": in_progress_tasks,
            "blocked_tasks": blocked_tasks,
            "by_status": {k.value: v for k, v in by_status.items()},
            "by_phase": by_phase,
            "active_phase": active_phase,
            "all_complete": all_complete,
            "runnable_count": len(runnable),
            "next_task": runnable[0] if runnable else None,
            "has_cycles": bool(cycles),
            "cycles": cycles,
            "stop_active": self._stop_active(),
        }

    def get_next(self, phase: Optional[int] = None, parallel: bool = False) -> List[List[Task]]:
        """Find next runnable tasks scheduled into conflict-free parallel waves."""
        tasks = self.load_tasks()
        graph = DependencyGraph(tasks)
        selected_phase = phase if phase is not None else self._active_phase(tasks)
        if selected_phase and self._phase_prerequisites(tasks, selected_phase):
            return []
        runnable = graph.get_runnable_tasks(phase=selected_phase or None)
        if not runnable:
            return []
        if not parallel:
            return [[runnable[0]]]
        return graph.schedule_parallel_waves(runnable)

    def build_packet(self, task: Task) -> Dict[str, Any]:
        """Machine-readable execution packet for an agent assigned to a task."""
        plan = self.load_plan()
        brief = self.agents_dir / f"{task.owner}.md"
        return {
            "task_id": task.id,
            "title": task.title,
            "phase": task.phase,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "owner": task.owner,
            "is_senior": task.is_senior,
            "is_human": task.is_human,
            "deps": task.deps,
            "files": task.files,
            "do": task.do,
            "accept": task.accept,
            "verify": task.verify,
            "brief": str(brief) if brief.exists() else "",
            "read_first": [
                "plan.md",
                "ToDos.md",
                "PROGRESS.md",
                "agents/TEAM.md",
                "GLOBAL-RULES.md",
                f"agents/{task.owner}.md" if task.owner else "",
            ],
            "hard_rules": plan.hard_rules if plan else [],
            "track": plan.track if plan else Track.PRODUCT_WEB.value,
            "project_name": plan.project_name if plan else "",
        }

    def start_task(self, task_id: str) -> Tuple[bool, str]:
        """Mark task as IN_PROGRESS (- [~]) in ToDos.md."""
        with self._workspace_lock():
            if self._stop_active():
                return False, "STOP file present. Resolve the handoff before starting another task."
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist. Run init first."

            tasks = self.load_tasks()
            task = next((t for t in tasks if t.id == task_id), None)
            if not task:
                return False, f"Task {task_id} not found in ToDos.md."
            if task.status == TaskStatus.IN_PROGRESS:
                return True, f"Task {task_id} is already IN_PROGRESS (- [~])."
            if task.status == TaskStatus.COMPLETED:
                return False, f"Task {task_id} is already COMPLETED. Use reset to reopen it."
            if task.status == TaskStatus.BLOCKED:
                return False, f"Task {task_id} is BLOCKED (- [!]). Diagnose, then run: akstack reset {task_id}"
            if task.is_human:
                return False, f"Task {task_id} is a HUMAN task. Use `akstack approve {task_id}` after sign-off."
            if task.task_type == TaskType.GATE:
                return False, f"Task {task_id} is a gate. Use `akstack gate {task_id}` instead of start."

            active_phase = self._active_phase(tasks)
            if task.phase > active_phase:
                return False, f"Task {task_id} is in Phase {task.phase}; Phase {active_phase} is still active."

            plan = self.load_plan()
            track = plan.track if plan else Track.PRODUCT_WEB.value
            if task.phase == 4 and track in (Track.PRODUCT_WEB.value, Track.HYBRID.value):
                design_signoff = next(
                    (
                        candidate for candidate in tasks
                        if candidate.phase == 3
                        and candidate.task_type == TaskType.GATE
                        and candidate.gate_key == "G1"
                    ),
                    None,
                )
                if design_signoff is None:
                    return False, "Frontend build is locked: add and complete human design sign-off P3-G1 first."
                if design_signoff.status != TaskStatus.COMPLETED:
                    return False, f"Frontend build is locked until design sign-off {design_signoff.id} is approved."

            graph = DependencyGraph(tasks)
            unmet = graph.unmet_deps(task)
            if unmet:
                return False, f"Task {task_id} cannot start. Unmet dependencies: {', '.join(unmet)}"

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, task_id, TaskStatus.IN_PROGRESS)
            if not updated:
                return False, f"Task {task_id} not found in ToDos.md."
            self._write_todos(new_content)
            return True, f"Task {task_id} status updated to IN_PROGRESS (- [~])."

    def complete_task(
        self,
        task_id: str,
        run_verify: bool = True,
        git_commit: bool = True,
        verification_notes: str = "",
    ) -> Tuple[bool, str]:
        """
        Run verification command (if enabled), mark task COMPLETED (- [x]),
        append entry to PROGRESS.md, and optionally create a git commit.
        """
        with self._workspace_lock():
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist."

            tasks = self.load_tasks()
            task = next((t for t in tasks if t.id == task_id), None)
            if not task:
                return False, f"Task {task_id} not found."
            if task.status == TaskStatus.COMPLETED:
                return True, f"Task {task_id} is already COMPLETED."
            if task.status == TaskStatus.BLOCKED:
                return False, f"Task {task_id} is BLOCKED. Reset it before completing."
            if task.is_human:
                return False, f"Task {task_id} requires human approval. Use `akstack approve {task_id}`."
            if task.task_type == TaskType.GATE:
                return False, f"Task {task_id} is a gate. Use `akstack gate {task_id}` instead."
            if task.status != TaskStatus.IN_PROGRESS:
                return False, f"Task {task_id} must be IN_PROGRESS before completion. Run `akstack start {task_id}`."

            scope_violations = self._scope_violations(task)
            if scope_violations:
                return False, (
                    f"Task {task_id} changed files outside its declared Files: boundary: "
                    + ", ".join(scope_violations)
                )

            graph = DependencyGraph(tasks)
            unmet = graph.unmet_deps(task)
            if unmet:
                return False, f"Task {task_id} cannot complete. Unmet dependencies: {', '.join(unmet)}"

            verify_output = "Manual verification or skip flag specified."
            if run_verify:
                ok, detail = self._run_command(task.verify)
                if not ok:
                    return False, f"Verification command failed: {detail}"
                verify_output = detail
            elif not MarkdownParser.should_skip_verify(task.verify) and not verification_notes.strip():
                return False, "Skipping a real Verify command requires explicit verification notes."

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, task_id, TaskStatus.COMPLETED)
            if not updated:
                return False, f"Failed to update task {task_id} in ToDos.md."
            self._write_todos(new_content)

            progress_entry = (
                f"\n### {self._now()} — {task.id}: {task.title}\n"
                f"**Owner:** {task.owner}\n"
                f"**Changed:** {', '.join(task.files) if task.files else 'Task files'}\n"
                f"**Verified:** {verification_notes or verify_output}\n"
                f"**Status:** COMPLETED\n"
            )
            self._append_progress(progress_entry)

            if git_commit:
                ok, git_msg = self._commit_task(task)
                if not ok:
                    return False, f"Task {task_id} state changed, but git commit failed: {git_msg}"
                return True, f"Task {task_id} completed successfully and committed."

            return True, f"Task {task_id} completed successfully."

    def approve_task(
        self,
        task_id: str,
        notes: str,
        evidence: str = "",
        git_commit: bool = True,
    ) -> Tuple[bool, str]:
        """Complete a HUMAN task only after explicit stakeholder evidence."""
        with self._workspace_lock():
            task = self._find_task(task_id)
            if not task:
                return False, f"Task {task_id} not found."
            if not task.is_human:
                return False, f"Task {task_id} is not marked HUMAN. Use complete after implementation."
            if task.status == TaskStatus.COMPLETED:
                return True, f"Task {task_id} is already COMPLETED."
            if not notes.strip():
                return False, "Human approval requires non-empty notes."
            evidence_paths, error = self._safe_evidence(evidence)
            if error:
                return False, f"Approval evidence required: {error}"
            if self._phase_prerequisites(self.load_tasks(), task.phase):
                return False, f"Task {task_id} cannot be approved while an earlier phase is incomplete."
            unmet = DependencyGraph(self.load_tasks()).unmet_deps(task)
            if unmet:
                return False, f"Task {task_id} cannot be approved. Unmet dependencies: {', '.join(unmet)}"

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, task_id, TaskStatus.COMPLETED)
            if not updated:
                return False, f"Failed to approve {task_id}."
            self._write_todos(new_content)
            evidence_text = ", ".join(path.relative_to(self.workspace_root).as_posix() for path in evidence_paths)
            self._append_progress(
                f"\n### {self._now()} — HUMAN APPROVAL: {task_id}\n"
                f"**Owner:** {task.owner}\n"
                f"**Notes:** {notes}\n"
                f"**Evidence:** {evidence_text}\n"
                f"**Status:** COMPLETED\n"
            )
            if self.stop_file.exists():
                self.stop_file.unlink()
            if git_commit:
                ok, git_msg = self._commit_metadata(evidence_paths)
                if not ok:
                    return False, f"Approval recorded, but git commit failed: {git_msg}"
            return True, f"Human task {task_id} approved and completed."

    def fail_task(self, task_id: str, error_msg: str) -> Tuple[bool, str]:
        """Mark a task as BLOCKED (- [!]) and log diagnosis to PROGRESS.md."""
        with self._workspace_lock():
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist."

            task = self._find_task(task_id)
            if not task:
                return False, f"Task {task_id} not found."
            if not error_msg.strip():
                return False, "A root-cause diagnosis is required when blocking a task."

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, task_id, TaskStatus.BLOCKED)
            if not updated:
                return False, f"Task {task_id} not found."
            self._write_todos(new_content)

            entry = (
                f"\n### {self._now()} — BLOCKED: {task_id}\n"
                f"**Error:** {error_msg}\n"
                f"**Diagnosis:** Task failed verification; execution halted on dependent tasks.\n"
                f"**Next:** Diagnose root cause, then `akstack reset {task_id}` and retry (max 3).\n"
            )
            self._append_progress(entry)
            return True, f"Task {task_id} marked as BLOCKED (- [!]). Error logged to PROGRESS.md."

    def reset_task(self, task_id: str, reason: str = "") -> Tuple[bool, str]:
        """Reset a blocked, in-progress, or completed task back to PENDING."""
        with self._workspace_lock():
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist."
            task = self._find_task(task_id)
            if not task:
                return False, f"Task {task_id} not found."
            if task.status == TaskStatus.PENDING:
                return True, f"Task {task_id} is already PENDING."

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, task_id, TaskStatus.PENDING)
            if not updated:
                return False, f"Failed to reset task {task_id}."
            self._write_todos(new_content)

            note = reason or f"Reset from {task.status.value} to PENDING."
            self._append_progress(
                f"\n### {self._now()} — RESET: {task_id}\n"
                f"**Previous status:** {task.status.value}\n"
                f"**Reason:** {note}\n"
            )
            return True, f"Task {task_id} reset to PENDING (- [ ])."

    def handoff(self, task_id: str, blocked_on: str, why: str) -> Tuple[bool, str]:
        """Record a human HANDOFF and create a STOP file."""
        with self._workspace_lock():
            if not blocked_on.strip() or not why.strip():
                return False, "HANDOFF requires both --blocked-on and --why."
            task = self._find_task(task_id)
            owner = task.owner if task else "coordinator"
            self._atomic_write(
                self.stop_file,
                f"STOP\nTask: {task_id}\nBlocked on: {blocked_on}\nWhy: {why}\n",
            )
            self._append_progress(
                f"\n### {self._now()} — HANDOFF: {task_id}\n"
                f"**Owner:** {owner}\n"
                f"**Blocked on:** {blocked_on}\n"
                f"**Why the agent cannot proceed:** {why}\n"
                f"**STOP Signal:** Created `STOP` file in repo root.\n"
            )
            return True, f"HANDOFF recorded for {task_id}. STOP file created."

    def resume(self, notes: str, git_commit: bool = True) -> Tuple[bool, str]:
        """Clear a resolved STOP handoff with an explicit human note."""
        with self._workspace_lock():
            if not self.stop_file.exists():
                return True, "No STOP file is active."
            if not notes.strip():
                return False, "Resuming requires a note describing what resolved the handoff."
            self.stop_file.unlink()
            self._append_progress(
                f"\n### {self._now()} — HANDOFF RESOLVED\n"
                f"**Notes:** {notes}\n"
                f"**STOP Signal:** Cleared.\n"
            )
            if git_commit:
                ok, git_msg = self._commit_metadata()
                if not ok:
                    return False, f"STOP cleared, but git commit failed: {git_msg}"
            return True, "Handoff resolved and STOP file cleared."

    def question(self, task_id: str, ambiguity: str, risk: str, recommended: str) -> Tuple[bool, str]:
        """Record a domain QUESTION that must not be guessed."""
        with self._workspace_lock():
            if not all(value.strip() for value in (ambiguity, risk, recommended)):
                return False, "QUESTION requires ambiguity, risk, and recommended course."
            task = self._find_task(task_id)
            owner = task.owner if task else "coordinator"
            self._append_progress(
                f"\n### {self._now()} — QUESTION: {task_id}\n"
                f"**Owner:** {owner}\n"
                f"**The Ambiguity:** {ambiguity}\n"
                f"**Risk/Hard Rule at Stake:** {risk}\n"
                f"**Recommended Course:** {recommended}\n"
            )
            return True, f"QUESTION recorded for {task_id} in PROGRESS.md."

    def file_finding(
        self,
        gate_id: str,
        title: str,
        owner: str,
        severity: str,
        file_path: str,
        issue: str,
        fix: str,
    ) -> Tuple[bool, str]:
        """File a Critical/High gate finding as a new -F task below the gate."""
        with self._workspace_lock():
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist."
            tasks = self.load_tasks()
            gate = next((t for t in tasks if t.id == gate_id), None)
            if not gate:
                return False, f"Gate {gate_id} not found."
            if gate.task_type != TaskType.GATE:
                return False, f"{gate_id} is not a gate."
            if severity not in {"Critical", "High", "Medium", "Low"}:
                return False, "Severity must be Critical, High, Medium, or Low."
            if not all(value.strip() for value in (title, owner, issue, fix)):
                return False, "Finding requires title, owner, issue, and fix."

            phase = gate.phase
            existing_findings = [t for t in tasks if t.task_type == TaskType.FINDING and t.phase == phase]
            next_n = len(existing_findings) + 1
            finding_id = f"P{phase}-F{next_n:02d}"
            while any(t.id == finding_id for t in tasks):
                next_n += 1
                finding_id = f"P{phase}-F{next_n:02d}"

            # A finding must be fixable while its gate remains open. It is
            # associated with the gate through Gate:, not a circular dependency.
            block = (
                f"- [ ] **{finding_id}** [{severity}] {title}\n"
                f"  - **Owner:** {owner}\n"
                f"  - **Gate:** {gate_id}\n"
                f"  - **Deps:** —\n"
                f"  - **Files:** `{file_path}`\n"
                f"  - **Do:** {issue} Remediate: {fix}\n"
                f"  - **Accept:** Finding no longer reproducible; reviewer re-checks {gate_id}.\n"
                f"  - **Verify:** manual review\n"
            )
            content = self.todos_file.read_text(encoding="utf-8")
            new_content = MarkdownParser.append_task_block(content, block, after_id=gate_id)
            self._write_todos(new_content)
            if gate.status == TaskStatus.COMPLETED:
                reopened, _ = MarkdownParser.update_task_status(new_content, gate_id, TaskStatus.PENDING)
                self._write_todos(reopened)
                new_content = reopened
            self._append_progress(
                f"\n### {self._now()} — FINDING FILED: {finding_id}\n"
                f"**Gate:** {gate_id}\n"
                f"**Severity:** {severity}\n"
                f"**Issue:** {issue}\n"
                f"**Status:** OPEN\n"
            )
            ok, commit_msg = self._commit_metadata()
            if not ok:
                return False, f"Finding {finding_id} recorded, but git commit failed: {commit_msg}"
            return True, f"Filed {finding_id} under {gate_id} owned by {owner}."

    def run_gate(self, gate_id: str, evidence: str = "", notes: str = "") -> Tuple[bool, str]:
        """
        Check gate status and preconditions.
        Ensures phase order, prior gates, open findings, verification, and
        evidence allow the gate to pass.
        """
        with self._workspace_lock():
            if not self.todos_file.exists():
                return False, "ToDos.md does not exist."

            tasks = self.load_tasks()
            gate = next((t for t in tasks if t.id == gate_id), None)
            if not gate:
                return False, f"Gate {gate_id} not found in ToDos.md."
            if gate.task_type != TaskType.GATE:
                return False, f"{gate_id} is not a gate task."
            if gate.is_human:
                return False, f"{gate_id} requires human approval. Use `akstack approve {gate_id}`."
            if gate.status == TaskStatus.COMPLETED:
                return True, f"Gate {gate_id} already passed."

            phase = gate.phase
            plan = self.load_plan()
            track = plan.track if plan else Track.PRODUCT_WEB.value

            if gate.gate_key == "G0-ML" and track == Track.PRODUCT_WEB.value:
                content = self.todos_file.read_text(encoding="utf-8")
                new_content, _ = MarkdownParser.update_task_status(content, gate_id, TaskStatus.COMPLETED)
                self._write_todos(new_content)
                self._append_progress(
                    f"\n### {self._now()} — GATE SKIPPED: {gate_id}\n"
                    f"**Reason:** G0-ML does not apply to Product/Web track.\n"
                    f"**Status:** SKIPPED / CLEARED\n"
                )
                return True, f"Gate {gate_id} skipped (Product/Web track has no ML eval gate)."

            required = self._required_gate_keys(track) if phase == 5 else []
            if phase == 5 and gate.gate_key not in GATE_ORDER:
                return False, f"Unknown Phase 5 gate key: {gate.gate_key}."
            if phase == 5 and gate.gate_key in required:
                prior = self._prior_gates_incomplete(tasks, gate, required)
                if prior:
                    return False, prior

            earlier = self._phase_prerequisites(tasks, phase)
            if earlier:
                return False, (
                    f"Gate {gate_id} cannot pass while earlier phase tasks are incomplete "
                    f"(e.g. {earlier[0].id})."
                )

            pending_impl = [
                task for task in tasks
                if task.phase == phase
                and task.task_type in (TaskType.STANDARD, TaskType.CHANGE)
                and task.status != TaskStatus.COMPLETED
            ]
            if pending_impl:
                return False, (
                    f"Gate {gate_id} cannot pass: {len(pending_impl)} implementation task(s) "
                    f"in Phase {phase} are incomplete (e.g. {pending_impl[0].id})."
                )

            graph = DependencyGraph(tasks)
            unmet = graph.unmet_deps(gate)
            if unmet:
                return False, f"Gate {gate_id} cannot pass. Unmet dependencies: {', '.join(unmet)}"

            open_findings = [
                t for t in tasks
                if t.task_type == TaskType.FINDING
                and (t.gate_id == gate_id or gate_id in t.deps)
                and t.status != TaskStatus.COMPLETED
            ]
            if open_findings:
                sample = ", ".join(t.id for t in open_findings[:5])
                return False, f"Gate {gate_id} cannot pass: {len(open_findings)} open finding(s) ({sample})."

            evidence_paths, evidence_error = self._safe_evidence(evidence)
            if evidence_error:
                return False, f"Gate evidence required: {evidence_error}"

            if gate.gate_key in {"G4", "G4-CRO", "G4-A11Y", "G5"} and track in (Track.PRODUCT_WEB.value, Track.HYBRID.value):
                area = {"G4": "visual", "G4-CRO": "growth", "G4-A11Y": "a11y", "G5": "performance"}[gate.gate_key]
                contract = self.frontend_check(area)
                if not contract["ok"]:
                    return False, f"Frontend {area} contract failed: {'; '.join(contract['errors'][:3])}"

            ok, verify_output = self._run_command(gate.verify)
            if not ok:
                return False, f"Gate verification failed: {verify_output}"

            content = self.todos_file.read_text(encoding="utf-8")
            new_content, updated = MarkdownParser.update_task_status(content, gate_id, TaskStatus.COMPLETED)
            if not updated:
                return False, f"Gate {gate_id} not found in ToDos.md."
            self._write_todos(new_content)
            evidence_text = ", ".join(path.relative_to(self.workspace_root).as_posix() for path in evidence_paths)
            self._append_progress(
                f"\n### {self._now()} — GATE PASSED: {gate_id}\n"
                f"**Phase:** {phase}\n"
                f"**Reviewer:** {gate.owner}\n"
                f"**Evidence:** {evidence_text}\n"
                f"**Verification:** {verify_output}\n"
                f"**Notes:** {notes or 'None'}\n"
                f"**Status:** PASSED\n"
            )
            ok, commit_msg = self._commit_metadata(evidence_paths)
            if not ok:
                return False, f"Gate {gate_id} passed in the ledger, but git commit failed: {commit_msg}"
            if gate.gate_key == "G6":
                tag_ok, tag_msg = self._tag_phase(phase)
                if not tag_ok:
                    return False, f"Gate {gate_id} passed, but release tag failed: {tag_msg}"
            return True, f"Gate {gate_id} passed successfully."

    def _prior_gates_incomplete(self, tasks: List[Task], gate: Task, required: List[str]) -> str:
        order_index = {key: i for i, key in enumerate(required)}
        current_idx = order_index.get(gate.gate_key, 999)
        for key in required[:current_idx]:
            candidate = next((t for t in tasks if t.phase == gate.phase and t.task_type == TaskType.GATE and t.gate_key == key), None)
            if candidate is None:
                return f"Gate {gate.id} cannot pass: required prior gate P{gate.phase}-{key} is missing."
            if candidate.status != TaskStatus.COMPLETED:
                return f"Gate {gate.id} cannot pass until prior gate {candidate.id} is cleared."
        return ""

    def lint(self) -> List[str]:
        """Validate structural integrity of all akstack documents, agents, and tasks."""
        errors: List[str] = []
        tasks = self.load_tasks()

        seen_ids = set()
        for task in tasks:
            if task.id in seen_ids:
                errors.append(f"Duplicate task ID found: {task.id}")
            seen_ids.add(task.id)
            if not MarkdownParser.TASK_ID_PATTERN.fullmatch(task.id):
                errors.append(f"Invalid task ID format: {task.id}")
            id_phase = re.match(r"P(\d+)-", task.id)
            if id_phase and int(id_phase.group(1)) != task.phase:
                errors.append(f"Task {task.id} phase heading does not match its ID phase {task.phase}.")

        for task in tasks:
            for dep in task.deps:
                if dep not in seen_ids and not dep.startswith("{{"):
                    errors.append(f"Task {task.id} references non-existent dependency: {dep}")
            if not task.owner:
                errors.append(f"Task {task.id} has no Owner.")
            if not task.do:
                errors.append(f"Task {task.id} has empty Do: field.")
            if not task.accept:
                errors.append(f"Task {task.id} has empty Accept: field.")
            if not task.verify:
                errors.append(f"Task {task.id} has empty Verify: field.")
            elif self._parse_command(task.verify)[1] not in {"", "manual verification"}:
                errors.append(f"Task {task.id} has invalid Verify: {self._parse_command(task.verify)[1]}")
            if task.task_type == TaskType.STANDARD and not task.files and not task.is_human:
                errors.append(f"Task {task.id} has empty Files: list (not parallel-safe).")
            if task.task_type == TaskType.FINDING and not task.gate_id and not task.deps:
                errors.append(f"Finding {task.id} is not associated with a gate (add Gate:).")

        graph = DependencyGraph(tasks)
        cycle = graph.detect_cycles()
        if cycle:
            errors.append(f"Circular dependency detected in tasks: {' -> '.join(cycle)}")

        if self.agents_dir.exists():
            agent_files = {f.stem for f in self.agents_dir.glob("*.md")}
            for task in tasks:
                owner = task.owner
                if not owner or owner.startswith("<") or owner.startswith("{{"):
                    continue
                if owner in SPECIAL_OWNERS or owner in agent_files:
                    continue
                errors.append(f"Task {task.id} references undefined agent owner: '{owner}' (no agents/{owner}.md)")

            for agent_file in self.agents_dir.glob("*.md"):
                if agent_file.name == "TEAM.md":
                    continue
                content = agent_file.read_text(encoding="utf-8")
                if not (content.startswith("---") and "name:" in content and "description:" in content):
                    errors.append(f"Agent brief {agent_file.name} missing valid YAML frontmatter (name, description).")
                else:
                    name_m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
                    if name_m and name_m.group(1).strip() != agent_file.stem:
                        errors.append(
                            f"Agent brief {agent_file.name} frontmatter name "
                            f"'{name_m.group(1).strip()}' does not match filename."
                        )

            required = {
                "coordinator", "senior-system-architect", "senior-database-architect",
                "senior-security-engineer", "senior-backend-engineer", "senior-frontend-engineer",
                "senior-qa-architect", "senior-devops-engineer", "senior-product-designer",
                "ui-designer", "visual-qa", "senior-accessibility-engineer",
                "growth-cro-engineer", "product-analytics-engineer", "technical-seo-engineer",
                "design-system-engineer",
            }
            missing = sorted(required - agent_files)
            for name in missing:
                errors.append(f"Required agent brief missing: agents/{name}.md")

        if self.phases_dir.exists():
            for n in range(0, 7):
                matches = list(self.phases_dir.glob(f"PHASE-{n}-*.md"))
                if not matches:
                    errors.append(f"Missing phase specification: phases/PHASE-{n}-*.md")

        return errors

    def doctor(self, frontend: bool = False) -> Dict[str, Any]:
        """Environment and workspace health check."""
        checks: List[Dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
            checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

        py_ok = sys.version_info >= (3, 10)
        add("python", py_ok, f"{sys.version.split()[0]} (need >= 3.10)")
        add("git", shutil.which("git") is not None, shutil.which("git") or "git not on PATH")
        add("templates", self.templates_dir.exists(), str(self.templates_dir))
        add("agents", self.agents_dir.exists(), str(self.agents_dir))
        add("phases", self.phases_dir.exists(), str(self.phases_dir))
        project_files = (self.plan_file, self.todos_file, self.progress_file)
        project_initialized = any(path.exists() for path in project_files)
        project_required = frontend or project_initialized
        missing_detail = "run `akstack init` if this is a project" if project_required else "not initialized (expected in akstack source repo)"
        add("plan.md", self.plan_file.exists(), missing_detail, required=project_required)
        add("ToDos.md", self.todos_file.exists(), missing_detail, required=project_required)
        add("PROGRESS.md", self.progress_file.exists(), missing_detail, required=project_required)
        add("STOP", not self._stop_active(), "STOP file present — human handoff active" if self._stop_active() else "clear")

        lint_errors = self.lint()
        add("lint", len(lint_errors) == 0, f"{len(lint_errors)} issue(s)")

        node = shutil.which("node")
        npm = shutil.which("npm")
        add("node", node is not None, node or "node not on PATH", required=frontend)
        add("npm", npm is not None, npm or "npm not on PATH", required=frontend)
        add("npx", shutil.which("npx") is not None, shutil.which("npx") or "npx not on PATH", required=False)
        if frontend:
            contract = self.frontend_check("all")
            add("frontend-contract", contract["ok"], f"{len(contract['errors'])} error(s), {len(contract['warnings'])} warning(s)")

        return {
            "ok": all(c["ok"] for c in checks if c.get("required", True)),
            "frontend": frontend,
            "checks": checks,
            "lint_errors": lint_errors,
        }

    def init_project(self, project_name: str, track: str = "Product/Web", force: bool = False) -> Tuple[bool, str]:
        """Bootstrap a new project from akstack templates."""
        if not self.templates_dir.exists():
            return False, "templates/ directory missing."

        plan_tpl = self.templates_dir / "plan.template.md"
        todos_tpl = self.templates_dir / "ToDos.template.md"
        progress_tpl = self.templates_dir / "PROGRESS.template.md"

        if not (plan_tpl.exists() and todos_tpl.exists() and progress_tpl.exists()):
            return False, "Required template files missing in templates/."

        existing = [p.name for p in (self.plan_file, self.todos_file, self.progress_file) if p.exists()]
        if existing and not force:
            return False, (
                f"Refusing to overwrite existing {', '.join(existing)}. "
                "Pass --force to re-initialize."
            )

        resolved_track = Track.parse(track).value

        plan_content = plan_tpl.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)
        plan_content = plan_content.replace("{{Product/Web | AI/ML | Hybrid}}", resolved_track)
        self._atomic_write(self.plan_file, plan_content)

        todos_content = todos_tpl.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)
        self._atomic_write(self.todos_file, todos_content)

        progress_content = progress_tpl.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", project_name)
        self._atomic_write(self.progress_file, progress_content)

        self._seed_project_assets()
        self._seed_supporting_docs()

        return True, f"Project '{project_name}' successfully initialized with track '{resolved_track}'."

    def _seed_project_assets(self) -> None:
        """Copy framework assets into a project created from an installed CLI."""
        for name in ("agents", "phases"):
            source = self.asset_root / name
            target = self.workspace_root / name
            if source.exists() and not target.exists():
                shutil.copytree(source, target)
        self.agents_dir = self.workspace_root / "agents" if (self.workspace_root / "agents").exists() else self.agents_dir
        self.phases_dir = self.workspace_root / "phases" if (self.workspace_root / "phases").exists() else self.phases_dir

    def _seed_supporting_docs(self) -> None:
        copies = {
            ("docs/adr", "adr.template.md", "0000-template.md"),
            ("docs/runbooks", "runbook.template.md", "TEMPLATE.md"),
            ("design-system", "design-system.MASTER.template.md", "MASTER.md"),
            ("docs/design", "screen-spec.template.md", "SCREEN-SPEC-TEMPLATE.md"),
            ("docs/design", "accessibility-report.template.md", "accessibility-spec.md"),
            ("docs/design", "component-traceability.template.md", "component-traceability.md"),
            ("docs/analytics", "measurement-plan.template.md", "measurement-plan.md"),
            ("docs/seo", "technical-seo.template.md", "technical-seo.md"),
            ("docs/qa", "visual-report.template.md", "visual-report.md"),
            ("docs/performance", "performance-report.template.md", "report.md"),
            ("docs/qa", "frontend-quality-checklist.md", "frontend-quality-checklist.md"),
            (".", "playwright.config.template.ts", "playwright.config.ts"),
            (".github/workflows", "frontend-ci.template.yml", "frontend-quality.yml"),
        }
        for dest_dir, tpl_name, dest_name in copies:
            src = self.templates_dir / tpl_name
            if not src.exists():
                continue
            target_dir = self.workspace_root / dest_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / dest_name
            if not dest.exists():
                dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        env_tpl = self.templates_dir / "env-spec.template.md"
        if env_tpl.exists():
            docs = self.workspace_root / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            dest = docs / "env-spec.md"
            if not dest.exists():
                dest.write_text(env_tpl.read_text(encoding="utf-8"), encoding="utf-8")

        openapi_tpl = self.templates_dir / "openapi.template.yaml"
        if openapi_tpl.exists():
            docs = self.workspace_root / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            dest = docs / "openapi.yaml"
            if not dest.exists():
                dest.write_text(openapi_tpl.read_text(encoding="utf-8"), encoding="utf-8")

    def _is_git_repo(self) -> bool:
        return (self.workspace_root / ".git").exists()

    def _commit_task(self, task: Task) -> Tuple[bool, str]:
        paths = [self.todos_file, self.progress_file]
        paths.extend(self.workspace_root / file_path for file_path in task.files)
        return self._commit_paths(paths, f"{task.id}: {task.title}")

    def status_json(self) -> Dict[str, Any]:
        status = self.get_status()
        status["in_progress_tasks"] = [t.to_dict() for t in status["in_progress_tasks"]]
        status["blocked_tasks"] = [t.to_dict() for t in status["blocked_tasks"]]
        next_task = status["next_task"]
        status["next_task"] = next_task.to_dict() if next_task else None
        status["by_phase"] = {str(k): v for k, v in status["by_phase"].items()}
        return status
