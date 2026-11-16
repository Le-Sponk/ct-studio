"""Synthetic child receipts through real saved-choice owners, not editor loading."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from custom_wine_helpers import pe
from fakes.install import install_program

from ctstudio.core.tools.editors import Launched
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved

WARNING = (
    "RiiStudio cannot open paths with non-ASCII characters on Windows: it will start "
    "with an empty editor. Move or rename the file to an ASCII-only path."
)
CODE = r"""
import json, os, pathlib, sys, uuid
sys.stdout.reconfigure(encoding='utf-8')
helper = sys.argv[1:3] == ['winepath.exe', '-w']
folder = pathlib.Path(OUTPUT) / ('helpers' if helper else 'editors')
record = {'argv': sys.argv[1:], 'cwd': os.getcwd(), 'pid': os.getpid(),
          'prefix': os.environ.get('WINEPREFIX'), 'program': PROGRAM}
output = folder / (uuid.uuid4().hex + '.json')
pending = output.with_suffix('.pending')
pending.write_text(json.dumps(record), encoding='utf-8')
os.replace(pending, output)
if helper:
    print('Z:\\saved choice\\' + pathlib.Path(sys.argv[3]).name)
"""


def windows() -> Literal["windows"]:
    return "windows"


def linux() -> Literal["linux"]:
    return "linux"


def converted(path: Path) -> str:
    return "Z:\\saved choice\\" + path.name


def read_receipt(path: Path) -> dict[str, object]:
    deadline = time.monotonic() + 10
    while not path.is_file() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert path.is_file(), "child did not atomically publish a receipt"
    return cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))


def receipts(folder: Path, count: int) -> list[dict[str, object]]:
    deadline = time.monotonic() + 10
    paths = sorted(folder.glob("*.json"))
    while len(paths) < count and time.monotonic() < deadline:
        time.sleep(0.02)
        paths = sorted(folder.glob("*.json"))
    assert len(paths) == count, "wrong number of child receipts"
    assert not list(folder.glob("*.pending")), "receipt was not atomically published"
    return [read_receipt(path) for path in paths]


def snapshot(root: Path) -> dict[str, bytes | None]:
    """Include every input byte/directory, absent files and unexpected writes alike."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
        if not path.is_relative_to(root / "receipts")
    }


@dataclass
class Request:
    root: Path
    choice: EditorChoice
    document: Path
    project: Path
    executable: Path
    launcher: Path
    prefix: Path
    output: Path
    settings: Path
    fields: dict[str, object]
    tokens: list[str]
    revision: int
    wine: bool

    def save(self) -> None:
        self.settings.write_bytes(
            (json.dumps(self.fields, ensure_ascii=True, indent=2) + "\n").encode("utf-8")
        )

    def open(self) -> Launched | Exception:
        try:
            return open_saved(
                self.choice, self.document, project=self.project, settings_path=self.settings
            )
        except Exception as error:
            return error

    def arguments(self) -> list[str]:
        value = converted if self.wine else str
        if self.choice.namespace == "builtin":
            return [
                value(self.document),
                *(["/audio:none"] if self.choice.tool_id == "brawlcrate" else []),
            ]
        tokens = [
            value(self.document),
            "",
            value(self.project),
            value(self.document.parent),
            "{file}",
            f'--revision={self.revision} é 日本 "quoted" ;&|>$()',
            value(self.document),
        ]
        return tokens if self.revision == 0 else list(reversed(tokens))


def program(path: Path, output: Path, tag: str) -> Path:
    code = CODE.replace("OUTPUT", repr(str(output))).replace("PROGRAM", repr(tag))
    return install_program(path, code)


def request(root: Path, choice: EditorChoice, revision: int, *, wine: bool = False) -> Request:
    folder = root / f"request {revision} é 日本"
    folder.mkdir(parents=True)
    document = folder / "documents é 日本" / "synthetic é 日本.brres"
    document.parent.mkdir()
    document.write_bytes(b"synthetic only\x00\xff" + bytes([revision]))
    project = folder / "separate project 日本"
    project.mkdir()
    (project / "ctstudio.toml").write_bytes(b"synthetic project marker; not loaded\n")
    output = root / "receipts" / str(revision)
    for kind in ("editors", "helpers"):
        (output / kind).mkdir(parents=True)
    executables = make_executables(folder, output, revision, wine=wine)
    launcher = program(folder / "Wine 日本" / "wine", output, f"wine-{revision}")
    prefix = folder / "prefix é 日本"
    prefix.mkdir()
    (prefix / "system.reg").write_bytes(b"#arch=win64\n; unchanged registry\n")
    executable = executables[choice.namespace]
    tokens = [
        "{file:}",
        "",
        "{project:}",
        "{dir:}",
        "{{file}}",
        f'--revision={revision} é 日本 "quoted" ;&|>$()',
        "{file}",
    ]
    if revision:
        tokens.reverse()
    settings = root / "machine settings 日本.json"
    result = Request(
        root,
        choice,
        document,
        project,
        executable,
        launcher,
        prefix,
        output,
        settings,
        {},
        tokens,
        revision,
        wine,
    )
    result.fields = settings_fields(result, executables)
    result.save()
    return result


def settings_fields(item: Request, executables: dict[str, Path]) -> dict[str, object]:
    choice, wine = item.choice, item.wine
    launcher, prefix = item.launcher, item.prefix
    folder, revision, tokens = item.document.parent.parent, item.revision, item.tokens
    return {
        "format": 1,
        "tools": {
            choice.tool_id: str(executables["builtin"]),
            "wine": str(launcher) if wine else "unused\0Wine\ud800",
        },
        "wine_prefixes": {
            choice.tool_id: {
                "prefix": str(prefix) if wine else str(folder / "unused absent prefix")
            }
        },
        "custom_tools": {
            choice.tool_id: {
                "name": "Custom 日本",
                "exe": str(executables["custom"]),
                "args_template": tokens,
            }
        },
        "editor_preferences": {
            ".brres": "riistudio" if choice.tool_id == "brawlcrate" else "brawlcrate"
        },
        "future": {"unchanged": ["é 日本", revision]},
    }


def make_executables(folder: Path, output: Path, revision: int, *, wine: bool) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for namespace in ("builtin", "custom"):
        tag = f"{namespace}-{revision}"
        if wine:
            path = pe(folder / f"{tag} synthetic editor.ExE")
            path.write_bytes(path.read_bytes() + tag.encode("ascii"))
        else:
            path = program(folder / tag / "éditeur 日本", output, tag)
        paths[namespace] = path.resolve()
    return paths


def exercise(item: Request) -> tuple[int, int]:
    before = snapshot(item.root)
    result = item.open()
    assert isinstance(result, Launched), result
    warnings = (
        (WARNING,) if item.choice == EditorChoice("builtin", "riistudio") and not item.wine else ()
    )
    assert result == Launched(item.choice.tool_id, result.pid, item.document.resolve(), warnings)
    assert result.pid > 0 and result.pid != os.getpid()
    writer = check_child(item)
    assert snapshot(item.root) == before
    return result.pid, writer


def check_child(item: Request) -> int:
    data = receipts(item.output / "editors", 1)[0]
    expected = item.arguments()
    if item.wine:
        expected.insert(0, str(item.executable))
    assert data["argv"] == expected
    assert Path(str(data["cwd"])).resolve() == item.document.parent.resolve()
    assert data["prefix"] == (
        str(item.prefix.resolve()) if item.wine else "inherited native sentinel"
    )
    expected_program = (
        f"wine-{item.revision}" if item.wine else f"{item.choice.namespace}-{item.revision}"
    )
    assert data["program"] == expected_program
    writer = data["pid"]
    assert isinstance(writer, int) and writer > 0 and writer != os.getpid()
    return writer


def check_helpers(item: Request) -> None:
    paths = [item.document.resolve()]
    if item.choice.namespace == "custom":
        paths.extend([item.project.resolve(), item.document.parent.resolve()])
    rows = receipts(item.output / "helpers", len(paths) if item.wine else 0)
    assert (
        sorted(cast("list[str]", row["argv"]) for row in rows)
        == sorted(["winepath.exe", "-w", str(path)] for path in paths)
        if item.wine
        else rows == []
    )
    for row in rows:
        argv = cast("list[str]", row["argv"])
        assert Path(str(row["cwd"])).resolve() == Path(argv[2]).parent
        assert row["prefix"] == str(item.prefix.resolve())
        assert row["program"] == f"wine-{item.revision}"
        assert isinstance(row["pid"], int) and row["pid"] > 0
