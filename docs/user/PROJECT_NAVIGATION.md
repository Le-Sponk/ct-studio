# Creating and opening projects

CT Studio is under development. Project navigation works; the dashboard Build button is not
implemented yet. The command-line build remains available for projects with supplied parts.

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
View → Project dashboard (Ctrl+D) returns to it. Tab reaches the available copy buttons; the
dashboard scrolls to focused controls in a small window. File → New/Open remain available.
Navigation errors and history-save problems stay visible on the welcome screen; a project that
opened successfully remains open, and its dashboard is still available from View.

Project details can edit the slot and source as described below. Component actions and GUI
build controls are still under development; the command-line build remains available for supplied parts.

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

Open in Blender and other component actions are still under development.

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
