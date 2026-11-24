# docs/dev

Agent-maintained developer notes created during the build:
`ENVIRONMENT.md` (P0-T01), `SPIKES.md` (Phase 0), `BENCHMARKS.md` (P1/P4, updated at gates),
`CLI.md` (P3), `BRIDGE.md` (P6), `ADDON_LIVE_LINK.md` (P6-T07 proposal).

## Dev mode

Set `CTSTUDIO_DEV=1` before starting `ctstudio` to watch for UI freezes (P5-T01b), or turn
on Settings → Advanced → Developer mode, which takes effect from the next start (P5-T08e3).
Each time the window stops responding for more than 100 ms, one warning with the UI thread's
stack goes to the CT Studio log (`ctstudio.log` in the user log folder); the log also says
when the watchdog starts. Any other value of the variable, with the setting off, leaves it
off.
