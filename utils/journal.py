"""Persistent trade journal: JSONL + CSV records of every decision and fill."""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any, Optional

from core.types import TradeSignal


class TradeJournal:
    """Append-only journal stored as JSON lines with a CSV mirror."""

    def __init__(self, directory: str = "logs") -> None:
        """Create the journal directory and file paths."""
        self.directory = directory
        os.makedirs(directory, exist_ok=True)
        self.jsonl_path = os.path.join(directory, "journal.jsonl")
        self.csv_path = os.path.join(directory, "journal.csv")
        self._csv_header = [
            "event", "time", "symbol", "action", "ticket", "volume",
            "entry", "exit", "sl", "tp", "profit", "confidence",
            "setup_id", "reason",
        ]
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, "w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(self._csv_header)

    def _append(self, record: dict[str, Any]) -> None:
        """Append one record to both JSONL and CSV stores."""
        with open(self.jsonl_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        with open(self.csv_path, "a", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerow([record.get(col, "") for col in self._csv_header])

    def record_signal(self, signal: TradeSignal, note: str = "") -> None:
        """Journal a strategy signal (entry or hold)."""
        self._append({
            "event": "SIGNAL", "time": signal.timestamp.isoformat(),
            "symbol": signal.symbol, "action": signal.action.value,
            "ticket": "", "volume": "", "entry": signal.entry, "exit": "",
            "sl": signal.stop_loss, "tp": signal.take_profit, "profit": "",
            "confidence": round(signal.confidence, 2), "setup_id": signal.setup_id,
            "reason": note or "; ".join(signal.reasoning[:6]),
        })

    def record_fill(
        self,
        symbol: str,
        action: str,
        ticket: str,
        volume: float,
        price: float,
        stop_loss: float,
        take_profit: float,
        confidence: float,
        setup_id: str = "",
        reason: str = "",
        when: Optional[datetime] = None,
    ) -> None:
        """Journal an order fill."""
        self._append({
            "event": "FILL", "time": (when or datetime.now()).isoformat(),
            "symbol": symbol, "action": action, "ticket": ticket,
            "volume": volume, "entry": price, "exit": "", "sl": stop_loss,
            "tp": take_profit, "profit": "", "confidence": confidence,
            "setup_id": setup_id, "reason": reason,
        })

    def record_close(
        self,
        symbol: str,
        action: str,
        ticket: str,
        volume: float,
        entry: float,
        exit: float,
        profit: float,
        reason: str = "",
        when: Optional[datetime] = None,
    ) -> None:
        """Journal a position close with realised profit."""
        self._append({
            "event": "CLOSE", "time": (when or datetime.now()).isoformat(),
            "symbol": symbol, "action": action, "ticket": ticket,
            "volume": volume, "entry": entry, "exit": exit, "sl": "",
            "tp": "", "profit": round(profit, 2), "confidence": "",
            "setup_id": "", "reason": reason,
        })

    def record_basket(self, event: str, detail: dict[str, Any]) -> None:
        """Journal a basket-level event (target hit, trailing close, reset)."""
        record = {"event": f"BASKET_{event}", "time": datetime.now().isoformat()}
        record.update({k: v for k, v in detail.items()})
        with open(self.jsonl_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def read_closes(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        """Closed-trade history (oldest first), rebuilt from the journal.

        Used to re-seed the dashboard History tab after a restart so the
        session's realised trades survive process restarts.
        """
        rows: list[dict[str, Any]] = []
        if not os.path.exists(self.jsonl_path):
            return rows
        with open(self.jsonl_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:  # tolerate torn lines
                    continue
                event = str(record.get("event", ""))
                if event == "CLOSE":
                    rows.append({
                        "time": str(record.get("time", "")),
                        "symbol": str(record.get("symbol", "")),
                        "action": f"{record.get('action', '')} {record.get('reason', '') or 'CLOSE'}".strip(),
                        "profit": float(record.get("profit", 0.0) or 0.0),
                        "reason": f"#{record.get('ticket', '')} {record.get('reason', '')}".strip(),
                    })
                elif event.startswith("BASKET_") and "profit" in record:
                    rows.append({
                        "time": str(record.get("time", "")),
                        "symbol": "BASKET",
                        "action": event.replace("BASKET_", "CLOSE "),
                        "profit": float(record.get("profit", 0.0) or 0.0),
                        "reason": str(record.get("reason", event)),
                    })
        if limit is not None:
            rows = rows[-limit:]
        return rows
