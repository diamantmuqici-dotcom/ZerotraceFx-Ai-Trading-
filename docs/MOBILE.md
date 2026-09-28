# Android companion app (APK)

Each release ships `ZeroTraceFXAI-<version>-android.apk`. It is a **remote monitor
and control app** for the ZeroTrace engine running on your Windows PC.

## Why a companion app and not the full engine?

MetaTrader 5's Python API (`MetaTrader5` package) only works on Windows with the
MT5 desktop terminal. Android has no equivalent API, so the trading engine stays
on the PC. The phone connects to it.

## What the app does

- Live account: balance, equity, floating, daily PnL, drawdown, win rate
- Basket profit vs target, direction, trailing state
- Last AI decision with its confidence and reasoning
- Adaptive learning stats: trades learned, learned component weights,
  per-symbol win rate and threshold adjustment
- Open positions and recent closed trades (refreshes every 3 s)
- **Pause / resume** trading and **Close all positions** (asks for confirmation)

## Setup

1. On the PC, edit `.env`:
   ```
   REMOTE_API_ENABLED=true
   REMOTE_API_PORT=8765
   REMOTE_API_TOKEN=<a long random string, 16+ characters>
   ```
2. Start ZeroTrace (dashboard or `trade` mode). The log shows `Remote API listening`.
3. Allow inbound TCP 8765 in Windows Firewall (private networks only).
4. Install the APK on the phone (allow "install unknown apps" for your browser/files app).
5. In the app enter `http://<PC LAN IP>:8765` and the token, then tap **Connect**.

## Security

- Every request needs `Authorization: Bearer <token>`; the server refuses to
  start with a short token. Comparison is constant-time.
- Traffic is plain HTTP. Use it on your home LAN or through a VPN such as
  Tailscale/WireGuard. **Never port-forward it to the public internet.**
- The APK is signed with a debug key unless the release workflow is given a
  keystore (`ZT_KEYSTORE*` environment variables). Only install APKs from this
  repository's Releases page.
