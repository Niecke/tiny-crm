#!/usr/bin/env python3
"""Render one markdown summary of both test suites.

Reads whatever CI produced — pytest's JUnit XML and coverage XML, flutter test's
JSON report and its lcov file — and writes a table to stdout. Missing inputs are
reported as such rather than skipped, because a suite that did not produce a
report usually means the job died before running it.

    python3 ci/pr_report.py --backend-junit backend/junit.xml ... > comment.md
"""

from __future__ import annotations

import argparse
import json
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
    """pytest --junitxml: one <testsuite> with counts as attributes."""
    root = ElementTree.parse(path).getroot()
    element = root if root.tag == "testsuite" else root.find("testsuite")
    if element is None:
        suite.note = f"no testsuite element in {path.name}"
        return

    total = int(element.get("tests", 0))
    failed = int(element.get("failures", 0)) + int(element.get("errors", 0))
    skipped = int(element.get("skipped", 0))
    suite.failed = failed
    suite.skipped = skipped
    suite.passed = total - failed - skipped
    duration = element.get("time")
    suite.duration = float(duration) if duration else None

    suite.failures = [
        f"{case.get('classname', '')}::{case.get('name', '')}".lstrip(":")
        for case in element.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]


def _read_coverage_xml(path: Path, suite: Suite) -> None:
    """coverage.py --cov-report=xml: line-rate on the root element."""
    root = ElementTree.parse(path).getroot()
    line_rate = root.get("line-rate")
    if line_rate is not None:
        suite.coverage = float(line_rate) * 100


def _read_flutter_json(path: Path, suite: Suite) -> None:
    """flutter test --file-reporter=json: one JSON event per line."""
    results: dict[str, str] = {}
    names: dict[str, str] = {}
    hidden: set[str] = set()
    elapsed = 0

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        event = json.loads(line)
        kind = event.get("type")
        if kind == "testStart":
            test = event["test"]
            names[str(test["id"])] = test.get("name", "")
            # Flutter reports its own loading/compiling steps as hidden tests.
            if test.get("name", "").startswith(("loading ", "compiling ")):
                hidden.add(str(test["id"]))
        elif kind == "testDone":
            test_id = str(event["testID"])
            if event.get("hidden") or test_id in hidden:
                continue
            results[test_id] = "skipped" if event.get("skipped") else event.get("result", "error")
        elif kind == "done":
            elapsed = event.get("time", 0)

    suite.passed = sum(1 for r in results.values() if r == "success")
    suite.skipped = sum(1 for r in results.values() if r == "skipped")
    suite.failed = sum(1 for r in results.values() if r not in {"success", "skipped"})
    suite.duration = elapsed / 1000 if elapsed else None
    suite.failures = [
        names.get(test_id, test_id)
        for test_id, result in results.items()
        if result not in {"success", "skipped"}
    ]


def _read_lcov(path: Path, suite: Suite) -> None:
    """lcov.info: LF is lines found, LH lines hit, per file."""
    found = hit = 0
    for line in path.read_text().splitlines():
        if line.startswith("LF:"):
            found += int(line[3:])
        elif line.startswith("LH:"):
            hit += int(line[3:])
    if found:
        suite.coverage = hit / found * 100


def _collect(name: str, results: Path | None, coverage: Path | None, flutter: bool) -> Suite:
    suite = Suite(name=name)
    if results is None or not results.exists():
        suite.note = "no test report — the job did not get that far"
        return suite

    try:
        if flutter:
            _read_flutter_json(results, suite)
        else:
            _read_junit(results, suite)
    except (ElementTree.ParseError, json.JSONDecodeError, KeyError) as exc:
        suite.note = f"unreadable report ({type(exc).__name__})"
        return suite

    if coverage is not None and coverage.exists():
        if flutter:
            _read_lcov(coverage, suite)
        else:
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

    lines += [
        "",
        "<sub>Line coverage, as a rough signal — it is not a gate. The frontend figure "
        "covers only the libraries its tests import, so it reads higher than the app as "
        "a whole.</sub>",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-junit", type=Path)
    parser.add_argument("--backend-coverage", type=Path)
    parser.add_argument("--frontend-report", type=Path)
    parser.add_argument("--frontend-coverage", type=Path)
    args = parser.parse_args()

    suites = [
        _collect("Backend", args.backend_junit, args.backend_coverage, flutter=False),
        _collect("Frontend", args.frontend_report, args.frontend_coverage, flutter=True),
    ]
    print(render(suites))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
