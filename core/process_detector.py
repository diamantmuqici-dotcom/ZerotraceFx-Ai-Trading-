"""Safe process/window probes used for authenticated venue discovery.

This module never reads process memory, credentials, browser cookies, or
terminal files. It only asks the operating system which public processes and
windows are present. Trading remains disabled until the official MT5 API
confirms an authenticated real account.
"""
from __future__ import annotations

import csv
import os
import subprocess
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class ProcessMatch:
    """A public process observation."""

    executable: str
    pid: int | None = None
    title: str = ""


@dataclass(frozen=True)
class SessionDiscovery:
    """Non-invasive discovery result for desktop and web terminals."""

    desktop_running: bool = False
    web_running: bool = False
    desktop_processes: tuple[ProcessMatch, ...] = field(default_factory=tuple)
    web_processes: tuple[ProcessMatch, ...] = field(default_factory=tuple)

    @property
    def any_terminal_present(self) -> bool:
        """Whether a candidate MT5 desktop/browser process is visible."""
        return self.desktop_running or self.web_running

    @property
    def waiting_message(self) -> str:
        """Operator-facing status used when no authenticated venue is ready."""
        return "Waiting for authenticated MT5 session..."


def _tasklist() -> list[ProcessMatch]:
    """Read executable names from Windows tasklist without shell execution."""
    if os.name != "nt":
        return []
    try:
        completed = subprocess.run(
            ["tasklist", "/V", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    matches: list[ProcessMatch] = []
    for fields in csv.reader(completed.stdout.splitlines()):
        if len(fields) < 2:
            continue
        try:
            pid = int(fields[1].strip())
        except ValueError:
            pid = None
        title = fields[-1].strip() if len(fields) >= 9 else ""
        matches.append(ProcessMatch(fields[0].strip().lower(), pid=pid, title=title))
    return matches


def _browser_candidates() -> tuple[str, ...]:
    """Executables capable of hosting a user-authenticated MT5 web tab."""
    return (
        "msedge.exe", "chrome.exe", "firefox.exe", "brave.exe",
        "opera.exe", "vivaldi.exe",
    )


def discover_sessions(processes: Iterable[ProcessMatch] | None = None) -> SessionDiscovery:
    """Discover desktop and browser candidates without claiming authentication.

    Browser presence is only a hint: MetaTrader Web has no supported Python
    trading API. The web detector therefore never authorises an order; it is a
    status signal until a future user-authorized connector is available.
    """
    observed = list(processes) if processes is not None else _tasklist()
    desktop = tuple(p for p in observed if p.executable.lower() in {
        "terminal64.exe", "terminal.exe", "metatrader.exe",
    })
    browser_names = set(_browser_candidates())
    web = tuple(
        p for p in observed
        if p.executable.lower() in browser_names
        and any(token in p.title.lower() for token in ("metatrader", "mt5", "metaquotes"))
    )
    return SessionDiscovery(
        desktop_running=bool(desktop),
        web_running=bool(web),
        desktop_processes=desktop,
        web_processes=web,
    )
