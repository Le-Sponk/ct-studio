# Opening part files in editors

CT Studio can start the editors you already use (BrawlCrate, RiiStudio, Lorenzi's KMP Editor,
KMP Cloud, Blender, or programs you add yourself) with one of your project's files. It starts
the editor and hands it the file; what happens inside the editor is up to the editor.

## Open in…

After a project's statuses are checked, a card whose part is one file that exists (Course
model, Collision, Minimap, Skybox, Course data) offers More (…) → Open in…. Parts that are not
one file (Post-effects, Objects, Track info) never offer it. CT Studio prepares the choices in
the background, then shows "Open course_model.brres in…" with every editor for that kind of
file: the built-in editors first, in the order you chose, then your own editors.

Choose an editor with the arrow keys or the mouse and press Enter or Open; Escape cancels.
An editor that cannot be used is still listed, marked "(not found)" or "(cannot open this
file)", with the reason and the next step below the list. For a missing built-in editor,
"Set up … in Tools…" opens Settings → Tools with that program selected (with several missing,
"Set up editors in Tools…" selects the first), so you can choose where it is or download it.
In a read-only project you can see the choices and set up tools, but no editor can be started
from it.

Each choice starts a new editor process with exactly one file. To edit two files, choose
Open in… twice; you get two editor windows. CT Studio never sends a second file to an editor
that is already running, and never offers to open several files at once.

Lorenzi's KMP Editor is only offered when a file named exactly `course.kcl` (lower case) sits
beside the KMP file; without it the editor would silently edit against an empty collision
box. CT Studio checks again when it starts the editor, in case the file was removed.

## Default editors

| File | Editors, first to last | Where it is offered |
| --- | --- | --- |
| `.brres` | BrawlCrate, RiiStudio | Course model, Minimap and Skybox cards |
| `.kmp` | Lorenzi's KMP Editor, KMP Cloud | Course data card |
| `.szs` | BrawlCrate, RiiStudio | `ctstudio open` on the command line ([CLI](../dev/CLI.md)) |
| `.blend` | Blender | Open in Blender, with the project's Blender source |
| Folders | Your system's file manager | a card's More (…) → Open folder |
| Any file | Your own editors, after the built-in ones | every Open in… (Collision has only these) |

## What “started” means

When an editor starts, the dashboard shows two lines like these, plus any warning:

    RiiStudio was started (process 4242) with C:\Tracks\castle\course_model.brres.
    CT Studio cannot tell whether RiiStudio finished opening the file.

CT Studio only knows that it started the program. It does not watch the editor's window or
output: RiiStudio, for example, can keep an empty window up after a failed load, and CT Studio
never reads its output to decide anything. If the editor shows no file, open the file from the
editor's own menu. Changes you save there are noticed by the project's cards as usual.

A warning is shown when a path is known to cause trouble, such as RiiStudio with accented or
non-Latin letters in the path on Windows.

## Choosing editors: Settings → Editors…

Settings → Editors… has three tabs. Each change is saved at once, and the next Open in… uses it
without restarting CT Studio.

- **Order**: for each kind of file with more than one built-in editor, the default order or the
  one editor you want first.
- **Your editors**: Add…, Edit… and Remove your own programs. An entry has a name (shown in
  Open in…), the program, and its arguments, one per line. Use `{file}` for the file, `{dir}`
  for its folder and `{project}` for the project folder. Each line stays one argument, spaces
  included (blank lines are skipped); there is no shell, so quotes and symbols are passed as
  written.
- **Wine (Linux)**: a Wine prefix folder for each Windows editor (see below).

Before each save CT Studio keeps a backup of the settings file and every setting it does not
know about. If the file is damaged, or was written by a newer CT Studio, the window shows its
path and why, and CT Studio will never overwrite it: fix the file or put a backup back, then
reopen Settings → Editors….

## Linux and Wine

BrawlCrate, KMP Cloud, RiiStudio and Lorenzi's KMP Editor are Windows programs. On Linux,
CT Studio starts them through Wine, each in a prefix folder you prepare once. Choose that folder
on the Wine (Linux) tab of Settings → Editors…; selecting an editor there shows the commands that
make a suitable prefix. For the built-in editors, Wine is found on your system unless you set its
program in Settings → Tools. Your own editors whose program ends in `.exe` also go through Wine,
but only with the Wine program set in Settings → Tools (CT Studio does not search for it) and a
prefix chosen on the Wine (Linux) tab; without both they are listed as "(not found)". Blender
must be the Linux build (Blender in Wine is not supported), and Flatpak editors cannot be
started yet.
The Wine tab is shown on every system; Windows ignores it.

## What is checked by hand

CT Studio's automated tests use stand-in programs, including a stand-in Wine, to check the exact
command for every editor on Windows and Linux, one new process per file, the refusals, and that
your files are left unchanged. They do not show whether a real editor loads or saves the file,
whether real Wine loads it on Linux, or how the editor windows look on your desktop. Those are
checked by hand at human checkpoint 1 (HC1, see
[HUMAN_CHECKPOINTS.md](../process/HUMAN_CHECKPOINTS.md)).
