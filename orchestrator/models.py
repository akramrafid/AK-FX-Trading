"""
Data models for the Akram-Stack (akstack) orchestration engine.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class TaskStatus(str, Enum):
    PENDING = "PENDING"          # - [ ]
    IN_PROGRESS = "IN_PROGRESS"  # - [~]
    COMPLETED = "COMPLETED"      # - [x]
    BLOCKED = "BLOCKED"          # - [!]


class TaskType(str, Enum):
    STANDARD = "STANDARD"  # P<n>-T<nnn>
    GATE = "GATE"          # P<n>-G<n> or P<n>-G<n>-SUFFIX
    FINDING = "FINDING"    # P<n>-F<nn>
    CHANGE = "CHANGE"      # P<n>-C<nn>


class Track(str, Enum):
    PRODUCT_WEB = "Product/Web"
    AI_ML = "AI/ML"
    HYBRID = "Hybrid"

    @classmethod
    def parse(cls, raw: str) -> "Track":
        normalized = (raw or "").strip().lower().replace(" ", "").replace("_", "/")
        mapping = {
            "product/web": cls.PRODUCT_WEB,
            "productweb": cls.PRODUCT_WEB,
            "web": cls.PRODUCT_WEB,
            "ai/ml": cls.AI_ML,
            "aiml": cls.AI_ML,
            "ml": cls.AI_ML,
            "hybrid": cls.HYBRID,
        }
        return mapping.get(normalized, cls.PRODUCT_WEB)


VERIFY_SKIP_VALUES = frozenset({
    "", "—", "-", "none", "n/a", "na", "manual", "manual review",
    "human review", "human", "skip", "tbd",
})

SPECIAL_OWNERS = frozenset({
    "coordinator", "akstack", "human", "cli", "orchestrator",
})

GATE_ORDER = (
    "G0-ML",
    "G1",
    "G2",
    "G3",
    "G3-P",
    "G4",
    "G4-CRO",
    "G4-A11Y",
    "G5",
    "G6",
)


@dataclass
class Task:
    id: str
    title: str
    phase: int
    task_type: TaskType
    status: TaskStatus
    owner: str = ""
    deps: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    do: str = ""
    accept: str = ""
    verify: str = ""
    is_senior: bool = False
    is_human: bool = False
    gate_id: str = ""
    raw_text: str = ""
    line_start: int = 0
    line_end: int = 0

    @property
    def file_set(self) -> Set[str]:
        """Normalized set of affected files for collision checking."""
        return {
            f.strip().replace("\\", "/").rstrip("/").lower()
            for f in self.files
            if f.strip()
        }

    @property
    def gate_key(self) -> str:
        """Canonical gate key, e.g. P5-G4-A11Y -> G4-A11Y, P5-G1 -> G1."""
        if self.task_type != TaskType.GATE:
            return ""
        parts = self.id.split("-", 1)
        return parts[1] if len(parts) == 2 else self.id

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["task_type"] = self.task_type.value
        payload["files"] = list(self.files)
        payload["deps"] = list(self.deps)
        return payload


@dataclass
class Gate:
    id: str
    phase: int
    title: str
    owner: str
    status: TaskStatus
    review_focus: str = ""
    open_findings: List[str] = field(default_factory=list)


@dataclass
class ProjectPlan:
    project_name: str
    track: str = Track.PRODUCT_WEB.value
    mission: str = ""
    hard_rules: List[str] = field(default_factory=list)
    frontend: str = ""
    backend: str = ""
    database: str = ""
    auth: str = ""
    infra: str = ""
    ai_stack: str = ""
    slos: List[str] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
