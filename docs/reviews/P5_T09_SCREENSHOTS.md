# P5-T09 screenshot review

The end-to-end flow tests take these pictures on every run (`tests/artifacts/screens/`,
git-ignored, never uploaded by CI). To make them on any machine:

```bash
uv run pytest tests/gui/test_end_to_end.py tests/gui/test_end_to_end_open_in.py
```

Reviewed by the agent from Windows offscreen runs (2026-11-25; corrected by the P5-T09b
review, whose run cut off a folder path that the first run happened to break) against
[REVIEW_CHECKLIST.md §5](../process/REVIEW_CHECKLIST.md). HC1 is the human look at the same
pictures and at the real app on the Mint host; the Linux pictures (Ubuntu fonts) are made
the same way there.

## Pictures

| File | What it shows |
|---|---|
| `p5-t09-1-wizard-summary.png` | New project wizard, summary page |
| `p5-t09-2-new-project.png` | Dashboard of the new project, first check done |
| `p5-t09-3-assigned.png` | Collision chosen and Course data dropped (manual mode) |
| `p5-t09-4-built.png` | After a test build: statuses and the build result |
| `p5-t09-5-issues.png` | Issues panel with a finding selected and its details |
| `p5-t09-6-editors.png` | Settings → Editors, "Your editors" after adding one |
| `p5-t09-7-open-in.png` | Open in… choice dialog |
| `p5-t09-8-started.png` | Dashboard notice after the editor was started |
| `p5-t09-9-dark.png`, `p5-t09-9-dark-large.png` | Dark palette; and with an enlarged font (about 150 %) |
| `p5-t09-9-dark-1280x720.png`, `p5-t09-9-dark-large-1280x720.png` | The same at 1280 × 720 |
| `p5-t09-10-light-1280x720.png` | Light at 1280 × 720 |

## Checklist §5

| Item | Result | Notes |
|---|---|---|
| One obvious primary action per card/page; destructive actions confirmed | Partly | Cards give "Change mode…" and "Copy path" equal weight; the build buttons sit at the bottom of the scrolling dashboard, below the issues panel, out of view at 1280 × 720 (Tab reaches them and scrolls, `test_build_dashboard_window.py`). Removing an editor asks first. → P5-T10 |
| Status never by colour alone | Yes | Every status has an icon and a word ("problem", "your own file", "missing", "ready", "warning"). |
| Plain-language labels; jargon explained | Mostly | "Replaces beginner_course.szs" on the dashboard vs "Replaces: Luigi Circuit (Mushroom Cup, track 1)" in the wizard: the dashboard should name the track too. → P5-T10 |
| No truncated text at 1280 × 720 and 150 % | No | Labels and statuses fit, but a folder path is cut off at the right edge when one of its folder names is longer than the line and has no space or hyphen to break at: the wizard summary's folder line and the dashboard's "Project folder" line (enlarged font), and the launch notice's file path when its own path has a long enough unbroken stretch. Paths only break at spaces and hyphens, so whether a picture shows it depends on the test's temporary folder (the review's run cut off the two folder lines; a run whose folder names break at a hyphen cuts off none). The wizard summary also breaks the folder straight after "C:". At 150 % on 1280 × 720 the header (folder, notices, two button rows) takes about 70 % of the height before the first card. → P5-T10 |
| Empty states say what to do; errors offer Copy details and a next step | Yes here | Each missing part says what is missing ("…has not been made yet"); a selected finding gives "Next:". Error dialogs were not reached in this flow (P5-T10 covers them). |
| Keyboard: tab order, Ctrl+B, Esc | Not pictured | Covered by tests (`test_build_dashboard_window.py`: shortcuts and Esc; tab to the footer). |
| Long operations show progress, can be cancelled, window responsive | Not pictured | The flow's waits are all on worker threads (wizard creation, assignment, build, status check, launch); cancel is tested elsewhere. |
| Advanced options out of the beginner's path | Yes | Mode changes sit behind "Change mode…" and the "…" menu; build settings are in Settings. |
| Every generated file has Open in… and Reveal | Yes | Card "…" menu: Open in… (single-file parts) and "Open folder". Folder parts (post-effects) have no Open in…, by design. |

## Other observations (for P5-T10)

- A card just assigned shows both "using files/course.kmp" and "Now using files/course.kmp
  (a copy of course.kmp)": the second repeats the first.
- Assigning a second part clears the first part's "Now using…" note (every card is rebound).
  Intended so far; P5-T10 decides whether the note should stay until the next check.
- The launch notice gives the full path of the opened file; long project folders make it
  three lines at 150 %.
- The Open in… dialog names the file only in its title bar ("Open course.kcl in…", not in
  the picture, which leaves out the window frame); its text says only "Choose an editor:" and
  never names the part (Collision).
- "Open in Blender" is shown disabled when no `.blend` is chosen; only the header line "No
  Blender file chosen" explains why (its tooltip says what it does, not why it is off).
- The editors list shortens long program paths in the middle ("pytest-of-ad…test_open…");
  the full path is in the row's tooltip.
