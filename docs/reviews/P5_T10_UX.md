# P5-T10 UX pass: closing review

The P5-T10 polish pass worked through the findings of the
[P5-T09 picture review](P5_T09_SCREENSHOTS.md). This page reruns the
[REVIEW_CHECKLIST.md §5](../process/REVIEW_CHECKLIST.md) pictures after it, light and dark,
at 1280 × 720 and at 150 %, and gives each §5 row a result. P5-GATE's phase review links it.

The tests take every picture on every run (`tests/artifacts/screens/`, git-ignored, never
uploaded by CI). To make them on any machine:

```bash
uv run pytest tests/gui/test_end_to_end.py tests/gui/test_end_to_end_open_in.py \
  tests/gui/test_build_bar.py tests/gui/test_compact_header.py \
  tests/gui/test_build_controls_visual.py tests/gui/test_high_dpi.py \
  tests/gui/test_tools_page_wide.py
```

Reviewed by the agent from Windows offscreen runs of commit `04296e1` (2026-11-26).
"About 150 %" means two things here: the end-to-end and build-bar pictures enlarge the font
(the way P5-T09 did), and the P5-T10h pictures run the whole app at a real 1.5× and 2× scale
on a 1280 × 720 screen. GitHub's Ubuntu runner runs the same checks with Ubuntu's fonts; HC1
is the human look at these pictures and at the real app on the Mint host.

## Pictures

| File | What it shows |
|---|---|
| `p5-t09-1-wizard-summary.png` … `p5-t09-8-started.png` | The end-to-end flow (new project, assign, build, issues, editors, Open in…, started notice) |
| `p5-t09-9-dark-1280x720.png`, `p5-t09-9-dark-large-1280x720.png` | Dark, at 1280 × 720, normal and enlarged font |
| `p5-t09-10-light-1280x720.png` | Light at 1280 × 720 |
| `p5-t10b-bar-{1280x720,800x600}[-enlarged].png` | The pinned build bar (P5-T10b) |
| `p5-t10d-header-*.png` | The compact header (P5-T10d) |
| `p5-t03e21-build-error-{light,dark}-{native,150}.png` | A failed build with Copy details (P5-T10f) |
| `p5-t10h-dashboard-{150,200}pct.png`, `p5-t10h-settings-{tools,editors}-{150,200}pct.png` | The populated dashboard and Settings at a real 1.5× and 2× (P5-T10h) |
| `p5-t10i-tools-*.png` | Settings → Tools at 1280 × 720 / 150 % and wide fonts (P5-T10i) |

## Checklist §5

| Item | Result | Notes |
|---|---|---|
| One obvious primary action per card/page; destructive actions confirmed | Yes | Each card has at most one button, "Change mode…" (hidden for parts with only one mode), with everything else in its "…" menu (P5-T10e removed the second copy button). Build test / Build release sit in a bar pinned to the window's bottom edge, visible without scrolling at 1280 × 720 and 800 × 600, normal and enlarged (P5-T10b). Removing an editor still asks first. |
| Status never by colour alone | Yes | Every checked status has an icon and a word, and "Not checked" is a word alone; no status is a colour only. The icons are drawn at the screen's scale (P5-T10h). |
| Plain-language labels; jargon explained | Yes | "Replaces Luigi Circuit (Mushroom Cup, track 1)", with the file in the tooltip; "Open in Blender" says why it is off; Open in… names the part and file ("Choose an editor for Collision (course.kcl)") (P5-T10a). |
| No truncated text at 1280 × 720 and 150 % | Partly → P13-T06 | Fixed: the dashboard's and wizard's paths stay on one line, shortened in the middle, with the whole path on hover and Copy, and the started and opened notices name files by their place in the project (P5-T10c); the high-DPI checks find no cut button, label, table or choice on the dashboard and Settings at 1.5× and 2× (P5-T10h). Left for P13-T06, each with its full text in the tooltip (and Copy details): the build bar's message does not break paths, so a long path is cut at the right edge mid-name and breaks straight after "C:", and the message stops at four lines with a sliver of a fifth (`p5-t03e21-build-error-*-150`); a card's description stops at its line limit without "…" at 800 × 600 enlarged (`p5-t10b-bar-800x600-enlarged`). |
| Empty states say what to do; errors offer Copy details and a next step | Yes | Missing parts say what is missing; build errors end with "Review the problem and retry the build." and offer Copy details; an unusable settings file and a failed status check offer it on the dashboard; an unexpected error shows one window with Copy details (P5-T10f). |
| Keyboard: tab order, Ctrl+B, Esc | Yes (tests) | Not pictured: Ctrl+B, Esc and the Tab walk to the build bar are tested in `test_build_dashboard_window.py`; the other Tab walks in `test_build_bar.py`, `test_component_card.py`, `test_component_card_actions.py` and (Settings → Tools, P5-T10i) `test_tools_page_wide.py`. |
| Long operations show progress, can be cancelled, window responsive | Yes (tests) | Not pictured: progress and Cancel live in the pinned build bar; every long step runs off the GUI thread; developer mode's stall watchdog logs any wait over 100 ms. |
| Advanced options out of the beginner's path | Yes | Mode changes sit behind "Change mode…" and the "…" menu; build and tool settings are in Settings. |
| Every generated file has Open in… and Reveal | Yes | Card "…" menu: Open in… (single-file parts), Copy path and Open folder; folder parts (post-effects) have no Open in…, by design. |

## What P5-T10 changed against the P5-T09 findings

| P5-T09 finding | Now |
|---|---|
| Two equal card buttons; build buttons out of view at 1280 × 720 | One card button; pinned build bar (P5-T10b, P5-T10e) |
| "Replaces beginner_course.szs" | The track's name (P5-T10a) |
| Folder paths cut off at the right edge; the wizard broke after "C:" | Middle-shortened one-line paths with hover and Copy (P5-T10c) |
| The header took about 70 % of the height at 150 % | The first card starts within about 35–40 % (P5-T10d) |
| "using …" repeated as "Now using …"; notes cleared by other cards | Notes say only what is new and stay until their own card changes (P5-T10e) |
| Error dialogs not reached | Copy details on errors; one window for unexpected errors (P5-T10f) |
| Open in… named neither part nor file; "Open in Blender" off without a reason | Both named; the reason in the tooltip (P5-T10a) |

Still open elsewhere: window size and position are not remembered (owner decision D5 →
P13-T09); the widest-font Settings sweep (TD-022 → P13-T06); a card beside a taller card
spreads its lines (P13-T06).

## Also seen, for HC1 and P13-T06

- Course model and Skybox say "problem" while Minimap says "missing", all three with the
  line "…has not been made yet" (`p5-t09-3`, `-9`, `-10`). The words are right: the first two
  also cannot be made right now (a tool or the .blend is missing), but a card's one line shows
  only its first reason, so that blocker is only in the tooltip and a beginner cannot tell why
  the cards differ.
- In the dark build-error pictures the disabled "Cancel build" is drawn as bright as the
  enabled buttons. The picture renders the build bar on its own with a test palette, and the
  dark dashboard pictures draw disabled buttons dimmed, so this is probably the test's palette;
  HC1 checks it in the real app.
