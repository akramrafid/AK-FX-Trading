"""
Dependency graph resolution, cycle detection, topological sorting,
and parallel file contention checking for akstack tasks.
"""

from typing import Dict, List, Optional

from .models import Task, TaskStatus


class DependencyGraph:
    """Manages the task dependency DAG and parallel wave scheduling."""

    def __init__(self, tasks: List[Task]):
        self.tasks: List[Task] = tasks
        self.task_map: Dict[str, Task] = {t.id: t for t in tasks}
        self.adj: Dict[str, List[str]] = {t.id: [] for t in tasks}
        self._build_graph()

    def _build_graph(self) -> None:
        """Populate adjacency list where u -> v means v depends on u."""
        for task in self.tasks:
            for dep_id in task.deps:
                if dep_id in self.task_map:
                    self.adj[dep_id].append(task.id)

    def detect_cycles(self) -> Optional[List[str]]:
        """
        Detect cycles in the dependency graph using 3-color DFS.
        Returns the cycle path if detected, or None.
        """
        state: Dict[str, int] = {t_id: 0 for t_id in self.task_map}
        parent: Dict[str, Optional[str]] = {t_id: None for t_id in self.task_map}
        cycle_path: List[str] = []

        def dfs(node: str) -> bool:
            state[node] = 1
            task = self.task_map[node]
            for dep_id in task.deps:
                if dep_id not in self.task_map:
                    continue
                if state[dep_id] == 1:
                    curr = node
                    cycle_path.append(dep_id)
                    while curr and curr != dep_id:
                        cycle_path.append(curr)
                        curr = parent.get(curr)
                    cycle_path.append(dep_id)
                    cycle_path.reverse()
                    return True
                if state[dep_id] == 0:
                    parent[dep_id] = node
                    if dfs(dep_id):
                        return True
            state[node] = 2
            return False

        for node in self.task_map:
            if state[node] == 0 and dfs(node):
                return cycle_path
        return None

    def get_runnable_tasks(self, phase: Optional[int] = None) -> List[Task]:
        """
        Return all tasks whose dependencies are 100% COMPLETED (- [x])
        and whose own status is PENDING (- [ ]).
        """
        runnable: List[Task] = []
        for task in self.tasks:
            if phase is not None and task.phase != phase:
                continue
            if task.status != TaskStatus.PENDING:
                continue
            if self.deps_satisfied(task):
                runnable.append(task)
        return runnable

    def deps_satisfied(self, task: Task) -> bool:
        for dep_id in task.deps:
            dep_task = self.task_map.get(dep_id)
            if not dep_task or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    def unmet_deps(self, task: Task) -> List[str]:
        unmet: List[str] = []
        for dep_id in task.deps:
            dep_task = self.task_map.get(dep_id)
            if not dep_task:
                unmet.append(f"{dep_id} (missing)")
            elif dep_task.status != TaskStatus.COMPLETED:
                unmet.append(f"{dep_id} ({dep_task.status.value})")
        return unmet

    def schedule_parallel_waves(self, tasks: List[Task]) -> List[List[Task]]:
        """
        Partition runnable tasks into conflict-free waves.
        Tasks in the same wave have strictly disjoint file sets.
        Tasks with empty Files: lists are never considered parallel-safe.
        """
        waves: List[List[Task]] = []

        for task in tasks:
            placed = False
            task_files = task.file_set

            for wave in waves:
                has_collision = False
                for wave_task in wave:
                    if self._files_collide(task_files, wave_task.file_set):
                        has_collision = True
                        break
                if not has_collision:
                    wave.append(task)
                    placed = True
                    break

            if not placed:
                waves.append([task])

        return waves

    @staticmethod
    def _files_collide(a: set, b: set) -> bool:
        if not a or not b:
            return True
        for left in a:
            for right in b:
                if left == right:
                    return True
                # Treat a declared directory and any child path as a conflict.
                if left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/"):
                    return True
        return False

    def topological_order(self) -> Optional[List[Task]]:
        if self.detect_cycles():
            return None
        indegree = {t.id: 0 for t in self.tasks}
        for task in self.tasks:
            for dep_id in task.deps:
                if dep_id in indegree:
                    indegree[task.id] += 1
        queue = [t.id for t in self.tasks if indegree[t.id] == 0]
        ordered: List[Task] = []
        while queue:
            node = queue.pop(0)
            ordered.append(self.task_map[node])
            for nxt in self.adj[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if len(ordered) != len(self.tasks):
            return None
        return ordered

    def to_mermaid(self) -> str:
        """Export dependency graph as a Mermaid flowchart diagram."""
        lines = ["flowchart TD"]
        lines.append("  classDef pending fill:#f9f9f9,stroke:#999,stroke-width:1px;")
        lines.append("  classDef inprogress fill:#fff3cd,stroke:#ffc107,stroke-width:2px;")
        lines.append("  classDef completed fill:#d4edda,stroke:#28a745,stroke-width:2px;")
        lines.append("  classDef blocked fill:#f8d7da,stroke:#dc3545,stroke-width:2px;")

        for task in self.tasks:
            status_class = {
                TaskStatus.PENDING: "pending",
                TaskStatus.IN_PROGRESS: "inprogress",
                TaskStatus.COMPLETED: "completed",
                TaskStatus.BLOCKED: "blocked",
            }.get(task.status, "pending")

            senior_marker = "★ " if task.is_senior else ""
            escaped_title = task.title.replace('"', "'")
            lines.append(f'  {task.id}["{senior_marker}{task.id}: {escaped_title}"]:::{status_class}')

            for dep_id in task.deps:
                if dep_id in self.task_map:
                    lines.append(f"  {dep_id} --> {task.id}")

        return "\n".join(lines)
