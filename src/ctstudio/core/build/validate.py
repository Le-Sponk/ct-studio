"""The validate step: check ``build/<slot>.szs`` and write ``.ctstudio/issues.json`` (P4-T06).

``wszst analyze --json`` gives an empty ``sha1_<part>`` for each required part the archive
lacks, KMP or not (measured on 2.42a, TOOLS.md); each becomes one error naming the part.
``wszst check`` adds its own findings (from P2-T05a's parser); its "Missing file" lines for
those same parts appear only when there is a KMP, so they are dropped as duplicates. Test
builds never fail on findings. A strict build (release by default) fails when there is any
error, after writing every finding to issues.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from ctstudio.core import fsutil
from ctstudio.core.build.node import BuildContext, Node, NodeResult, Profile, StepFailed
from ctstudio.core.components.registry import COMPONENT_BY_ID
from ctstudio.core.project.manifest import Manifest
from ctstudio.core.tools.wiimm import analyze, check
from ctstudio.core.validation.issues import Issue, issue_to_json

ISSUES_FILE = ".ctstudio/issues.json"
FORMAT = 1
BUILD_DIR = "build"
# analyze key -> the part it fingerprints, in the order the dashboard lists parts
_PARTS = (
    ("sha1_course", "course_model"),
    ("sha1_kcl", "kcl"),
    ("sha1_minimap", "minimap"),
    ("sha1_vrcorn", "skybox"),
    ("sha1_kmp", "kmp"),
)


def validate_step(
    root: Path, manifest: Manifest, profile: Profile, strict: bool | None = None
) -> Node:
    """``strict``: fail on errors; None means "the profile decides" (release is strict)."""
    szs = root / BUILD_DIR / f"{manifest.project.slot}.szs"
    report = root / ISSUES_FILE
    strict = profile == "release" if strict is None else strict

    def run(ctx: BuildContext) -> NodeResult:
        exe = ctx.tools.get("wszst")
        path = exe.path if exe else None
        found = analyze(szs, executable=path, cancel=ctx.cancel)
        missing = _missing_parts(found, szs)
        names = {spec.outputs[0] for spec in (COMPONENT_BY_ID[i.component] for i in missing)}
        findings = [
            i
            for i in check(szs, executable=path, cancel=ctx.cancel)
            if not (i.code == "WSZST_MISSING_FILE" and i.file and i.file.as_posix() in names)
        ]
        issues = (*missing, *findings)
        _write(ctx.root, report, szs, issues)
        errors = sum(1 for i in issues if i.severity == "error")
        ctx.log(f"{szs.name}: {errors} errors, {len(issues) - errors} other findings")
        if strict and errors:
            raise StepFailed(_stop(szs, errors), also=issues)
        return NodeResult(issues)

    return Node("validate", (szs,), (report,), {"strict": strict}, ("wszst",), frozenset(), 1, run)


def _missing_parts(found: dict[str, object], szs: Path) -> list[Issue]:
    issues: list[Issue] = []
    for key, part in _PARTS:
        if found.get(key) != "":
            continue
        spec = COMPONENT_BY_ID[part]
        issues.append(
            Issue(
                "error",
                part,
                "VALIDATE_PART_MISSING",
                f"{spec.name} ({spec.outputs[0]}) is not in {szs.name}, so the game cannot load"
                " the track.",
                "Choose its file on the dashboard, then build again.",
                "wszst analyze",
                szs,
                spec.wiki,
            )
        )
    return issues


def _stop(szs: Path, errors: int) -> Issue:
    return Issue(
        "error",
        "validate",
        "VALIDATE_STRICT",
        f"{szs.name} has {errors} error{'s' if errors > 1 else ''}, so this release build"
        " stops here.",
        "Fix the errors listed, or make a test build to try the track anyway.",
        "validate",
        szs,
    )


def _write(root: Path, report: Path, szs: Path, issues: tuple[Issue, ...]) -> None:
    data = {
        "format": FORMAT,
        "track": szs.relative_to(root).as_posix(),
        "issues": [issue_to_json(issue, root) for issue in issues],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    fsutil.atomic_write_text(report, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
