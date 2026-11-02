"""P3-T04: every reachable status for every track part, with plain reasons.

A small ``World`` builds a project folder: it writes the files the manifest names, "builds"
parts the way the build runner will (writes their outputs under ``.ctstudio/stage/`` and
records them in state.json), then changes things. Each table row is one scenario.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from test_magic import brres, kcl, kmp, png, postfx

from ctstudio.core.components.registry import COMPONENTS
from ctstudio.core.components.state import (
    GENERATED_DIR,
    ProjectState,
    load_state,
    record,
    save_state,
)
from ctstudio.core.components.status import ComponentStatus, State, evaluate, settings_key
from ctstudio.core.project import manifest as m
from ctstudio.core.tools.registry import TOOL_BY_ID

pytestmark = pytest.mark.timeout(30)
ALL_TOOLS = frozenset(TOOL_BY_ID)
BLEND = "art/track.blend"
OUTPUTS = {
    "course_model": {"course_model.brres": b"model"},
    "kcl": {"course.kcl": b"collision"},
    "minimap": {"map_model.brres": b"map"},
    "skybox": {"vrcorn_model.brres": b"sky"},
    "posteffect": {"posteffect/posteffect.blight": b"light", "posteffect/posteffect.bfg": b"fog"},
}
MANUAL = {
    "course_model": ("files/course_model.brres", brres()),
    "kcl": ("files/course.kcl", kcl()),
    "minimap": ("files/map_model.brres", brres()),
    "skybox": ("files/vrcorn_model.brres", brres()),
    "kmp": ("files/course.kmp", kmp()),
}
NOT_FOUND = "which was not found (see the Tools page)"


@dataclass
class World:
    root: Path
    manifest: m.Manifest = field(default_factory=lambda: m.Manifest(m.ProjectInfo(name="T")))
    tools: frozenset[str] = ALL_TOOLS

    def write(self, rel: str, data: bytes) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def touch(self, rel: str) -> None:
        st = (self.root / rel).stat()
        os.utime(self.root / rel, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))

    def edit(self, rel: str, data: bytes = b"edited!") -> None:
        self.write(rel, data)
        self.touch(rel)

    def delete(self, rel: str) -> None:
        (self.root / rel).unlink()

    def mkdir(self, rel: str) -> None:
        (self.root / rel).mkdir(parents=True)

    def change(self, **changes: object) -> None:
        self.manifest = dataclasses.replace(self.manifest, **changes)

    def project(self, **changes: object) -> None:
        info = dataclasses.replace(self.manifest.project, **changes)
        self.manifest = dataclasses.replace(self.manifest, project=info)

    def part(self, component: str, **changes: object) -> None:
        table = dataclasses.replace(getattr(self.manifest.components, component), **changes)
        parts = dataclasses.replace(self.manifest.components, **{component: table})
        self.manifest = dataclasses.replace(self.manifest, components=parts)

    def blend(self) -> None:
        self.project(blend=BLEND)
        if not (self.root / BLEND).exists():
            self.write(BLEND, b"BLENDER-v300REND")

    def manual(self, component: str, data: bytes | None = None, *, exists: bool = True) -> None:
        rel, good = MANUAL[component]
        self.part(component, mode="manual", file=rel)
        if exists:
            self.write(rel, good if data is None else data)

    def build(self, component: str) -> None:
        """What the build runner will do: write the outputs, then record them."""
        if component != "posteffect":
            self.blend()
        if component == "minimap" and not (self.root / GENERATED_DIR / "course.kcl").exists():
            self.write(f"{GENERATED_DIR}/course.kcl", b"collision")  # its input
        outputs: list[Path] = []
        for name, data in OUTPUTS[component].items():
            self.write(f"{GENERATED_DIR}/{name}", data)
            outputs.append(self.root / GENERATED_DIR / name)
        source = {"posteffect": [], "minimap": [f"{GENERATED_DIR}/course.kcl"]}
        inputs = [self.root / rel for rel in source.get(component, [BLEND])]
        made = record(self.root, settings_key(self.manifest, component), outputs, inputs)
        save_state(self.root, ProjectState({**load_state(self.root).components, component: made}))

    def status(self, component: str) -> ComponentStatus:
        return evaluate(self, self.tools)[component]


type Setup = Callable[[World], object]


def out(component: str) -> str:
    return f"{GENERATED_DIR}/{next(iter(OUTPUTS[component]))}"


def steps(*setups: Setup) -> Setup:
    def run(w: World) -> None:
        for setup in setups:
            setup(w)

    return run


def build(component: str) -> Setup:
    return lambda w: w.build(component)


def tools_without(*tool_ids: str) -> Setup:
    return lambda w: setattr(w, "tools", ALL_TOOLS - set(tool_ids))


@dataclass(frozen=True)
class Row:
    component: str
    name: str
    setup: Setup
    state: State
    reasons: tuple[str, ...]


def row(component: str, name: str, setup: Setup, state: State, *reasons: str) -> Row:
    return Row(component, name, setup, state, reasons)


def wrong(shown: str, expected: str, found: str) -> str:
    return f"{shown} is the wrong type: expected {expected}, found {found}"


def needs(tool: str) -> str:
    return f"needs {TOOL_BY_ID[tool].name}, {NOT_FOUND}"


def _generated_rows(c: str) -> list[Row]:
    name = next(iter(OUTPUTS[c]))
    source = f"{GENERATED_DIR}/course.kcl" if c == "minimap" else BLEND
    tool = "wszst" if c == "minimap" else "blender"
    kind = "collision file (KCL)" if c == "kcl" else "BRRES model"
    rel = MANUAL[c][0]
    built = build(c)
    gone = f"{Path(source).name}, used to make {name}, is gone"
    return [
        row(c, "never built", World.blend, State.MISSING, f"{name} has not been made yet"),
        row(c, "built", built, State.READY),
        row(c, "output touched only", steps(built, lambda w: w.touch(out(c))), State.READY),
        row(c, "output deleted", steps(built, lambda w: w.delete(out(c))), State.MISSING,
            f"{name} is gone; it will be made again"),
        row(c, "output edited", steps(built, lambda w: w.edit(out(c))), State.EDITED_EXTERNALLY,
            f"{name} was changed outside CT Studio"),
        row(c, "source edited", steps(built, lambda w: w.edit(source)), State.STALE,
            f"{Path(source).name} changed since {name} was made"),
        row(c, "source gone", steps(built, lambda w: w.delete(source)), State.STALE, gone)
        if c == "minimap"
        else row(c, "source gone", steps(built, lambda w: w.delete(source)), State.ERROR,
                 gone, f"{BLEND} was not found"),
        row(c, "tool missing", steps(World.blend, tools_without(tool)), State.ERROR,
            f"{name} has not been made yet", needs(tool)),
        row(c, "manual", lambda w: w.manual(c), State.MANUAL, f"using {rel}"),
        row(c, "manual, none chosen", lambda w: w.part(c, mode="manual"), State.MISSING,
            "no file chosen"),
        row(c, "manual, not found", lambda w: w.manual(c, exists=False), State.MISSING,
            f"{rel} was not found"),
        row(c, "manual, wrong type", lambda w: w.manual(c, png()), State.ERROR,
            wrong(rel, kind, "PNG image")),
    ]  # fmt: skip


def _posteffect_rows() -> list[Row]:
    c = "posteffect"
    fog = f"{GENERATED_DIR}/posteffect/posteffect.bfg"
    added = f"{GENERATED_DIR}/posteffect/x.bdof"
    folder = "files/posteffect"
    light = f"{folder}/posteffect.blight"
    built = build(c)

    def manual(*files: tuple[str, bytes]) -> Setup:
        def setup(w: World) -> None:
            w.part(c, mode="manual", file=folder)
            for rel, data in files:
                w.write(rel, data)

        return setup

    good = manual((light, postfx(b"LGHT")), (f"{folder}/posteffect.bfg", b"fog"))
    return [
        row(c, "never made", lambda w: None, State.MISSING, "posteffect/ has not been made yet"),
        row(c, "made", built, State.READY),
        row(c, "a file edited", steps(built, lambda w: w.edit(fog)), State.EDITED_EXTERNALLY,
            "posteffect/posteffect.bfg was changed outside CT Studio"),
        row(c, "a file added", steps(built, lambda w: w.write(added, b"x")),
            State.EDITED_EXTERNALLY, "posteffect/x.bdof was added outside CT Studio"),
        row(c, "a folder added", steps(built, lambda w: w.mkdir(f"{GENERATED_DIR}/posteffect/sub")),
            State.READY),
        row(c, "a file deleted", steps(built, lambda w: w.delete(fog)), State.MISSING,
            "posteffect/posteffect.bfg is gone; it will be made again"),
        row(c, "tool missing", tools_without("wszst"), State.ERROR,
            "posteffect/ has not been made yet", needs("wszst")),
        row(c, "other track", steps(built, lambda w: w.part(c, template_track="castle_course")),
            State.STALE, "settings changed since posteffect/ was made"),
        row(c, "manual folder", good, State.MANUAL, f"using {folder}"),
        row(c, "manual, none chosen", lambda w: w.part(c, mode="manual"), State.MISSING,
            "no file chosen"),
        row(c, "manual folder missing", manual(), State.MISSING, f"{folder} was not found"),
        row(c, "manual folder empty", steps(manual(), lambda w: w.mkdir(folder)), State.ERROR,
            f"{folder} is empty"),
        row(c, "manual, a file is wrong", manual((light, png())), State.ERROR,
            wrong(light, "lighting settings (BLIGHT)", "PNG image")),
        row(c, "manual, a file not a folder", manual((folder, b"x")), State.ERROR,
            wrong(folder, "a folder", "a file")),
    ]  # fmt: skip


def _other_rows() -> list[Row]:
    cm, model = "course_model", "course_model.brres"
    new_blend = steps(build(cm), lambda w: w.edit(BLEND, b"BLENDER newer"))
    road = m.BlenderSettings(m.BlenderCollections(course="Road"))
    no_add = m.BuildSettings(auto_add=False)
    folder = steps(lambda w: w.part(cm, mode="manual", file="files/model"),
                   lambda w: w.mkdir("files/model"))  # fmt: skip
    newer = f"track.blend changed since {model} was made"
    return [
        row(cm, "no .blend chosen", lambda w: None, State.ERROR,
            f"{model} has not been made yet", "no .blend file chosen for this project"),
        row(cm, "collections changed", steps(build(cm), lambda w: w.change(blender=road)),
            State.STALE, f"settings changed since {model} was made"),
        row(cm, "edited and source changed", steps(new_blend, lambda w: w.edit(out(cm))),
            State.EDITED_EXTERNALLY, f"{model} was changed outside CT Studio", newer),
        row(cm, "stale and no tools", steps(new_blend, lambda w: setattr(w, "tools", frozenset())),
            State.ERROR, newer, *(needs(t) for t in ("blender", "rszst", "abmatt", "wimgt"))),
        row(cm, "edited and no tools",
            steps(build(cm), lambda w: w.edit(out(cm)), lambda w: setattr(w, "tools", frozenset())),
            State.EDITED_EXTERNALLY, f"{model} was changed outside CT Studio"),
        row(cm, "manual path is a folder", folder, State.ERROR,
            wrong("files/model", "BRRES model", "a folder")),
        row(cm, "manual, unrecognised", lambda w: w.manual(cm, b"just text\n\x00"), State.ERROR,
            wrong("files/course_model.brres", "BRRES model", "an unrecognised file")),
        row("kcl", "settings changed", steps(build("kcl"), lambda w: w.part("kcl", unbean="none")),
            State.STALE, "settings changed since course.kcl was made"),
        row("skybox", "template, never made", lambda w: w.part("skybox", mode="template"),
            State.MISSING, "vrcorn_model.brres has not been made yet"),
        row("kmp", "manual", lambda w: w.manual("kmp"), State.MANUAL, "using files/course.kmp"),
        row("kmp", "none chosen", lambda w: None, State.MISSING, "no file chosen"),
        row("kmp", "not found", lambda w: w.manual("kmp", exists=False), State.MISSING,
            "files/course.kmp was not found"),
        row("kmp", "wrong type", lambda w: w.manual("kmp", kcl()), State.ERROR,
            wrong("files/course.kmp", "course data file (KMP)", "collision file (KCL)")),
        row("objects", "auto-add on", lambda w: None, State.READY,
            "added automatically while the track is assembled"),
        row("objects", "auto-add off", lambda w: w.change(build=no_add), State.WARNING,
            "auto-add is off: objects the course data places must already be in the track"),
        row("objects", "no Wiimm", tools_without("wszst"), State.WARNING,
            f"needs {TOOL_BY_ID['wszst'].name} to add objects automatically, {NOT_FOUND}"),
        row("track_info", "complete", lambda w: w.project(author="Sponk"), State.READY,
            "replaces beginner_course"),
        row("track_info", "no author", lambda w: None, State.WARNING, "no author set"),
        row("track_info", "blank author", lambda w: w.project(author="  "), State.WARNING,
            "no author set"),
    ]  # fmt: skip


ROWS: list[Row] = [
    *(r for c in ("course_model", "kcl", "minimap", "skybox") for r in _generated_rows(c)),
    *_posteffect_rows(),
    *_other_rows(),
]


@pytest.mark.parametrize(
    ("component", "setup", "state", "reasons"),
    [
        pytest.param(r.component, r.setup, r.state, r.reasons, id=f"{r.component}: {r.name}")
        for r in ROWS
    ],
)
def test_status(
    tmp_path: Path, component: str, setup: Setup, state: State, reasons: tuple[str, ...]
) -> None:
    w = World(tmp_path / "Piste é")
    w.root.mkdir()
    setup(w)
    got = w.status(component)
    assert (got.state, got.reasons) == (state, reasons)


def test_the_table_reaches_every_status_and_every_part() -> None:
    assert {r.state for r in ROWS} == set(State)
    assert {r.component for r in ROWS} == {c.id for c in COMPONENTS}
    names = [(r.component, r.name) for r in ROWS]
    assert len(set(names)) == len(names)
