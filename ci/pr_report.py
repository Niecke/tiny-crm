#!/usr/bin/env python3
"""Render one markdown summary of the test suites.

Reads whatever CI produced — a JUnit XML and a Cobertura coverage XML per suite,
from pytest for the backend and Vitest for the frontend — and writes a table to
stdout. Missing inputs are reported as such rather than skipped, because a suite
that did not produce a report usually means the job died before running it.

    python3 ci/pr_report.py --backend-junit backend/junit.xml ... > comment.md
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Suite:
    name: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float | None = None
    coverage: float | None = None
    note: str | None = None
    failures: list[str] | None = None

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped

    @property
    def status(self) -> str:
        if self.note and self.total == 0:
            return "⚠️"
        return "✅" if self.failed == 0 else "❌"


def _read_junit(path: Path, suite: Suite) -> None:
    """JUnit XML: pytest writes one <testsuite>, Vitest one per test file."""
    root = ElementTree.parse(path).getroot()
    elements = [root] if root.tag == "testsuite" else root.findall("testsuite")
    if not elements:
        suite.note = f"no testsuite element in {path.name}"
        return

    total = sum(int(e.get("tests", 0)) for e in elements)
    failed = sum(int(e.get("failures", 0)) + int(e.get("errors", 0)) for e in elements)
    skipped = sum(int(e.get("skipped", 0)) for e in elements)
    suite.failed = failed
    suite.skipped = skipped
    suite.passed = total - failed - skipped
    # Vitest's files run in parallel, so their times add up to more than the
    # run took; its root element has the wall time. pytest's root has none.
    duration = root.get("time") if root.tag == "testsuites" else None
    if duration is None:
        times = [float(t) for e in elements if (t := e.get("time"))]
        suite.duration = sum(times) if times else None
    else:
        suite.duration = float(duration)

    suite.failures = [
        f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
        for e in elements
        for case in e.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]


def _read_coverage_xml(path: Path, suite: Suite) -> None:
    """Cobertura XML (coverage.py, Vitest): line-rate on the root element."""
    root = ElementTree.parse(path).getroot()
    line_rate = root.get("line-rate")
    if line_rate is not None:
        suite.coverage = float(line_rate) * 100


def _collect(name: str, results: Path | None, coverage: Path | None) -> Suite:
    suite = Suite(name=name)
    if results is None or not results.exists():
        suite.note = "no test report — the job did not get that far"
        return suite

    try:
        _read_junit(results, suite)
    except ElementTree.ParseError as exc:
        suite.note = f"unreadable report ({type(exc).__name__})"
        return suite

    if coverage is not None and coverage.exists():
        _read_coverage_xml(coverage, suite)
    return suite


def _cell(value: float | None, unit: str) -> str:
    return "–" if value is None else f"{value:.1f}{unit}"


def render(suites: list[Suite]) -> str:
    lines = [
        "### Test results",
        "",
        "| Suite | | Passed | Failed | Skipped | Coverage | Time |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for suite in suites:
        lines.append(
            f"| {suite.name} | {suite.status} | {suite.passed} | {suite.failed} | "
            f"{suite.skipped} | {_cell(suite.coverage, '%')} | {_cell(suite.duration, 's')} |"
        )

    for suite in suites:
        if suite.note:
            lines += ["", f"> **{suite.name}:** {suite.note}"]
        if suite.failures:
            lines += ["", f"**{suite.name} failures**"]
            lines += [f"- `{name}`" for name in suite.failures[:10]]
            if len(suite.failures) > 10:
                lines.append(f"- …and {len(suite.failures) - 10} more")

    footer = (
        "Line coverage, as a rough signal — it is not a gate. The frontend figure leaves"
        " out the route pages, which the integration test drives instead."
    )
    lines += ["", f"<sub>{footer}</sub>"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-junit", type=Path)
    parser.add_argument("--backend-coverage", type=Path)
    parser.add_argument("--frontend-junit", type=Path)
    parser.add_argument("--frontend-coverage", type=Path)
    args = parser.parse_args()

    suites = [
        _collect("Backend", args.backend_junit, args.backend_coverage),
        _collect("Frontend", args.frontend_junit, args.frontend_coverage),
    ]
    print(render(suites))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
