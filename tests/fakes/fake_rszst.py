"""Measured subset of RiiStudio CLI 5.11.5 (P2-T04c).

Only the recorded four-mesh fixture shape is converted; no real BRRES is decoded. The
opaque stand-in marker identifies archives this process created. All other valid inputs
are refused with exit 121 rather than passing with invented output.
"""

from __future__ import annotations

import os
from pathlib import Path

import rszst_cli as cli
from fake_runtime import Outcome, Unmodelled, finish, recordings

VERSION = cli.VERSION
MARK = b"\nCT-STUDIO-FAKE-RSZST\n"
FOLDER = Path(__file__).resolve().parent / "recordings" / "rszst" / VERSION
OPS: dict[str, dict[str, object]] = {
    str(item["case"]): item for item in recordings("rszst", VERSION, "ops")
}
MATERIALS = ("fence", "grass", "road", "water")
TEXTURES = ("road.png", "grass.png", "fence.png", "water.png")
FAKE_BRRES = b"bres" + MARK
FAKE_JSON = b'{"chrs":[]' + MARK
FAKE_BIN = b"RBUF" + MARK


def template(name: str) -> str:
    first, separator, body = str(OPS[name]["stdout"]).partition("\n")
    if not separator or not first.startswith("RiiStudio CLI Alpha "):
        raise Unmodelled(f"{name}: operation recording has no RiiStudio banner")
    return body


def reply(code: int, text: str, error: str = "") -> Outcome:
    return cli.outcome(code, cli.BANNER + "\n" + text, error)


def _shape(path: Path) -> None:
    """Only the DAE and four PNGs actually run through the real converter are modelled."""
    inputs = FOLDER / "inputs"
    if path.read_bytes() != (inputs / "course.dae").read_bytes():
        raise Unmodelled("DAE differs from the recorded four-mesh course")
    for name in TEXTURES:
        texture = path.parent / name  # rszst also looks in textures/ (P2-T05e recording)
        if not texture.is_file():
            texture = path.parent / "textures" / name
        if not texture.is_file() or texture.read_bytes() != (inputs / name).read_bytes():
            raise Unmodelled(f"{name}: missing or differs from the recorded texture")


def archive(path: Path) -> None:
    if not path.is_file():
        raise Unmodelled(f"{path}: fake archive missing")
    if path.read_bytes() != FAKE_BRRES:
        raise Unmodelled(f"{path}: real or unrecognised BRRES")


def _paths(parsed: cli.Parsed, suffix: str) -> tuple[str, str]:
    source = parsed.positionals[0]
    destination = (
        parsed.positionals[1]
        if len(parsed.positionals) > 1
        else str(Path(source).with_suffix(suffix))
    )
    return source, destination


def _known_options(parsed: cli.Parsed, names: set[str]) -> None:
    unknown = parsed.options.keys() - names
    if unknown:
        raise Unmodelled(f"{parsed.command.name}: options {sorted(unknown)}")


def _import_mipmap_options(parsed: cli.Parsed) -> None:
    if "min-mip" in parsed.options and (
        parsed.options.get("mipmaps"),
        parsed.options["min-mip"],
    ) != (True, "64"):
        raise Unmodelled("min-mip value not recorded")
    if "mipmaps" in parsed.options and "min-mip" not in parsed.options:
        raise Unmodelled("mipmaps without min-mip not recorded")


def _import_options(parsed: cli.Parsed) -> tuple[str, str, str, str | None]:
    """Return source, destination, model and preset after checking measured options."""
    _known_options(parsed, {"model-name", "mipmaps", "min-mip", "preset-path"})
    _import_mipmap_options(parsed)
    model = parsed.options.get("model-name", "course")
    if model not in {"course", "vrcorn"}:
        raise Unmodelled("model name not recorded")
    keys = frozenset(parsed.options)
    measured = {
        frozenset(),
        frozenset({"model-name"}),
        frozenset({"mipmaps", "min-mip"}),
        frozenset({"preset-path"}),
    }
    if model == "course":  # the adapter always names its model (P2-T05e recordings)
        measured |= {
            frozenset({"model-name", *k}) for k in (("mipmaps", "min-mip"), ("preset-path",))
        }
    if keys not in measured:
        raise Unmodelled(f"option combination not recorded: {sorted(keys)}")
    source, destination = _paths(parsed, ".brres")
    if Path(source).suffix.lower() != ".dae" or Path(destination).suffix.lower() != ".brres":
        raise Unmodelled("only DAE to BRRES was recorded")
    preset = parsed.options.get("preset-path")
    if preset is not None and not isinstance(preset, str):
        raise Unmodelled("preset-path requires a path")
    return source, destination, model, preset


def _ansi_mangled(text: str) -> bool:
    """Windows reads argv through the ANSI code page: é paths are mangled (measured).

    Absolute paths and non-ASCII relative names were recorded with é only, on Windows.
    """
    if text.isascii() and not Path(text).is_absolute():
        return False
    if os.name != "nt" or any(not (c.isascii() or c == "é") for c in text):
        raise Unmodelled("path not recorded on this OS")
    if "é" not in text:
        raise Unmodelled("absolute ASCII path not recorded")
    return True


def _shown(text: str) -> str:
    return "".join(c if c.isascii() else "\ufffd" for c in text)


def _import_failure(source: str, error: str) -> Outcome | None:
    path = Path(source)
    ansi_path = _ansi_mangled(source)
    if ansi_path or not path.exists():
        shown = _shown(source) if ansi_path else source
        msg = "Failed to parse args: FileNotExist\n"
        return reply(-1, template("import missing"), f"Error: File {shown} does not exist.\n{msg}")
    if path.read_bytes().startswith(b"not a track file\n"):
        return reply(
            -1, template("import junk"), error + "Failed to parse: Assimp failed to read scene\n"
        )
    return None


def _import_presets(preset: str | None) -> tuple[str, str]:
    if preset is None:
        return template("import"), ""
    if _ansi_mangled(preset) or not Path(preset).is_dir():
        return template(
            "import"
        ), f"Warning: Preset path {_shown(preset)} does not exist not valid.\n"
    files = sorted(p.name for p in Path(preset).glob("*.rspreset"))
    if files != [f"{m}.rspreset" for m in MATERIALS] or any(
        (Path(preset) / name).read_bytes() != FAKE_BRRES for name in files
    ):
        raise Unmodelled("unrecognised material presets")
    text = template("import presets").replace(
        "Info: Reading presets from presets", f"Info: Reading presets from {preset}"
    )
    return text, ""


def _import(parsed: cli.Parsed) -> Outcome:
    source, destination, model, preset = _import_options(parsed)
    error = ""
    if not Path(destination).exists():
        error = f"Warning: File {destination} will be overwritten by this operation.\n"
    failed = _import_failure(source, error)
    if failed is not None:
        return failed
    _shape(Path(source))
    text, preset_warning = _import_presets(preset)
    text = text.replace("Model name: course", f"Model name: {model}")
    writes = [(Path(destination), FAKE_BRRES)] if Path(destination).parent.is_dir() else []
    result = reply(0, text, error + preset_warning)
    result.writes = writes
    return result


def _to_json(parsed: cli.Parsed) -> Outcome:
    _known_options(parsed, set())
    source, destination = _paths(parsed, ".json")
    if Path(source).suffix.lower() != ".brres" or Path(destination).suffix.lower() != ".json":
        raise Unmodelled("only BRRES to JSON was recorded")
    path = Path(source)
    if not path.exists():
        return reply(-1, "FolderNotExist\n", f"Error: File {source} does not exist.\n")
    archive(path)
    error = (
        f"Warning: File {destination} will be overwritten by this operation.\n"
        if Path(destination).exists()
        else ""
    )
    result = reply(0, template("to json"), error)
    if Path(destination).parent.is_dir():
        result.writes = [
            (Path(destination), FAKE_JSON),
            (Path(destination).with_suffix(".bin"), FAKE_BIN),
        ]
    return result


def _from_json(parsed: cli.Parsed) -> Outcome:
    _known_options(parsed, set())
    source, destination = _paths(parsed, ".brres")
    if Path(source).suffix.lower() != ".json" or Path(destination).suffix.lower() != ".brres":
        raise Unmodelled("only JSON to BRRES was recorded")
    path = Path(source)
    if not path.exists():
        return reply(-1, f'Failed to read file at "{source}"\n')
    data = path.read_bytes()
    if data != FAKE_JSON and data != b"not a track file\n" * 4:
        raise Unmodelled("unrecognised JSON")
    bin_path = path.with_suffix(".bin")
    if not bin_path.exists():
        return reply(-1, f'Failed to read file at "{bin_path}"\n')
    if bin_path.read_bytes() != FAKE_BIN:
        raise Unmodelled("unrecognised binary JSON sidecar")
    if data != FAKE_JSON:
        raise Unmodelled("unrecognised JSON")
    result = reply(0, "")
    if Path(destination).parent.is_dir():
        result.writes = [(Path(destination), FAKE_BRRES)]
    return result


def _dump(parsed: cli.Parsed) -> Outcome:
    _known_options(parsed, set())
    source, destination = _paths(parsed, ".presets")
    if Path(source).suffix.lower() != ".brres":
        raise Unmodelled("only BRRES presets were recorded")
    if not Path(source).exists():
        return reply(-1, "", f"Error: File {source} does not exist.\nFileNotExist\n")
    archive(Path(source))
    folder = Path(destination)
    if folder.is_file():
        error = f"Error: Cannot write folder to {destination}--file exists with the same name!"
        return reply(-1, "", error + "\nNotAFolder\n")
    if not folder.parent.is_dir():
        raise Unmodelled("preset folder parent missing")
    error = (
        f"Warning: Folder {destination} will be overwritten by this operation.\n"
        if folder.exists()
        else ""
    )
    error += f"Dumping Presets BRRES,{source} => {destination}\n"
    result = reply(0, template("dump presets"), error)
    result.make_parents = True
    result.writes = [(folder / f"{name}.rspreset", FAKE_BRRES) for name in MATERIALS]
    return result


COMMANDS = {
    "import-brres": _import,
    "brres-to-json": _to_json,
    "json-to-brres": _from_json,
    "dump-presets": _dump,
}


def main(argv: list[str]) -> int:
    def run() -> Outcome:
        help_reply = cli.replay(argv)
        if help_reply is not None:
            return help_reply
        parsed = cli.parse(argv)
        return COMMANDS[parsed.command.name](parsed)

    return finish("rszst", argv, run)
