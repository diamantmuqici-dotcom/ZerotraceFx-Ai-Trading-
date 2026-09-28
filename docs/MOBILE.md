# Mobile and APK support

ZeroTrace FX AI does **not** currently provide an Android APK or an iOS app. The Windows release is a desktop application, and it cannot be repackaged into an APK as-is.

## Why there is no APK

- **MetaTrader 5 integration is Windows-only.** The Python `MetaTrader5` package used by this project's live-trading integration is distributed for Windows, and the MetaTrader 5 desktop terminal is required for that connection. It is not an Android trading API.
- **The dashboard is a desktop UI.** The current PySide6 dashboard and PyInstaller packaging are configured for desktop use; this repository does not include an Android UI, Android-compatible MT5 adapter, or mobile build configuration.
- **An APK would need a separate mobile implementation.** Supporting phones would require a dedicated mobile client and a secure service/API on a supported host. Simply bundling the current Python application would not provide working MT5 connectivity or a usable Android app.

## Current options

- Run the Windows desktop bundle on a supported Windows PC with MetaTrader 5 installed and configured.
- Use the source on a supported desktop environment for tests, backtests, and other platform-independent features. Live MT5 trading requires the supported Windows/MT5 setup.
- If remote access is necessary, use a trusted, secured remote-desktop solution to reach the Windows machine. Do not expose trading credentials or an unauthenticated control endpoint to the public internet.

There is no official ZeroTrace FX AI APK download. Be cautious of third-party APKs claiming to be this project. Forex trading involves substantial risk; software availability does not guarantee trading results.
