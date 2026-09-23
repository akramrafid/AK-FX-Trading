"""Static checks for the frontend design-to-code contract.

The checker deliberately stays framework-agnostic. It validates the artifacts
that every frontend stack can provide and applies a few high-signal heuristics
to source files. Browser-specific evidence still comes from Playwright or the
project's chosen browser runner and is attached to the quality gate.
"""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


class FrontendContractChecker:
    """Validate design, growth, accessibility, and performance handoff artifacts."""

    SOURCE_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".tsx", ".jsx", ".vue", ".svelte", ".html"}
    SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", "coverage", "vendor"}
    HEX_IN_COMPONENT = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    PLACEHOLDER = re.compile(r"\{\{.*?\}\}")

    def __init__(self, workspace_root: Path):
        self.root = Path(workspace_root)

    def run(self, area: str = "all") -> Dict[str, Any]:
        area = area.lower()
        errors: List[str] = []
        warnings: List[str] = []
        checks: List[Dict[str, Any]] = []

        def check(name: str, ok: bool, detail: str, required: bool = True) -> None:
            checks.append({"name": name, "ok": ok, "detail": detail, "required": required})
            if required and not ok:
                errors.append(f"{name}: {detail}")

        master = self.root / "design-system" / "MASTER.md"
        if area in {"all", "design", "visual", "a11y"}:
            self._artifact_check(master, "design-system/MASTER.md", check)
            if master.exists():
                text = master.read_text(encoding="utf-8")
                required_terms = ("Color", "Typography", "Spacing", "Motion", "component", "Breakpoint")
                for term in required_terms:
                    check(f"design-system:{term}", term.lower() in text.lower(), f"missing {term} section")
                check("design-system:resolved", not self.PLACEHOLDER.search(text), "contains unresolved {{placeholders}}")

            specs = self._matching_files((self.root / "docs" / "design", self.root / "design-system" / "pages"))
            specs = [
                p for p in specs
                if p.name.lower() not in {"master.md", "template.md", "accessibility-spec.md", "component-traceability.md"}
                and "template" not in p.name.lower()
            ]
            check("screen-specs", bool(specs), "add at least one screen spec under docs/design/ or design-system/pages/")
            for spec in specs:
                text = spec.read_text(encoding="utf-8", errors="replace")
                if self.PLACEHOLDER.search(text):
                    errors.append(f"screen-specs: unresolved placeholder in {spec.relative_to(self.root).as_posix()}")
                for section in ("Visual Direction", "Responsive States", "Interaction States", "Accessibility", "Instrumentation"):
                    if section.lower() not in text.lower():
                        errors.append(f"screen-specs: {spec.relative_to(self.root).as_posix()} is missing `{section}`")
            traceability = self._first_existing(
                self.root / "docs" / "design" / "component-traceability.md",
                self.root / "design-system" / "traceability.md",
            )
            self._artifact_check(traceability, "component-traceability", check)
            if traceability:
                check("component-traceability:resolved", not self.PLACEHOLDER.search(traceability.read_text(encoding="utf-8")), "contains unresolved {{placeholders}}")

        if area in {"all", "growth", "cro"}:
            funnel = self._first_existing(
                self.root / "docs" / "discovery" / "funnel.md",
                self.root / "docs" / "growth" / "funnel.md",
            )
            self._artifact_check(funnel, "funnel-contract", check)
            measurement = self._first_existing(
                self.root / "docs" / "analytics" / "measurement-plan.md",
                self.root / "docs" / "measurement-plan.md",
            )
            self._artifact_check(measurement, "measurement-plan", check)
            seo = self._first_existing(
                self.root / "docs" / "seo" / "technical-seo.md",
                self.root / "docs" / "technical-seo.md",
            )
            self._artifact_check(seo, "technical-seo", check)
            for artifact, name in ((measurement, "measurement-plan"), (seo, "technical-seo")):
                if artifact:
                    check(f"{name}:resolved", not self.PLACEHOLDER.search(artifact.read_text(encoding="utf-8")), "contains unresolved {{placeholders}}")
            if funnel:
                check("funnel-contract:resolved", not self.PLACEHOLDER.search(funnel.read_text(encoding="utf-8")), "contains unresolved {{placeholders}}")
            if measurement:
                measurement_text = measurement.read_text(encoding="utf-8").lower()
                for section in ("north-star", "funnel", "event contract", "experiment"):
                    check(f"measurement-plan:{section}", section in measurement_text, f"missing {section} section")
            if seo:
                seo_text = seo.read_text(encoding="utf-8").lower()
                for section in ("public route", "metadata", "sitemap", "json-ld"):
                    check(f"technical-seo:{section}", section in seo_text, f"missing {section} section")

        if area in {"all", "a11y", "accessibility"}:
            a11y = self._first_existing(
                self.root / "docs" / "design" / "accessibility-spec.md",
                self.root / "docs" / "qa" / "accessibility-report.md",
            )
            self._artifact_check(a11y, "accessibility-evidence", check)
            if a11y:
                check("accessibility-evidence:resolved", not self.PLACEHOLDER.search(a11y.read_text(encoding="utf-8")), "contains unresolved {{placeholders}}")
                a11y_text = a11y.read_text(encoding="utf-8").lower()
                for section in ("automated", "manual", "decision"):
                    check(f"accessibility-evidence:{section}", section in a11y_text, f"missing {section} section")

        if area in {"all", "performance", "perf"}:
            performance = self._first_existing(
                self.root / "docs" / "performance" / "report.md",
                self.root / "docs" / "qa" / "performance-report.md",
            )
            self._artifact_check(performance, "performance-evidence", check)
            if performance:
                check("performance-evidence:resolved", not self.PLACEHOLDER.search(performance.read_text(encoding="utf-8")), "contains unresolved {{placeholders}}")
                performance_text = performance.read_text(encoding="utf-8").lower()
                for section in ("metrics", "review", "decision"):
                    check(f"performance-evidence:{section}", section in performance_text, f"missing {section} section")

        source_findings = self._source_findings()
        for finding in source_findings:
            errors.append(finding)
        if source_findings:
            check("source-heuristics", False, f"{len(source_findings)} blocking finding(s)", required=True)
        else:
            check("source-heuristics", True, "no hardcoded component colors or unsafe HTML patterns found", required=True)

        return {"ok": not errors, "area": area, "checks": checks, "errors": errors, "warnings": warnings}

    def _artifact_check(self, path: Path | None, name: str, check) -> None:
        if path is None or not path.exists():
            check(name, False, "required artifact is missing")
            return
        check(name, True, path.relative_to(self.root).as_posix())

    @staticmethod
    def _first_existing(*paths: Path) -> Path | None:
        return next((path for path in paths if path.is_file()), None)

    def _matching_files(self, roots: Iterable[Path]) -> List[Path]:
        found: List[Path] = []
        for root in roots:
            if not root.exists():
                continue
            if root.is_file():
                found.append(root)
                continue
            for path in root.rglob("*.md"):
                if not any(part in self.SKIP_DIRS for part in path.parts):
                    found.append(path)
        return found

    def _source_findings(self) -> List[str]:
        findings: List[str] = []
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in self.SOURCE_EXTENSIONS:
                continue
            if any(part in self.SKIP_DIRS for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            relative = path.relative_to(self.root).as_posix()
            if path.suffix.lower() in {".tsx", ".jsx", ".vue", ".svelte", ".html"}:
                if self.HEX_IN_COMPONENT.search(text):
                    findings.append(f"{relative}: hardcoded hex color in component markup; use semantic design tokens")
                if "dangerouslySetInnerHTML" in text or "v-html" in text:
                    findings.append(f"{relative}: raw HTML injection API found; prove sanitization and review at G3")
            if path.suffix.lower() in {".css", ".scss", ".sass", ".less"} and re.search(r"outline\s*:\s*none", text, re.IGNORECASE):
                if not re.search(r"focus-visible", text, re.IGNORECASE):
                    findings.append(f"{relative}: outline:none without a focus-visible replacement")
        return findings
