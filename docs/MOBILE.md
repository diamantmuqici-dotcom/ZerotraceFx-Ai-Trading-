# Android companion

Android is a monitor and operator-control client for the Python engine running
on Windows. MetaTrader 5 stays on the Windows host because the official MT5
Python package is not an Android trading API.

## Setup

On the Windows host, set a long random bearer token and enable the API:

```dotenv
REMOTE_API_ENABLED=true
REMOTE_API_HOST=0.0.0.0
REMOTE_API_PORT=8765
REMOTE_API_TOKEN=<random value with at least 16 characters>
```

Start `python main.py trade` or the desktop dashboard, permit the port on a
private Windows Firewall profile, and enter the host LAN/VPN address and token
in the companion. The app does not request MT5 credentials.

## Controls

The companion reads real account balance/equity, open positions, broker-close
history, AI reasoning and risk state. Pause/resume and close-all requests are
bearer-authenticated and forwarded to the desktop engine; they do not create
or simulate orders on Android.

Use HTTPS through a trusted VPN/reverse proxy when crossing an untrusted
network. Do not expose port 8765 directly to the public internet.
