# Creating and opening projects

CT Studio is under development. Project navigation, dashboard build controls and GUI file
assignment are available for projects with supplied parts. Automatic generation is not ready
yet; supply the required parts using the cards as described below. The command-line build also
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

CT Studio notices when files of an open project change outside it, for example a made part
edited in BrawlCrate or the Blender file saved: the statuses are checked again on their own
within about two seconds, and a part CT Studio made that was changed elsewhere shows "edited
outside CT Studio". CT Studio's own working files, finished tracks and Blender's backup copies
(`.blend1`) do not trigger a check. A Blender file or supplied file kept outside the project
folder is watched too, and if its drive is unplugged and plugged back in, the statuses are
checked each time and watching carries on. Changes made during a build show when the build's
own check runs. If changes can no longer be noticed (for example the project folder was
deleted or moved), a message under the status line says so; press Refresh statuses after
changing files, which also tries watching again.

Copy project folder and each available Copy path button copy a path without opening or
changing it. An automatically generated part's path is its planned output and may not exist
until built. A supplied part uses the chosen file. Objects has no single file to copy; Track
info copies the project manifest path. Copying remains available in read-only projects.

View → Recent projects (Ctrl+H) returns to the welcome list without closing the current project.
View → Project dashboard (Ctrl+D) returns to it. Tab reaches the available mode, copy and More controls; the
dashboard scrolls to focused controls in a small window. The four project actions use two rows
so their full button labels remain readable with larger desktop fonts. Component mode text
and its Change mode button also use separate rows to keep complete labels within each card.
File → New/Open remain available while idle.
Navigation errors and history-save problems stay visible on the welcome screen; a project that
opened successfully remains open, and its dashboard is still available from View.

Project details can edit the slot and source; component cards can change supported modes as
described below. Open in Blender, Open folder, building and using your own file for a part are
described below. Automatic generation is still under development.

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
The dashboard scrolls to keyboard-focused controls in a small window. While a build runs, a
small window also scrolls the dashboard down to keep the newest output, the build bar and the
final result in view. Scroll the dashboard up to read the cards without being pulled back;
scroll back to the bottom (or start another build) to follow again.

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
Output is literal text, not a terminal or a source of executable commands.

Each tool a build step starts gets its own bold "Ran:" line, written by CT Studio when it
starts the tool (never read from the tool's output). With that line selected in the log list,
Copy command copies the exact command: press Ctrl+Shift+C while the list has keyboard focus
(click the list or Tab to it first), or right-click the line → Copy command. Ctrl+C still copies
the line as shown. If newer output pushes the line you right-clicked out of the log while the
menu is open, Copy command turns off rather than copying a different command.
Ordinary output never offers Copy command, even when it looks like a command. On Windows the
copied text is a command line for PowerShell (type `& ` before pasting) or for programs that
start tools directly; it is not escaped for the old Command Prompt (cmd.exe), where `%` and
unquoted `& ^ | < >` change its meaning. On Linux and macOS it is POSIX shell quoting. Values a
step marks sensitive read `<redacted>`. A command too long for the list cannot be copied there;
its tooltip points to the full build log on disk.

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
manual without a supplied file will show that the part is missing until you give it one (see
"Using your own file for a part").

Loading and saving run in the background with the same backups and external-edit protection
as project details. Read-only, checking and building projects cannot change modes. While a
mode dialog is open, project navigation is blocked; while its worker is active, Save, Cancel
and closing are disabled/refused. Wait for it to finish. A failure keeps the old project and
card statuses visible with an explanation. A successful save refreshes modes, paths and statuses.

More → Copy path is another way to use the existing lexical path copy: it does not open or
validate the target, which may not exist yet, and remains available in read-only projects.

## Using your own file for a part

Course model, Collision, Minimap, Skybox, Course data and Post-effects can use a file you
supply (a folder for Post-effects). Drag one file or folder from your file manager onto the
part's card, or use the card's More (…) menu:

- Choose file… (Choose folder… for Post-effects) copies it into the project's `files` folder
  under the name the game uses (such as `files/course.kcl`) and uses that copy.
- Reference file in place… uses it where it is and copies nothing, so keep it there. For a file
  outside the project the card shows its name; hover over the note for the full path.

A drop is always a copy: holding Shift (move) in your file manager does not move or delete the
original. CT Studio first checks that it is the right kind of file for that part; a wrong file is
refused with an explanation on the card and nothing changes. A different copy already in `files`
is backed up to `.ctstudio/backups/` first; the card names that backup (hover for the full path,
and the note's text can be selected and copied). An identical copy is left alone.
The part's mode becomes manual and ctstudio.toml is saved with its usual backup; statuses are
then checked again. Dropping several files, a web link or anything that is not a file on this
computer is explained on the card and does nothing.

It runs in the background like Open folder: while it runs the card says so, other edit, launch,
refresh and build controls wait, and switching or closing the project waits until it finishes.
It is not available in read-only projects or while statuses are checked, a build runs, or a
dialog is open. The result stays on that card until the next assignment or the next time the
project's cards are shown again.

## Keeping or discarding an outside edit

When a generated part's file changes in another program, its card shows "Edited outside
CT Studio" with Lock as manual and Discard… choices. This normally appears within about two
seconds while the project is open and its folders can be watched; wait for the status check
to finish before choosing. These choices are for generated outputs, not for parts already
using manual mode. If watching reports a problem, press Refresh statuses after changing files;
this checks the cards and tries watching again. Automatic generation is still not ready yet:
these controls handle existing generated outputs, not a promise that generators are available.

To keep the change, choose Lock as manual. CT Studio makes an exact copy of the changed file
(or folder) in `files/` under the game's filename, switches this part to manual and saves
`ctstudio.toml`. Later builds use that supplied copy rather than regenerating the part.
A different copy already in `files/` is backed up in `.ctstudio/backups/` before replacement;
an identical copy is kept. The manifest save has its usual timestamped backup too.
The card reports "Locked as manual" and the file now used, plus any previous-copy backup.

To stop using the outside edit, choose Discard…. A native confirmation titled "Discard outside
edit?" asks whether to move the changed file or folder to a backup. Cancel is the default;
confirm with Discard only if you want the next build to remake the part. CT Studio moves the
changed output into `.ctstudio/backups/<UTC time>/`, keeping its project-relative path, and
removes it from `.ctstudio/stage/`. The backup keeps your edit; the card then reports the
missing output. Discard does not start a build or regenerate anything immediately. The next
build will remake the output when its generator is available and its inputs are ready.
Cancel changes nothing: no file is moved, no backup is made and no setting changes.

Use Tab to reach Lock as manual or Discard… and Space to activate the focused button.
In the Discard confirmation, Escape chooses Cancel; Enter also keeps the default Cancel
unless you explicitly select Discard. The dashboard scrolls to keyboard-focused controls.
There is no Capture button yet; capturing edits back into the source is planned for P7.

The choices are disabled in a read-only project, while statuses are being checked, during a
build, while an edit dialog is open, or while another launch or file request is running.
During your request the card says "Locking as manual…" or "Backing up outside edit…" and
shows progress; other edit, launch, refresh and build controls are disabled. Switching or
closing the project must wait. CT Studio keeps the project lock until the worker has
finished and been joined, not merely until a button returns or an error appears.
Each card has its own activity and outcome; a result for one part is not a result for another.
The outcome stays visible after the edited warning disappears. Hover it for the full text
and backup paths; screen readers receive those details too.

An action or startup failure does not mean rollback: the request may already have changed
files. CT Studio reloads the actual saved project after the worker finishes, rather than
assuming the old settings are still correct. If it reports "Saved project reloaded; changes
may have finished", check this card before trying again. If the file or project changed
before the choice could run, the request can be refused; refresh, or reopen as instructed.
Choices approved for an old project or an out-of-date card are not applied to a new one.

If "The saved project could not be read" appears, or changed project settings cannot safely
be shown, CT Studio protects the project as read-only while keeping its lock. Do not keep
retrying writes from this view. Follow "Close CT Studio and reopen this project before
editing" to load fresh saved state; check its cards and any backup before trying again.
Closing may still ask you to wait if background work has not stopped.

Linux desktop appearance is not verified; automated checks and local Windows screenshots
do not establish how these controls look on a Linux desktop.

## Finding and fixing issues

Every build checks the finished track (Wiimm's `wszst check`, plus CT Studio's own checks) and
keeps the results in `.ctstudio/issues.json`. The Issues panel below the cards shows the last
check's results whenever the project opens, after Refresh and after every build. Findings are
grouped by the part they are about, in card order, with "Whole track" last for anything about
the track as a whole; each group says how many errors, warnings, hints and notes it has, and
within it errors come first.

Select a finding to see, below the list, its next step, the file it is about and which part it
belongs to. "Open help page" opens that part's page on the Custom Mario Kart wiki in your
browser. Saved links are limited to HTTPS pages on `mkwiiki.org`; an invalid link falls back
to the part's known help page, or disables the button if there is none. Click a finding, or
press Enter on it, to scroll to that part's card and put the keyboard focus on it. "Copy
report" copies every finding, with next steps, files and help
pages, as text you can paste into a forum post or bug report.

Before the first build the panel says the track has not been checked yet. If the saved results
cannot be read it says so; build again to check the track afresh. If a status check fails, the
last results stay on screen.

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
