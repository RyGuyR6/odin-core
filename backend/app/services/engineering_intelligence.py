"""Evidence-backed engineering analysis built on Repository Intelligence."""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.repositories.security import safe_child
from app.services.repository_intelligence import (
    RepositoryIntelligencePayload,
    repository_intelligence_service,
)


Severity = Literal["info", "low", "medium", "high", "critical"]


class EngineeringEvidence(BaseModel):
    path: str
    line: int | None = None
    detail: str


class EngineeringFinding(BaseModel):
    id: str
    category: str
    title: str
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    rationale: str
    recommendation: str
    evidence: list[EngineeringEvidence] = Field(default_factory=list)


class ComplexityHotspot(BaseModel):
    path: str
    score: float = Field(ge=0)
    lines: int = Field(ge=0)
    symbol_count: int = Field(ge=0)
    dependency_fan_in: int = Field(ge=0)
    dependency_fan_out: int = Field(ge=0)
    reasons: list[str] = Field(default_factory=list)


class ImpactAssessment(BaseModel):
    targets: list[str] = Field(default_factory=list)
    direct_dependencies: list[str] = Field(default_factory=list)
    direct_dependents: list[str] = Field(default_factory=list)
    transitive_dependents: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    risk_level: Severity = "low"
    risk_score: float = Field(default=0, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)


class EngineeringIntelligenceReport(BaseModel):
    repository: str
    indexed_revision: str | None = None
    objective: str | None = None
    architecture: dict[str, Any]
    detected_patterns: list[dict[str, Any]] = Field(default_factory=list)
    complexity_hotspots: list[ComplexityHotspot] = Field(default_factory=list)
    technical_debt: list[EngineeringFinding] = Field(default_factory=list)
    refactoring_opportunities: list[EngineeringFinding] = Field(default_factory=list)
    impact: ImpactAssessment
    overall_risk: Severity
    risk_score: float = Field(ge=0, le=100)
    validation_recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    metrics: dict[str, int | float] = Field(default_factory=dict)


class EngineeringIntelligenceService:
    """Turns the canonical repository index into deterministic engineering advice."""

    MAX_SOURCE_BYTES = 1_000_000

    def analyze(
        self,
        repository: str,
        *,
        paths: list[str] | None = None,
        objective: str | None = None,
    ) -> EngineeringIntelligenceReport:
        record = repository_intelligence_service.get_scan(repository)
        if record is None or record.payload is None or record.status != "ready":
            raise ValueError(
                f"Repository intelligence is not ready for {repository}. Scan it first."
            )
        payload = record.payload
        inventory_paths = {item.path for item in payload.inventory}
        targets = sorted(set(paths or []))
        unknown = [path for path in targets if path not in inventory_paths]
        if unknown:
            raise ValueError(f"Paths are not present in the repository index: {unknown}")

        source_metrics = self._source_metrics(payload)
        fan_in, fan_out, dependencies, dependents = self._graph_metrics(payload)
        hotspots = self._hotspots(
            payload, source_metrics, fan_in, fan_out, targets=targets
        )
        debt = self._debt_findings(payload, source_metrics, hotspots)
        patterns = self._patterns(payload)
        impact = self._impact(
            payload,
            targets=targets,
            dependencies=dependencies,
            dependents=dependents,
            hotspots=hotspots,
        )
        refactors = self._refactoring_findings(payload, hotspots, debt)
        risk_score = min(
            100.0,
            round(
                impact.risk_score
                + sum(self._severity_weight(item.severity) for item in debt[:8])
                + min(15, len(payload.dependency_graph.circular_dependencies) * 5),
                1,
            ),
        )
        architecture_categories = {
            item.category: len(item.files) for item in payload.architecture
        }
        limitations = [
            "Static analysis cannot prove runtime behavior or business correctness.",
            "Complexity for non-Python files uses structural line and symbol heuristics.",
        ]
        if record.payload.indexed_revision is None:
            limitations.append("The index has no source revision, so freshness is uncertain.")

        return EngineeringIntelligenceReport(
            repository=repository,
            indexed_revision=payload.indexed_revision,
            objective=objective,
            architecture={
                "project_purpose": payload.summary.project_purpose,
                "languages": payload.summary.languages,
                "frameworks": payload.summary.frameworks,
                "categories": architecture_categories,
                "entry_points": payload.dependency_graph.entry_points,
                "major_modules": [
                    item.model_dump(mode="json")
                    for item in payload.summary.major_modules
                ],
                "circular_dependencies": payload.dependency_graph.circular_dependencies,
            },
            detected_patterns=patterns,
            complexity_hotspots=hotspots,
            technical_debt=debt,
            refactoring_opportunities=refactors,
            impact=impact,
            overall_risk=self._risk_level(risk_score),
            risk_score=risk_score,
            validation_recommendations=self._validation_recommendations(
                payload, impact
            ),
            limitations=limitations,
            metrics={
                "files_analyzed": len(source_metrics),
                "symbols_analyzed": len(payload.symbols),
                "dependency_edges_analyzed": len(payload.dependency_graph.edges),
                "findings": len(debt) + len(refactors),
            },
        )

    def _source_metrics(
        self, payload: RepositoryIntelligencePayload
    ) -> dict[str, dict[str, int]]:
        root = Path(payload.local_path)
        symbols = Counter(item.file_path for item in payload.symbols)
        metrics: dict[str, dict[str, int]] = {}
        for item in payload.inventory:
            if item.binary or item.size > self.MAX_SOURCE_BYTES:
                continue
            if item.language is None and Path(item.path).suffix not in {
                ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs"
            }:
                continue
            try:
                content = safe_child(root, item.path).read_text(
                    encoding="utf-8", errors="ignore"
                )
            except (OSError, ValueError):
                continue
            lines = content.splitlines()
            branches = len(
                re.findall(
                    r"\b(if|elif|else|for|while|case|catch|except|switch)\b", content
                )
            )
            todos = len(re.findall(r"\b(?:TODO|FIXME|HACK|XXX)\b", content, re.I))
            functions = 0
            max_function_lines = 0
            if item.path.endswith(".py"):
                try:
                    tree = ast.parse(content)
                    functions_nodes = [
                        node
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    functions = len(functions_nodes)
                    max_function_lines = max(
                        (
                            (getattr(node, "end_lineno", node.lineno) or node.lineno)
                            - node.lineno
                            + 1
                            for node in functions_nodes
                        ),
                        default=0,
                    )
                except SyntaxError:
                    pass
            metrics[item.path] = {
                "lines": len(lines),
                "branches": branches,
                "todos": todos,
                "symbols": symbols[item.path],
                "functions": functions,
                "max_function_lines": max_function_lines,
            }
        return metrics

    @staticmethod
    def _graph_metrics(payload: RepositoryIntelligencePayload):
        fan_in: Counter[str] = Counter()
        fan_out: Counter[str] = Counter()
        dependencies: dict[str, set[str]] = defaultdict(set)
        dependents: dict[str, set[str]] = defaultdict(set)
        for edge in payload.dependency_graph.edges:
            if edge.external or not edge.target:
                continue
            fan_out[edge.source] += 1
            fan_in[edge.target] += 1
            dependencies[edge.source].add(edge.target)
            dependents[edge.target].add(edge.source)
        return fan_in, fan_out, dependencies, dependents

    def _hotspots(
        self, payload, source_metrics, fan_in, fan_out, *, targets
    ) -> list[ComplexityHotspot]:
        result: list[ComplexityHotspot] = []
        for path, metric in source_metrics.items():
            score = (
                min(35, metric["lines"] / 20)
                + min(25, metric["branches"] * 1.5)
                + min(20, metric["symbols"] * 1.5)
                + min(20, (fan_in[path] + fan_out[path]) * 2)
            )
            reasons = []
            if metric["lines"] >= 400:
                reasons.append(f"large file ({metric['lines']} lines)")
            if metric["branches"] >= 30:
                reasons.append(f"high branch density ({metric['branches']} branches)")
            if metric["max_function_lines"] >= 80:
                reasons.append(
                    f"long function ({metric['max_function_lines']} lines)"
                )
            if fan_in[path] >= 8:
                reasons.append(f"high fan-in ({fan_in[path]} dependents)")
            if fan_out[path] >= 10:
                reasons.append(f"high fan-out ({fan_out[path]} dependencies)")
            if reasons or path in targets:
                result.append(
                    ComplexityHotspot(
                        path=path,
                        score=round(score, 1),
                        lines=metric["lines"],
                        symbol_count=metric["symbols"],
                        dependency_fan_in=fan_in[path],
                        dependency_fan_out=fan_out[path],
                        reasons=reasons or ["explicit analysis target"],
                    )
                )
        return sorted(result, key=lambda item: (-item.score, item.path))[:20]

    def _debt_findings(self, payload, source_metrics, hotspots):
        findings: list[EngineeringFinding] = []
        for path, metric in sorted(source_metrics.items()):
            if metric["todos"]:
                findings.append(
                    EngineeringFinding(
                        id=f"todo:{path}",
                        category="technical_debt",
                        title="Unresolved maintenance markers",
                        severity="medium" if metric["todos"] >= 3 else "low",
                        confidence=0.98,
                        rationale="TODO/FIXME/HACK markers record unfinished or risky work.",
                        recommendation="Triage the markers and convert actionable items into tracked work.",
                        evidence=[
                            EngineeringEvidence(
                                path=path,
                                detail=f"{metric['todos']} maintenance marker(s)",
                            )
                        ],
                    )
                )
        for cycle in payload.dependency_graph.circular_dependencies:
            findings.append(
                EngineeringFinding(
                    id="cycle:" + "|".join(cycle),
                    category="dependency",
                    title="Circular dependency",
                    severity="high",
                    confidence=1.0,
                    rationale="The indexed import graph contains a dependency cycle.",
                    recommendation="Introduce a stable boundary or move shared contracts below the cycle.",
                    evidence=[
                        EngineeringEvidence(path=path, detail="Member of dependency cycle")
                        for path in cycle
                    ],
                )
            )
        for hotspot in hotspots:
            if hotspot.score < 35:
                continue
            findings.append(
                EngineeringFinding(
                    id=f"hotspot:{hotspot.path}",
                    category="complexity",
                    title="Complexity hotspot",
                    severity="high" if hotspot.score >= 70 else "medium",
                    confidence=0.86,
                    rationale="; ".join(hotspot.reasons),
                    recommendation="Split responsibilities behind tested interfaces before adding behavior.",
                    evidence=[
                        EngineeringEvidence(
                            path=hotspot.path,
                            detail=f"heuristic complexity score {hotspot.score}",
                        )
                    ],
                )
            )
        return sorted(
            findings,
            key=lambda item: (-self._severity_weight(item.severity), item.id),
        )

    @staticmethod
    def _patterns(payload):
        categories = {item.category: item.files for item in payload.architecture}
        patterns = []
        for name, required in (
            ("Layered service architecture", ("api_routes", "services", "models")),
            ("Controller/service separation", ("controllers", "services")),
            ("Repository/data-access boundary", ("services", "database_layer")),
            ("Component architecture", ("components",)),
        ):
            evidence = sorted(
                {path for category in required for path in categories.get(category, [])}
            )
            if all(categories.get(category) for category in required):
                patterns.append(
                    {
                        "name": name,
                        "confidence": round(min(0.98, 0.7 + len(evidence) * 0.02), 2),
                        "evidence": evidence[:12],
                    }
                )
        if payload.dependency_graph.entry_points:
            patterns.append(
                {
                    "name": "Explicit application entry points",
                    "confidence": 0.95,
                    "evidence": payload.dependency_graph.entry_points[:12],
                }
            )
        return patterns

    @staticmethod
    def _refactoring_findings(payload, hotspots, debt):
        findings = []
        for hotspot in hotspots[:5]:
            if hotspot.score < 25:
                continue
            findings.append(
                EngineeringFinding(
                    id=f"refactor:{hotspot.path}",
                    category="refactoring",
                    title="Extract cohesive responsibilities",
                    severity="medium" if hotspot.score >= 50 else "low",
                    confidence=0.78,
                    rationale="The file combines structural size, symbols, and dependency pressure.",
                    recommendation="Identify one independently testable responsibility and extract it without changing public behavior.",
                    evidence=[
                        EngineeringEvidence(
                            path=hotspot.path,
                            detail=", ".join(hotspot.reasons),
                        )
                    ],
                )
            )
        return findings

    def _impact(self, payload, *, targets, dependencies, dependents, hotspots):
        if not targets:
            return ImpactAssessment()
        direct_dependencies = sorted(
            {item for path in targets for item in dependencies.get(path, set())}
        )
        direct_dependents = sorted(
            {item for path in targets for item in dependents.get(path, set())}
        )
        visited = set(targets)
        frontier = list(targets)
        transitive = set()
        while frontier:
            current = frontier.pop()
            for item in dependents.get(current, set()):
                if item in visited:
                    continue
                visited.add(item)
                transitive.add(item)
                frontier.append(item)
        tests = sorted(
            path
            for path in transitive | set(direct_dependents) | set(targets)
            if self._is_test(path)
        )
        hotspot_scores = {item.path: item.score for item in hotspots}
        score = min(
            100.0,
            10
            + len(direct_dependents) * 8
            + len(transitive) * 3
            + len(direct_dependencies) * 2
            + max((hotspot_scores.get(path, 0) for path in targets), default=0) * 0.4
            + (15 if not tests else 0),
        )
        reasons = [
            f"{len(direct_dependents)} direct and {len(transitive)} transitive dependents",
            f"{len(tests)} related tests discovered",
        ]
        return ImpactAssessment(
            targets=targets,
            direct_dependencies=direct_dependencies,
            direct_dependents=direct_dependents,
            transitive_dependents=sorted(transitive),
            related_tests=tests,
            risk_level=self._risk_level(score),
            risk_score=round(score, 1),
            reasons=reasons,
        )

    @staticmethod
    def _validation_recommendations(payload, impact):
        recommendations = []
        if impact.related_tests:
            recommendations.append(
                "Run related tests: " + ", ".join(impact.related_tests[:8])
            )
        elif impact.targets:
            recommendations.append(
                "Add or identify focused tests for the requested change targets."
            )
        frameworks = ", ".join(payload.summary.test_framework)
        if frameworks:
            recommendations.append(f"Run the repository test suite ({frameworks}).")
        if payload.dependency_graph.circular_dependencies:
            recommendations.append(
                "Re-scan the dependency graph and confirm no new cycles are introduced."
            )
        recommendations.append("Review the final diff against the reported impact set.")
        return recommendations

    @staticmethod
    def _severity_weight(severity: Severity) -> int:
        return {"info": 0, "low": 2, "medium": 5, "high": 10, "critical": 20}[severity]

    @staticmethod
    def _risk_level(score: float) -> Severity:
        if score >= 80:
            return "critical"
        if score >= 55:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    @staticmethod
    def _is_test(path: str) -> bool:
        name = Path(path).name.lower()
        return (
            "/tests/" in f"/{path.lower()}"
            or name.startswith("test_")
            or ".test." in name
            or ".spec." in name
        )


engineering_intelligence_service = EngineeringIntelligenceService()
