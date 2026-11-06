# Creating and opening projects

CT Studio is under development. Project navigation and dashboard build controls are available
for projects with supplied parts. Automatic generation and GUI file assignment are not ready
yet; start with a project that already names its supplied files. The command-line build also
remains available.

## New project

Choose New project on the welcome screen, or File → New project… (Ctrl+N).
The wizard asks for a track name and location, an optional Blender file, the original track
or arena to replace, then shows a summary. It shows the project folder before creating it.
A folder with another project or existing files is refused. Finish creates and opens the
project; failures appear on the summary page so you can go back or try again.

## Open a project

Choose Open project on the welcome screen, or File → Open project… (Ctrl+O).
Select the project folder containing `ctstudio.toml`, not the Blender file or a build folder.
Opening and folder checks run in the background. Navigation is disabled until they finish.
If the folder cannot be opened, the explanation appears below the recent list and the project
already open stays open. A project held by another CT Studio opens read-only, marked in the
heading; close it in the other copy before reopening if you need to change it.

## Project overview

Creating or opening a project shows its dashboard: name, project folder, the original track
file it replaces, Blender source (if set), and whether the project is writable or read-only.
The eight cards show each part's mode, status icon and text, and a short explanation. Hover a
card to read all its reasons; these are also available to screen readers. Statuses are checked
in the background. Refresh statuses checks again without changing project files. An error
keeps the last checked statuses visible, so they may be out of date until a refresh succeeds.
During a build the last checked statuses stay visible and refresh is disabled until it ends.

Copy project folder and each available Copy path button copy a path without opening or
changing it. An automatically generated part's path is its planned output and may not exist
until built. A supplied part uses the chosen file. Objects has no single file to copy; Track
info copies the project manifest path. Copying remains available in read-only projects.

View → Recent projects (Ctrl+H) returns to the welcome list without closing the current project.
View → Project dashboard (Ctrl+D) returns to it. Tab reaches the available mode, copy and More controls; the
dashboard scrolls to focused controls in a small window. The four project actions use two rows
so their full button labels remain readable with larger desktop fonts. File → New/Open remain
available while idle.
Navigation errors and history-save problems stay visible on the welcome screen; a project that
opened successfully remains open, and its dashboard is still available from View.

Project details can edit the slot and source; component cards can change supported modes as
described below. Open in Blender, Open folder and building are described below. GUI file
assignment and automatic generation are still under development.

## Building from the dashboard

At the bottom of a writable project's dashboard, choose Build test (Ctrl+B) or Build release
(Ctrl+Shift+B). Release builds fail on validation errors; a successful test build is not proof
that a track is playable. The existing manual-mode builder still needs the project's supplied
files and required tools. Missing inputs or tools produce an explanation and a next step.

The progress bar starts with planning, then counts processed steps; unchanged/skipped steps
count too. A full bar is not a success message: the last result appears only after the build
worker has finished. Each part's separate Build label reports working, done, unchanged, failed,
cancelled or not run. Its checked status and explanation remain visible during the build;
"done" describes that build step, not a new status check. Statuses are checked again afterwards.

Cancel build (Esc while on the dashboard) requests cancellation. Wait for it to stop; pressing
Cancel does not release the project lock or make another build safe to start. Starting another
build, editing, opening a different project and launching Blender/folders are disabled while
it runs. Read-only projects and projects being checked or edited cannot start builds.

Build warnings/errors are separate from status-check and launch notices. The last result shows
the actual outcome and duration; hover it for the full build-log path, or an explanation when
no log was written. Screen readers receive these details too. After correcting a problem, wait
for the status check to finish and choose Build again. A new build clears the previous run's
messages and transient card progress; it keeps your choice to show or hide the live log.

You may view the recent-project list and return with View → Project dashboard without losing
the running build. If closing must wait for a build, the dashboard stays visible with a stopping
message; wait and close again. The project remains locked until its worker has stopped.

## Reading live build output

Show build log, just above the build buttons, reveals the current build's messages. The panel
starts collapsed and keeps collecting while hidden; hiding it never stops a build. Tab reaches
the toggle, Space opens/closes it, and the next Tab reaches the populated output list. Use the
arrow keys, Home and End to read the list; Tab continues to the available build/cancel buttons.
The dashboard scrolls to keyboard-focused controls in a small window.

New output follows the bottom only while you are at the end. Scroll upwards to read older
messages without being pulled back; return to the end to follow again. The view retains at
most the newest 20,000 physical lines and 2,000,000 message characters. Messages are capped at
4,096 characters and step names at 128, with an ellipsis marking shortened text. The caption
reports earlier lines omitted from this view. Scroll horizontally inside the list for wide
retained lines; the dashboard itself does not widen. The existing full on-disk log is unchanged
and its location remains in the build result's details (or the result explains why none exists).

Finishing, failing, cancelling or returning from Recent projects keeps the output available.
An accepted new build starts a fresh log but keeps your expanded/collapsed choice; a changed
project binding clears and collapses it. Messages from an old or mismatched run are ignored.
Output is literal text, not a terminal or a source of executable commands. Command copying is
not available yet; it needs trusted command entries rather than guesses from arbitrary output.

## Editing project details

On a writable project's dashboard, choose Project details… after the status check finishes.
Select the original track or arena to replace, and type or choose the full path of an existing
`.blend` file. Clear source removes the reference, not the file. You can leave it empty when
supplying track parts manually. Save applies both choices; Cancel or Escape discards the draft.

Reading, checking and saving run in the background. While work is in progress, fields and
Save/Cancel are disabled; wait for it to finish before closing. Other project navigation is
blocked while details are open, keeping the project's write lock. Read-only projects and a
running build cannot edit details. A save failure keeps the dialog open and the old project
settings in use, so you can correct the source or cancel.

Before saving, CT Studio checks that the project file and its in-memory settings still match
what the dialog loaded. If another editor changed the file, it refuses to replace it: cancel,
close/reopen the project, then try again. Each changed save keeps the original exact file beside
`ctstudio.toml` as a timestamped `.bak` and writes the new file atomically. Unknown settings are
preserved, but TOML comments/formatting are not; the backup retains them. Saving unchanged
choices does not rewrite or back up the file. The dashboard then updates and checks statuses again.

The file is checked again after the replacement has been prepared. If an external edit is found
then, saving stops and leaves that edit in place. Other editors do not obey CT Studio's lock:
there is still a very small gap between this final check and replacement that cannot be locked
across unrelated apps. Avoid editing `ctstudio.toml` elsewhere while pressing Save.

## Opening Blender and component folders

Open in Blender starts Blender with the project's source file. It needs a writable project
with a Blender source chosen in Project details, and uses the Blender path from Settings →
Tools when one is set. CT Studio only knows that Blender was started (it shows the process
number and any warning); it cannot tell whether Blender finished opening the file.

Each card's More (…) menu → Open folder asks your system's file manager to show that part's
folder. A generated part opens the folder it will be built into, even before the file exists;
the folder itself must already exist, and CT Studio never creates it. Objects has no single
folder. Open folder also works in read-only projects.

Both run in the background. While one is starting, the dashboard shows a progress bar, other
launch, edit and refresh controls are disabled, and switching or closing the project waits
until it finishes; copying paths still works. The result, or an explanation with a next step,
stays below the project details until the next launch, even after statuses are rechecked.
If no window appears, open the folder shown in the message yourself.

## Changing a component mode

After statuses finish checking, choose Change mode… on a component card, or use its More (…)
menu → Mode → the mode you want. The menu selects a draft, not a saved change. Only modes
supported by that component are listed. Parts with only one mode have no mode control.

The dialog explains the available choices: auto asks CT Studio to make the part from project
sources/settings, manual uses a supplied file or folder, and template uses the configured
original-track template. Save applies the choice; Cancel or Escape leaves it unchanged.
The mode checkmark and card stay at the last saved choice until Save succeeds.

Changing a mode never chooses, copies or deletes a file, nor clears inactive settings. Existing
manual references and template choices are retained when switching away and back. Switching to
manual without a supplied file will show that the part is missing; GUI file assignment is not
ready yet, so use projects that already name their supplied files.

Loading and saving run in the background with the same backups and external-edit protection
as project details. Read-only, checking and building projects cannot change modes. While a
mode dialog is open, project navigation is blocked; while its worker is active, Save, Cancel
and closing are disabled/refused. Wait for it to finish. A failure keeps the old project and
card statuses visible with an explanation. A successful save refreshes modes, paths and statuses.

More → Copy path is another way to use the existing lexical path copy: it does not open or
validate the target, which may not exist yet, and remains available in read-only projects.

## Recent projects

Successfully created or opened folders are saved in this computer's `settings.json`, newest
first, up to ten distinct folders. The list survives restarting CT Studio.
Select an entry and choose Open selected (or activate it with Enter/double-click).
Missing folders are marked Missing folder and cannot be opened from the list. They are not
silently removed: reconnect the drive and restart, or use Open to select the folder again.
Remove from list forgets only the entry; it never deletes the project or its files.

Settings saves preserve other settings and keep a backup of the previous file. If the settings
file or recent list is damaged or from a newer version, CT Studio reports it and will not
replace it. New and Open still work, but history cannot be saved until you fix that file.

Closing the app releases its project lock. If background work has not stopped yet, the window
stays open and asks you to wait and close again, rather than abandoning that work.
