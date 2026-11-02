# The project file: `ctstudio.toml`

Every CT Studio project is a folder with a file called `ctstudio.toml` in it. CT Studio
reads it when you open the project and writes it when you change a project setting.
It is plain text, so you can also open it in a text editor.

## Comments are not kept

If you add comments (lines or line endings starting with `#`) and CT Studio later saves the
file, **your comments are gone**. CT Studio rewrites the whole file each time it saves,
and the part that writes TOML files cannot keep comments. Keep notes somewhere else, for
example a `NOTES.txt` in the project folder.

The values themselves are always kept, including any CT Studio does not recognise (for
example, a setting added by a newer CT Studio). CT Studio writes those back as they were and
notes each one in its log.

## What a small file looks like

```toml
schema_version = 1

[project]
name = "Sponk Speedway"
author = "Le-Sponk"
slot = "beginner_course"
blend = "source/track.blend"
```

Only `schema_version` and `[project]` `name` are required. Everything else has a sensible
default, so a missing setting means "use the default".

## The settings

| Setting | What it means | Allowed values (default first) |
|---|---|---|
| `schema_version` | The version of this file's layout. Do not change it. | `1` |
| `[project]` `name` | The track's name. | any text, not empty |
| `[project]` `author`, `version` | Shown with the track. | any text (`""`, `"1.0"`) |
| `[project]` `slot` | The original track your track replaces. | an original track or arena file name, such as `beginner_course`, `old_mario_gc` or `block_battle` |
| `[project]` `blend` | Your Blender file. | a path, relative to the project folder when inside it; leave it out for none |
| `[build]` `test_compression`, `release_compression` | How hard to compress the built track. | `best`, `fast`, `none` (test: `fast`, release: `best`) |
| `[build]` `make_d_variant` | Also build the `_d` copy of the track. | `true`, `false` |
| `[build]` `auto_add` | Let Wiimms SZS Tools add missing object files. | `true`, `false` |
| `[build]` `extra_wszst_args` | Extra options passed to Wiimms SZS Tools. | a list, such as `["--a", "--b"]` |
| `[blender.collections]` `course`, `kcl`, `skybox`, `minimap` | Which Blender collection holds each part. | collection names (`Course`, `KCL`, `Skybox`, empty minimap = make it from the KCL) |
| `[components.<part>]` `mode` | Whether CT Studio makes the part or you supply it. | `auto` or `manual`; KMP: `manual` only; post effects: `template` or `manual` |
| `[components.<part>]` `file` | Your own file, when the mode is `manual`. | a path, such as `files/course.kmp` |
| `[components.course_model]` `backend` | Which tool turns the model into a BRRES. | `default`, `rszst`, `abmatt` |
| `[components.course_model.textures."<name>.png"]` `format`, `mipmaps` | Your choice for one texture, instead of CT Studio's. | `CMPR`, `RGB5A3`, `RGBA32`, `RGB565`, `IA8`, `IA4`, `I8`, `I4`, `C4`, `C8`, `C14X2`; mipmaps `0` to `10` |
| `[components.course_model.materials."<name>"]` `transparency`, `cull` | Your choice for one material. | `auto`, `opaque`, `cutout`, `translucent`; cull `front`, `back`, `none` |
| `[components.minimap]` `source` | Where the minimap shape comes from. | `kcl`, `blender`, `file` |
| `[components.kmp]` `editor` | Which KMP editor CT Studio opens. | `lorenzi`, `kmp_cloud` |
| `[components.posteffect]` `template_track` | The original track whose lighting and effects to copy. | an original track or arena file name |
| `[hooks]` `post_stage`, `post_build` | Your own scripts, run at those points. | a path, or empty for none |

## When CT Studio cannot read the file

CT Studio leaves the file alone and tells you what is wrong, for example:

> Invalid ctstudio.toml value at 'build.test_compression': expected one of "best", "fast",
> "none"; found "fastest".

Fix that line in a text editor and open the project again.

- **A file from a newer CT Studio** (a higher `schema_version`) opens only in that newer
  version. CT Studio says so instead of guessing.
- **A file from an older CT Studio** is upgraded when it is opened. The file on disk is not
  changed until CT Studio next saves it.
