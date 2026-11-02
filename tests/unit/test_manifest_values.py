"""P3-T01: bad ``ctstudio.toml`` values and the schema-version upgrade framework.

Every bad value raises ``ManifestError`` naming the full key path and what is allowed.
``migrations.py`` upgrades older files one version at a step; only version 1 exists, so the
tests use a made-up version 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ctstudio.core.errors import ManifestError
from ctstudio.core.project import migrations
from ctstudio.core.project.manifest_io import FILE_NAME, load

pytestmark = pytest.mark.timeout(30)

HEAD = 'schema_version = 1\n[project]\nname = "X"\n'


def _load(tmp_path: Path, text: str) -> ManifestError:
    path = tmp_path / FILE_NAME
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ManifestError) as raised:
        load(path)
    return raised.value


@pytest.mark.parametrize(
    ("text", "key", "reason"),
    [
        (
            HEAD + 'slot = "rainbow"\n',
            "project.slot",
            'expected the file name of an original track or arena, such as "beginner_course"'
            ' or "old_mario_gc"; found "rainbow"',
        ),
        (HEAD.replace('"X"', '""'), "project.name", 'expected some text; found ""'),
        (HEAD.replace('"X"', "3"), "project.name", "expected text in quotes; found 3"),
        (HEAD + "version = 1.0\n", "project.version", "expected text in quotes; found 1.0"),
        (HEAD + 'blend = ""\n', "project.blend", 'expected some text; found ""'),
        (
            HEAD + '[build]\ntest_compression = "fastest"\n',
            "build.test_compression",
            'expected one of "best", "fast", "none"; found "fastest"',
        ),
        (
            HEAD + '[build]\nmake_d_variant = "yes"\n',
            "build.make_d_variant",
            'expected true or false; found "yes"',
        ),
        (HEAD + "[build]\nauto_add = 1\n", "build.auto_add", "expected true or false; found 1"),
        (
            HEAD + '[build]\nextra_wszst_args = "--x"\n',
            "build.extra_wszst_args",
            'expected a list of text, such as ["--a", "--b"]; found "--x"',
        ),
        (
            HEAD + "[build]\nextra_wszst_args = [1]\n",
            "build.extra_wszst_args",
            'expected a list of text, such as ["--a", "--b"]; found [1]',
        ),
        (
            HEAD + "[blender.collections]\ncourse = true\n",
            "blender.collections.course",
            "expected text in quotes; found true",
        ),
        (
            HEAD + '[components.kmp]\nmode = "auto"\n',
            "components.kmp.mode",
            'expected one of "manual"; found "auto"',
        ),
        (
            HEAD + '[components.posteffect]\nmode = "auto"\n',
            "components.posteffect.mode",
            'expected one of "template", "manual"; found "auto"',
        ),
        (
            HEAD + '[components.posteffect]\ntemplate_track = "nowhere"\n',
            "components.posteffect.template_track",
            'expected the file name of an original track or arena, such as "beginner_course"'
            ' or "old_mario_gc"; found "nowhere"',
        ),
        (
            HEAD + '[components.skybox]\nmode = "copy"\n',
            "components.skybox.mode",
            'expected one of "auto", "template", "manual"; found "copy"',
        ),
        (
            HEAD + '[components.skybox]\ntemplate_track = "space"\n',
            "components.skybox.template_track",
            'expected the file name of an original track or arena, such as "beginner_course"'
            ' or "old_mario_gc"; found "space"',
        ),
        (
            HEAD + '[components.kmp]\neditor = "notepad"\n',
            "components.kmp.editor",
            'expected one of "lorenzi", "kmp_cloud"; found "notepad"',
        ),
        (
            HEAD + '[components.course_model]\nbackend = "brawlcrate"\n',
            "components.course_model.backend",
            'expected one of "default", "rszst", "abmatt"; found "brawlcrate"',
        ),
        (
            HEAD + '[components.minimap]\nsource = "paint"\n',
            "components.minimap.source",
            'expected one of "kcl", "blender", "file"; found "paint"',
        ),
        (
            HEAD + '[components.course_model.textures."road.png"]\nformat = "DXT1"\n',
            'components.course_model.textures."road.png".format',
            'expected one of "CMPR", "RGB5A3", "RGBA32", "RGB565", "IA8", "IA4", "I8", "I4",'
            ' "C4", "C8", "C14X2"; found "DXT1"',
        ),
        (
            HEAD + '[components.course_model.textures."road.png"]\nmipmaps = -1\n',
            'components.course_model.textures."road.png".mipmaps',
            "expected a whole number from 0 to 10; found -1",
        ),
        (
            HEAD + '[components.course_model.textures."road.png"]\nmipmaps = 11\n',
            'components.course_model.textures."road.png".mipmaps',
            "expected a whole number from 0 to 10; found 11",
        ),
        (
            HEAD + '[components.course_model.textures."road.png"]\nmipmaps = true\n',
            'components.course_model.textures."road.png".mipmaps',
            "expected a whole number from 0 to 10; found true",
        ),
        (
            HEAD + '[components.course_model.materials.fence]\ncull = "both"\n',
            "components.course_model.materials.fence.cull",
            'expected one of "front", "back", "none"; found "both"',
        ),
        (
            HEAD + "[components.course_model.materials.fence]\ntransparency = 1\n",
            "components.course_model.materials.fence.transparency",
            'expected one of "auto", "opaque", "cutout", "translucent"; found 1',
        ),
        (
            HEAD + "[components.course_model]\ntextures = 3\n",
            "components.course_model.textures",
            "expected a table of named entries; found 3",
        ),
        (
            HEAD + '[components.course_model.textures]\n"road.png" = 3\n',
            'components.course_model.textures."road.png"',
            "expected a table; found 3",
        ),
        (HEAD + "[components]\nkcl = 3\n", "components.kcl", "expected a table; found 3"),
        ('schema_version = 1\nproject = "X"\n', "project", 'expected a table; found "X"'),
        (
            "schema_version = 1\n",
            "project",
            'missing; every project needs a [project] table with a name, such as name = "My Track"',
        ),
        (
            'schema_version = 1\n[project]\nauthor = "A"\n',
            "project.name",
            "missing; every project needs a name",
        ),
    ],
)
def test_a_bad_value_names_its_key_and_what_is_allowed(
    tmp_path: Path, text: str, key: str, reason: str
) -> None:
    error = _load(tmp_path, text)
    assert error.key_path == key
    assert error.user_message == f"Invalid ctstudio.toml value at '{key}': {reason}."


def test_a_long_found_value_is_shortened(tmp_path: Path) -> None:
    error = _load(tmp_path, HEAD + f'slot = "{"x" * 200}"\n')
    assert error.user_message.endswith('found "' + "x" * 40 + '…".')


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ('[project]\nname = "X"\n', "missing; expected schema_version = 1 at the top of the file"),
        ('schema_version = "1"\n[project]\nname = "X"\n', 'expected a whole number; found "1"'),
        ('schema_version = true\n[project]\nname = "X"\n', "expected a whole number; found true"),
        (
            'schema_version = 2\n[project]\nname = "X"\n',
            "this project was saved by a newer CT Studio (file version 2; this CT Studio"
            " reads up to 1). Update CT Studio to open it",
        ),
        (
            'schema_version = 0\n[project]\nname = "X"\n',
            "CT Studio cannot upgrade a version 0 file",
        ),
    ],
)
def test_a_bad_schema_version_is_explained(tmp_path: Path, text: str, reason: str) -> None:
    error = _load(tmp_path, text)
    assert error.key_path == "schema_version"
    assert error.user_message == f"Invalid ctstudio.toml value at 'schema_version': {reason}."


def _v0_to_v1(data: dict[str, object]) -> dict[str, object]:
    """Made-up version 0 kept the project name under [track].title."""
    track = data.pop("track")
    assert isinstance(track, dict)
    return {**data, "schema_version": 1, "project": {"name": track["title"]}}  # pyright: ignore[reportUnknownArgumentType]


def test_an_older_file_is_upgraded_on_load_and_not_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migrations, "STEPS", ((0, _v0_to_v1),))
    path = tmp_path / FILE_NAME
    text = 'schema_version = 0\n[track]\ntitle = "Old"\n'
    path.write_text(text, encoding="utf-8")
    m = load(path)
    assert m.project.name == "Old"
    assert m.schema_version == 1
    assert path.read_text(encoding="utf-8") == text  # load never writes


def test_upgrades_run_in_order_one_version_at_a_time() -> None:
    seen: list[int] = []

    def step(version: int) -> migrations.Step:
        def run(data: dict[str, object]) -> dict[str, object]:
            seen.append(version)
            assert data["schema_version"] == version
            return {**data, "schema_version": version + 1}

        return (version, run)

    steps = (step(1), step(0), step(2))  # listed out of order on purpose
    out = migrations.upgrade({"schema_version": 0, "k": "v"}, steps=steps, current=3)
    assert seen == [0, 1, 2]
    assert out == {"schema_version": 3, "k": "v"}


@pytest.mark.parametrize("produced", [0, 2])
def test_a_step_that_does_not_produce_the_next_version_is_a_bug_not_a_user_error(
    produced: int,
) -> None:
    steps: tuple[migrations.Step, ...] = ((0, lambda data: {**data, "schema_version": produced}),)
    with pytest.raises(RuntimeError, match=f"upgrade from version 0 produced version {produced}"):
        migrations.upgrade({"schema_version": 0}, steps=steps, current=2)


def test_the_current_file_needs_no_upgrade_and_is_returned_unchanged() -> None:
    data: dict[str, object] = {"schema_version": 1, "project": {"name": "X"}}
    assert migrations.upgrade(data, steps=(), current=1) == data


def test_the_shipped_steps_cover_every_version_below_the_current_one() -> None:
    froms = [version for version, _ in migrations.STEPS]
    assert len(froms) == len(set(froms))
    assert all(0 <= version < migrations.CURRENT for version in froms)
    assert migrations.CURRENT == 1
