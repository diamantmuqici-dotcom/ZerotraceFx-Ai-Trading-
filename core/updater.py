"""Conservative update metadata helper; downloads are delegated to release CI."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    notes: str = ""


def newer(current: str, candidate: str) -> bool:
    def parts(value: str) -> tuple[int, ...]:
        return tuple(int(part) for part in value.lstrip("v").split(".") if part.isdigit())
    return parts(candidate) > parts(current)
