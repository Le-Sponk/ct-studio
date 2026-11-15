"""Typed spies and isolated on-disk input for saved-choice tests."""

import json
from pathlib import Path
from typing import Literal

from ctstudio.core.tools import editors
from ctstudio.core.tools.saved_editors import EditorChoice, open_saved


def write_settings(path: Path, fields: dict[str, object]) -> bytes:
    path.write_text(json.dumps({"format": 1, **fields}), encoding="utf-8")
    return path.read_bytes()


def outcome(choice: EditorChoice, path: Path) -> editors.Launched | BaseException:
    try:
        return open_saved(
            choice, path.parent / "日本.brres", project=path.parent, settings_path=path
        )
    except BaseException as exc:
        return exc


def forbidden(*args: object, **kwargs: object) -> editors.Launched:
    raise AssertionError("unexpected owner call")


def choice(namespace: Literal["builtin", "custom"] = "custom") -> EditorChoice:
    return EditorChoice(namespace, "brawlcrate")
