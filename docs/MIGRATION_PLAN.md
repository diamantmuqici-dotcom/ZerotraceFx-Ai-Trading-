# ZeroTrace FX AI 2.0.0 migration plan

This plan records the repository audit and the safe replacement order used for
this release. Existing strategy and risk logic was preserved unless it could
route offline data or credentials into production.

## Audit findings

1. **Runtime boundary** — the previous composition root selected a paper broker
   for every non-LIVE value, and the CLI exposed backtest/demo flows.
2. **Authentication** — `MT5Client` accepted login/password/server settings and
   could call `mt5.login`, contrary to the already-authenticated-session rule.
3. **Market integrity** — MT5 rate retrieval included the forming bar; offline
   feeds could be injected into a generic data engine.
4. **Venue discovery** — no process/session status model existed, so the UI
   could only report a generic connection failure.
5. **Persistence** — the JSONL/CSV journal worked but had no indexed shared
   query store for the desktop/mobile surfaces.
6. **Presentation** — the repository had a PySide terminal but no Electron
   shell, responsive CSS-variable surface, or modular renderer.
7. **Release drift** — versions and CI targeted different Python releases, the
   release notes described simulator workflows, and the Windows build did not
   package the Electron workstation.
8. **Execution edge case** — a full live close reported the pre-close floating
   profit instead of querying settled MT5 deal history.

## Applied sequence

- Introduced a production-only real broker boundary in `core.engine` and
  removed simulator construction from production imports.
- Reworked settings and `MT5Client` so credentials are not modelled or stored;
  production attaches only to an authenticated real account.
- Added `core.process_detector` and `mt5.detector` for non-invasive desktop/web
  discovery. Browser presence is informational; it never authorises orders.
- Changed live status, diagnostics and both UI surfaces to the exact waiting
  message when no authenticated session is ready.
- Excluded the current MT5 forming candle and improved settled close-profit
  reconciliation.
- Added a WAL SQLite repository and kept JSONL/CSV as human-readable mirrors.
- Added the Electron main/preload/window/security/process layers, a modular
  renderer, responsive design system and selectable themes.
- Updated Android/release documentation, version 2.0.0, PyInstaller imports,
  npm packaging and CI compile coverage.
- Added regression tests for credential absence, real-only production broker
  selection and conservative browser detection.

## Follow-up gates before live rollout

1. Run `python main.py doctor` on the exact broker terminal and verify the
   account is real, the symbol suffixes resolve and risk limits are approved.
2. Build the Windows bundle on a clean Python 3.13 Windows runner and inspect
   the Electron installer plus portable artifact.
3. Test the official MT5 adapter with broker-approved minimum volume, filling
   mode, stop distance and market-hours constraints.
4. Test remote API exposure only through a private VPN/LAN and rotate the
   bearer token after each installation.
5. Confirm operator close-all, broker SL/TP reconciliation, restart history and
   kill-switch recovery from the journal/database.
6. Keep research fixtures outside the production UI and never use them to
   present performance claims.
