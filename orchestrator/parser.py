"""
Parser for akstack Markdown files: ToDos.md, plan.md, PROGRESS.md.
"""

import re
from typing import Dict, List, Tuple

from .models import ProjectPlan, Task, TaskStatus, TaskType, Track, VERIFY_SKIP_VALUES


class MarkdownParser:
    """Parses and manipulates akstack task ledgers, plans, and progress journals."""

    TASK_HEADER_PATTERN = re.compile(
        r"^[ \t]*- \[(?P<status>[ ~x!])\] \*\*(?P<id>P\d+-[TGFC]\d+(?:-[A-Za-z0-9]+)*)\*\*(?P<rest>.*)$",
        re.MULTILINE,
    )

    TASK_ID_PATTERN = re.compile(r"^P\d+-[TGFC]\d+(?:-[A-Za-z0-9]+)*$")

    FIELD_PATTERNS = {
        "owner": re.compile(r"^[ \t]*-[ \t]+\*\*Owner:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "deps": re.compile(r"^[ \t]*-[ \t]+\*\*Deps:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "files": re.compile(r"^[ \t]*-[ \t]+\*\*Files:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "do": re.compile(r"^[ \t]*-[ \t]+\*\*Do:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "accept": re.compile(r"^[ \t]*-[ \t]+\*\*Accept:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "verify": re.compile(r"^[ \t]*-[ \t]+\*\*Verify:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
        "gate": re.compile(r"^[ \t]*-[ \t]+\*\*Gate:\*\*[ \t]+(?P<val>.+)$", re.MULTILINE | re.IGNORECASE),
    }

    PHASE_HEADER_PATTERN = re.compile(r"^## Phase (\d+)", re.MULTILINE)

    @staticmethod
    def parse_status_char(char: str) -> TaskStatus:
        if char == "x":
            return TaskStatus.COMPLETED
        if char == "~":
            return TaskStatus.IN_PROGRESS
        if char == "!":
            return TaskStatus.BLOCKED
        return TaskStatus.PENDING

    @staticmethod
    def status_to_char(status: TaskStatus) -> str:
        if status == TaskStatus.COMPLETED:
            return "x"
        if status == TaskStatus.IN_PROGRESS:
            return "~"
        if status == TaskStatus.BLOCKED:
            return "!"
        return " "

    @classmethod
    def parse_todos(cls, content: str) -> List[Task]:
        """Parse tasks from ToDos.md content."""
        tasks: List[Task] = []
        matches = list(cls.TASK_HEADER_PATTERN.finditer(content))
        for i, match in enumerate(matches):
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            raw_block = content[start_pos:end_pos].strip()

            status_char = match.group("status")
            task_id = match.group("id")
            rest_of_header = match.group("rest")

            if "-G" in task_id:
                task_type = TaskType.GATE
            elif "-F" in task_id:
                task_type = TaskType.FINDING
            elif "-C" in task_id:
                task_type = TaskType.CHANGE
            else:
                task_type = TaskType.STANDARD

            phase_m = re.match(r"P(\d+)-", task_id)
            phase = int(phase_m.group(1)) if phase_m else 1

            is_senior = "★" in rest_of_header or "senior" in rest_of_header.lower()
            is_human = "🧑" in rest_of_header or "HUMAN" in rest_of_header

            title = rest_of_header.replace("★", "").replace("🧑 HUMAN", "").replace("🧑", "").strip()
            title = re.sub(r"^HUMAN\s+", "", title).strip()

            owner = cls._extract_field(raw_block, "owner")
            deps_raw = cls._extract_field(raw_block, "deps")
            files_raw = cls._extract_field(raw_block, "files")
            do = cls._extract_field(raw_block, "do")
            accept = cls._extract_field(raw_block, "accept")
            verify = cls._extract_field(raw_block, "verify")
            gate_id = cls._extract_field(raw_block, "gate")
            owner = cls._clean_owner(owner)

            tasks.append(Task(
                id=task_id,
                title=title,
                phase=phase,
                task_type=task_type,
                status=cls.parse_status_char(status_char),
                owner=owner,
                deps=cls._clean_list(deps_raw),
                files=cls._clean_files(files_raw),
                do=do,
                accept=accept,
                verify=cls.clean_verify(verify),
                is_senior=is_senior,
                is_human=is_human,
                gate_id=cls._clean_scalar(gate_id),
                raw_text=raw_block,
            ))

        return tasks

    @classmethod
    def _extract_field(cls, block: str, field_name: str) -> str:
        pattern = cls.FIELD_PATTERNS.get(field_name)
        if not pattern:
            return ""
        m = pattern.search(block)
        return m.group("val").strip() if m else ""

    @staticmethod
    def _clean_owner(raw: str) -> str:
        if not raw:
            return ""
        owner = raw.strip().strip("`")
        owner = re.split(r"\s*/\s*|\s*\(|,", owner)[0].strip()
        return owner

    @staticmethod
    def _clean_scalar(raw: str) -> str:
        return (raw or "").strip().strip("`").strip()

    @classmethod
    def clean_verify(cls, raw: str) -> str:
        """Normalize a markdown Verify field into an executable command."""
        value = cls._clean_scalar(raw)
        if value.startswith("```") and value.endswith("```"):
            value = value[3:-3].strip()
            lines = value.splitlines()
            if lines and re.fullmatch(r"[A-Za-z0-9_-]+", lines[0].strip()):
                value = "\n".join(lines[1:]).strip()
        return value.strip("`").strip()

    @staticmethod
    def _clean_list(raw: str) -> List[str]:
        if not raw or raw in ("—", "-", "none", "None", ""):
            return []
        items = re.split(r"[,;]\s*", raw)
        cleaned = []
        for item in items:
            it = item.strip().strip("`")
            if it and it not in ("—", "-"):
                cleaned.append(it)
        return cleaned

    @staticmethod
    def _clean_files(raw: str) -> List[str]:
        if not raw or raw in ("—", "-", "none", "None"):
            return []
        extracted = re.findall(r"`([^`]+)`", raw)
        if extracted:
            return [f.strip() for f in extracted if f.strip()]
        return [f.strip() for f in raw.split(",") if f.strip() and f.strip() != "—"]

    @staticmethod
    def should_skip_verify(verify: str) -> bool:
        return MarkdownParser.clean_verify(verify).lower() in VERIFY_SKIP_VALUES

    @classmethod
    def update_task_status(cls, content: str, task_id: str, new_status: TaskStatus) -> Tuple[str, bool]:
        """Update a task's checkbox status in ToDos.md content."""
        char = cls.status_to_char(new_status)
        pattern = re.compile(
            rf"^([ \t]*- \[)[ ~x!](] \*\*{re.escape(task_id)}\*\*)",
            re.MULTILINE,
        )
        new_content, count = pattern.subn(rf"\g<1>{char}\g<2>", content)
        return new_content, count > 0

    @classmethod
    def append_task_block(cls, content: str, block: str, after_id: str = "") -> str:
        """Insert a task block after a given task id, or append at end of file."""
        block = block.rstrip() + "\n"
        if after_id:
            pattern = re.compile(
                rf"(^[ \t]*- \[[ ~x!]\] \*\*{re.escape(after_id)}\*\*.*?)(?=^[ \t]*- \[[ ~x!]\] \*\*P|\Z)",
                re.MULTILINE | re.DOTALL,
            )
            match = pattern.search(content)
            if match:
                insert_at = match.end()
                prefix = content[:insert_at].rstrip() + "\n\n"
                suffix = content[insert_at:].lstrip("\n")
                return prefix + block + "\n" + suffix
        if not content.endswith("\n"):
            content += "\n"
        return content + "\n" + block

    @classmethod
    def parse_plan(cls, content: str) -> ProjectPlan:
        """Extract high level metadata from plan.md."""
        title_m = re.search(r"^#\s+(.+?)\s+(?:—|-)\s+Plan\s*$", content, re.MULTILINE | re.IGNORECASE)
        if not title_m:
            title_m = re.search(r"^#\s+(.+?)(?:—|-|\n)", content, re.MULTILINE)
        name = title_m.group(1).strip() if title_m else "Project"

        track_m = re.search(r"## 0\.\s*Track\s*\n+\*?\*?([A-Za-z/]+)", content)
        track_raw = track_m.group(1).strip() if track_m else Track.PRODUCT_WEB.value
        track = Track.parse(track_raw).value

        hard_rules = cls._bullet_section(content, r"## 3\.\s*Domain & Hard Rules")
        non_goals = cls._bullet_section(content, r"## 8\.\s*Non-Goals")
        if not non_goals:
            non_goals = cls._bullet_section(content, r"## 7\.\s*Non-Goals")
        open_questions = cls._bullet_section(content, r"## 9\.\s*Open Questions")
        if not open_questions:
            open_questions = cls._bullet_section(content, r"## 8\.\s*Open Questions")
        slos = cls._bullet_section(content, r"## 6\.\s*Service Level")

        stack = cls._kv_section(content, r"## 4\.\s*Architecture & Stack")

        return ProjectPlan(
            project_name=name,
            track=track,
            hard_rules=hard_rules,
            frontend=stack.get("frontend", ""),
            backend=stack.get("backend", ""),
            database=stack.get("database & storage", stack.get("database", "")),
            auth=stack.get("auth & security", stack.get("auth", "")),
            infra=stack.get("hosting/infra", stack.get("infra", "")),
            ai_stack=stack.get("ai/ml stack (if track includes ai/ml)", stack.get("ai/ml stack", "")),
            slos=slos,
            non_goals=non_goals,
            open_questions=open_questions,
        )

    @classmethod
    def _bullet_section(cls, content: str, header_pattern: str) -> List[str]:
        section = re.search(header_pattern + r"\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL | re.IGNORECASE)
        if not section:
            return []
        items: List[str] = []
        for line in section.group(1).splitlines():
            line = line.strip()
            if line and (line.startswith("-") or re.match(r"^\d+\.", line)):
                cleaned = re.sub(r"^(?:-|\d+\.)\s*", "", line).strip()
                cleaned = re.sub(r"^\*\*(.+?)\*\*:\s*", "", cleaned)
                if cleaned and not cleaned.startswith("{{"):
                    items.append(cleaned)
        return items

    @staticmethod
    def _kv_section(content: str, header_pattern: str) -> Dict[str, str]:
        section = re.search(header_pattern + r"\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL | re.IGNORECASE)
        if not section:
            return {}
        result: Dict[str, str] = {}
        for line in section.group(1).splitlines():
            m = re.match(r"^- \*\*(.+?):\*\*\s*(.+)$", line.strip())
            if m:
                result[m.group(1).strip().lower()] = m.group(2).strip()
        return result
