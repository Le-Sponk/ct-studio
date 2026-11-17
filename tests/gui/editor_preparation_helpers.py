"""Synthetic read-only preparation fixtures; no real editor may run."""

import struct
from pathlib import Path
from typing import NoReturn

import pytest

from ctstudio.core.project import settings
from ctstudio.core.project.manifest import Manifest, ProjectInfo
from ctstudio.core.project.project import Project
from ctstudio.core.tools import custom_editors, discovery, editors, process, wine
from ctstudio.core.tools.spec import ToolSpec


def forbidden(*_args: object, **_kwargs: object) -> NoReturn:
    raise AssertionError("Preparation must not start any process or write user state")


@pytest.fixture(autouse=True)
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (editors, custom_editors, wine, process):
        monkeypatch.setattr(module, "launch_detached", forbidden)
    monkeypatch.setattr(process, "run", forbidden)
    monkeypatch.setattr(wine, "run", forbidden)
    monkeypatch.setattr(settings, "save", forbidden)
    monkeypatch.setattr(Project, "save", forbidden)


def assignment_error(target: object, field: str, value: object) -> BaseException | None:
    try:
        setattr(target, field, value)
    except BaseException as error:
        return error
    return None


def project_at(root: Path) -> Project:
    root.mkdir()
    (root / "ctstudio.toml").write_bytes(b"synthetic manifest; preserve exactly")
    return Project(root, Manifest(project=ProjectInfo(name="Synthetic café 空")), None)


class Finder:
    def __init__(self, root: Path) -> None:
        self.environment = discovery.DiscoveryEnvironment("windows", root, root, {}, None)
        self.calls: list[tuple[str, Path | None, bool]] = []

    def __call__(
        self, spec: ToolSpec, *, configured: Path | None = None, include_dev: bool = False
    ) -> discovery.ToolLocation | None:
        self.calls.append((spec.id, configured, include_dev))
        return discovery.discover(
            spec,
            configured=configured,
            include_dev=include_dev,
            environment=self.environment,
            dev_root=self.environment.root / "empty-dev",
        )


def file_at(root: Path, name: str) -> Path:
    path = root / name
    path.write_bytes(b"synthetic only")
    path.chmod(0o755)  # Linux discovery requires executable permission, even for stand-ins.
    return path


def pe_at(root: Path, name: str) -> Path:
    path = root / name
    data = bytearray(256)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<H", data, 132, 0x8664)
    struct.pack_into("<H", data, 152, 0x20B)
    path.write_bytes(data)
    path.chmod(0o755)  # PE stand-ins are inspected, never executed; match Linux discovery.
    return path


def linux() -> str:
    return "linux"


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
