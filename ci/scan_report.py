#!/usr/bin/env python3
"""Render one markdown summary of the image scans.

Reads the JSON report Trivy wrote for each image — already filtered by the scan
to HIGH/CRITICAL findings that have a fixed version — and writes a table to
stdout, with the findings per image folded underneath. A missing report is
shown as such: it means the scan could not run, not that the image is clean.

    python3 ci/scan_report.py --image backend=trivy-backend.json ... > scan.md
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

# Per image, in the pull request comment: a base image that falls behind can
# carry dozens, and a comment has a size limit. The job summary renders them all.
MAX_ROWS = 30


@dataclass
class Finding:
    package: str
    advisory: str
    url: str | None
    severity: str
    installed: str
    fixed: str
    where: str


@dataclass
class Image:
    name: str
    findings: list[Finding] = field(default_factory=list)
    note: str | None = None

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def status(self) -> str:
        if self.note:
            return "❓"
        return "✅" if not self.findings else "⚠️"


def _read(name: str, path: Path) -> Image:
    image = Image(name)
    if not path.is_file():
        image.note = "no report — the scan did not complete, see the job log"
        return image

    report = json.loads(path.read_text())
    for result in report.get("Results") or []:
        # OS packages are reported against the image itself ("…:ci-abc1234
        # (debian 13.7)"); everything else against a file inside it.
        where = "OS packages" if result.get("Class") == "os-pkgs" else result.get("Target", "")
        for vuln in result.get("Vulnerabilities") or []:
            image.findings.append(
                Finding(
                    package=vuln.get("PkgName", ""),
                    advisory=vuln.get("VulnerabilityID", ""),
                    url=vuln.get("PrimaryURL"),
                    severity=vuln.get("Severity", ""),
                    installed=vuln.get("InstalledVersion", ""),
                    fixed=vuln.get("FixedVersion", ""),
                    where=where,
                )
            )
    image.findings.sort(key=lambda f: (f.severity != "CRITICAL", f.where, f.package, f.advisory))
    return image


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(images: list[Image], max_rows: int = MAX_ROWS) -> str:
    lines = [
        "### Image scan",
        "",
        "| Image | | Critical | High |",
        "|---|---|---:|---:|",
    ]
    for image in images:
        if image.note:
            lines.append(f"| {image.name} | {image.status} | – | – |")
        else:
            critical, high = image.count("CRITICAL"), image.count("HIGH")
            lines.append(f"| {image.name} | {image.status} | {critical} | {high} |")

    for image in images:
        if image.note:
            lines += ["", f"> **{image.name}:** {image.note}"]
        if not image.findings:
            continue
        lines += [
            "",
            f"<details><summary><b>{image.name}</b> — {len(image.findings)} findings</summary>",
            "",
            "| Package | Advisory | Severity | Installed | Fixed in | Where |",
            "|---|---|---|---|---|---|",
        ]
        shown = image.findings[:max_rows] if max_rows else image.findings
        for f in shown:
            advisory = f"[{f.advisory}]({f.url})" if f.url else f.advisory
            lines.append(
                f"| {_cell(f.package)} | {advisory} | {f.severity} | {_cell(f.installed)} "
                f"| {_cell(f.fixed)} | {_cell(f.where)} |"
            )
        if len(shown) < len(image.findings):
            hidden = len(image.findings) - len(shown)
            lines.append(f"| …and {hidden} more, see the job summary | | | | | |")
        lines += ["", "</details>"]

    footer = (
        "HIGH and CRITICAL findings with a fixed version available. A report, not a gate:"
        " fixes arrive through Renovate. Accepted findings are listed in .trivyignore.yaml."
    )
    lines += ["", f"<sub>{footer}</sub>"]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="NAME=REPORT",
        help="image name and the path of its Trivy JSON report; repeatable",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS,
        help="findings listed per image; 0 lists all",
    )
    args = parser.parse_args()

    images = []
    for spec in args.image:
        name, _, report = spec.partition("=")
        images.append(_read(name, Path(report)))
    print(render(images, args.max_rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
