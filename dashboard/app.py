"""ZeroTrace FX AI desktop dashboard (PySide6, dark institutional theme).

Launched directly by the Windows executable. Imports PySide6 lazily so the
rest of the platform (and the test-suite) works without Qt installed.
"""
from __future__ import annotations

from typing import Any, Optional

from dashboard.viewmodel import DashboardViewModel

DARK_QSS = """
QMainWindow, QWidget { background-color: #0b0f14; color: #e6edf3; font-family: 'Segoe UI', sans-serif; }
QLabel#title { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#subtitle { font-size: 12px; color: #8b949e; }
QFrame#card { background-color: #11161d; border: 1px solid #1f2937; border-radius: 10px; }
QLabel#cardTitle { font-size: 11px; color: #8b949e; text-transform: uppercase; }
QLabel#cardValue { font-size: 20px; font-weight: 700; color: #ffffff; }
QLabel#good { color: #22c55e; } QLabel#bad { color: #ef4444; } QLabel#warn { color: #f59e0b; }
QTableWidget { background-color: #11161d; border: 1px solid #1f2937; border-radius: 8px; gridline-color: #1f2937; }
QHeaderView::section { background-color: #161d26; color: #8b949e; border: none; padding: 6px; }
QPushButton { background-color: #1c2530; border: 1px solid #2d3a4a; border-radius: 8px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background-color: #243041; }
QPushButton#danger { background-color: #7f1d1d; border-color: #ef4444; }
QPushButton#danger:hover { background-color: #991b1b; }
QPushButton#accent { background-color: #14532d; border-color: #22c55e; }
QTextEdit { background-color: #0d1117; border: 1px solid #1f2937; border-radius: 8px; font-family: Consolas, monospace; font-size: 11px; }
QTabWidget::pane { border: 1px solid #1f2937; border-radius: 8px; }
QTabBar::tab { background: #11161d; padding: 8px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #1c2530; color: #ffffff; }
"""


def _require_qt() -> Any:
    """Import PySide6 on demand with a friendly error when missing."""
    try:
        from PySide6 import QtCore, QtWidgets  # type: ignore[import]
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # type: ignore[import]
        return QtCore, QtWidgets, FigureCanvasQTAgg
    except ImportError as exc:  # pragma: no cover - Qt is Windows-runtime only
        raise RuntimeError(
            "The dashboard requires PySide6 and matplotlib. "
            "Install with: pip install PySide6 matplotlib"
        ) from exc


class MainWindow:  # created dynamically inside launch_dashboard (Qt-bound)
    """Placeholder for type checkers; the real window is built by the factory."""


def launch_dashboard(viewmodel: DashboardViewModel, refresh_ms: int = 1000) -> int:
    """Build the Qt application, run the event loop and return the exit code."""
    QtCore, QtWidgets, FigureCanvasQTAgg = _require_qt()
    import matplotlib

    matplotlib.use("QtAgg")
    from matplotlib.figure import Figure

    class _StatCard(QtWidgets.QFrame):
        def __init__(self, title: str, parent: Optional[Any] = None) -> None:
            super().__init__(parent)
            self.setObjectName("card")
            layout = QtWidgets.QVBoxLayout(self)
            layout.setContentsMargins(12, 10, 12, 10)
            self.title = QtWidgets.QLabel(title.upper())
            self.title.setObjectName("cardTitle")
            self.value = QtWidgets.QLabel("--")
            self.value.setObjectName("cardValue")
            layout.addWidget(self.title)
            layout.addWidget(self.value)

        def set_value(self, text: str, tone: str = "") -> None:
            self.value.setText(text)
            self.value.setObjectName("cardValue")
            if tone in ("good", "bad", "warn"):
                self.value.setStyleSheet(
                    {"good": "color:#22c55e", "bad": "color:#ef4444",
                     "warn": "color:#f59e0b"}[tone]
                )
            else:
                self.value.setStyleSheet("")

    class _MainWindow(QtWidgets.QMainWindow):
        def __init__(self, vm: DashboardViewModel) -> None:
            super().__init__()
            self.vm = vm
            self.setWindowTitle("ZeroTrace FX AI - Institutional Trading Dashboard")
            self.resize(1280, 860)
            self.setStyleSheet(DARK_QSS)
            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)
            root.setContentsMargins(16, 14, 16, 14)
            root.setSpacing(12)
            header = QtWidgets.QHBoxLayout()
            title_box = QtWidgets.QVBoxLayout()
            title = QtWidgets.QLabel("ZERO TRACE FX AI")
            title.setObjectName("title")
            subtitle = QtWidgets.QLabel("Institutional Smart Money Autonomous Forex Trading Platform")
            subtitle.setObjectName("subtitle")
            title_box.addWidget(title)
            title_box.addWidget(subtitle)
            header.addLayout(title_box)
            header.addStretch(1)
            self.status_pill = QtWidgets.QLabel("STOPPED")
            self.status_pill.setObjectName("cardValue")
            header.addWidget(self.status_pill)
            self.btn_pause = QtWidgets.QPushButton("Pause Entries")
            self.btn_close = QtWidgets.QPushButton("CLOSE ALL NOW")
            self.btn_close.setObjectName("danger")
            self.btn_reset = QtWidgets.QPushButton("Reset Kill Switch")
            self.btn_reset.setObjectName("accent")
            self.btn_pause.clicked.connect(self._toggle_pause)
            self.btn_close.clicked.connect(self._close_all)
            self.btn_reset.clicked.connect(self._reset_kill)
            header.addWidget(self.btn_pause)
            header.addWidget(self.btn_reset)
            header.addWidget(self.btn_close)
            root.addLayout(header)
            grid = QtWidgets.QGridLayout()
            grid.setSpacing(10)
            self.cards: dict[str, _StatCard] = {}
            defs = [
                ("balance", "Balance"), ("equity", "Equity"),
                ("floating", "Floating PnL"), ("basket", "Basket Profit"),
                ("target", "Basket Target"), ("highest", "Basket Highest"),
                ("winrate", "Win Rate"), ("drawdown", "Drawdown"),
                ("signal", "Last Signal"), ("confidence", "Confidence"),
                ("session", "Session"), ("mode", "Mode"),
            ]
            for idx, (key, label) in enumerate(defs):
                card = _StatCard(label)
                self.cards[key] = card
                grid.addWidget(card, idx // 6, idx % 6)
            root.addLayout(grid)
            tabs = QtWidgets.QTabWidget()
            root.addWidget(tabs, 1)
            self.pos_table = QtWidgets.QTableWidget(0, 8)
            self.pos_table.setHorizontalHeaderLabels(
                ["Ticket", "Symbol", "Side", "Lots", "Entry", "Current", "SL/TP", "Profit"])
            self.pos_table.horizontalHeader().setStretchLastSection(True)
            self.pos_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tabs.addTab(self.pos_table, "Open Positions")
            self.figure = Figure(figsize=(10, 4), facecolor="#0b0f14")
            self.ax = self.figure.add_subplot(111)
            self.canvas = FigureCanvasQTAgg(self.figure)
            tabs.addTab(self.canvas, "Equity Curve")
            self.hist_table = QtWidgets.QTableWidget(0, 5)
            self.hist_table.setHorizontalHeaderLabels(
                ["Time", "Symbol", "Action", "Profit", "Reason"])
            self.hist_table.horizontalHeader().setStretchLastSection(True)
            self.hist_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            tabs.addTab(self.hist_table, "Trade History")
            self.log_view = QtWidgets.QTextEdit()
            self.log_view.setReadOnly(True)
            tabs.addTab(self.log_view, "Reasoning")
            self.statusBar().showMessage("Initialising...")
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(refresh_ms)
            self.refresh()

        def _toggle_pause(self) -> None:
            snap = self.vm.snapshot()
            self.vm.set_paused(not snap["paused"])
            self.btn_pause.setText("Resume Entries" if not snap["paused"] else "Pause Entries")

        def _close_all(self) -> None:
            result = self.vm.close_all()
            self.statusBar().showMessage(f"Close-all: {result.get('message', result)}", 8000)

        def _reset_kill(self) -> None:
            self.vm.reset_kill_switch()
            self.statusBar().showMessage("Kill switch reset by operator", 8000)

        def refresh(self) -> None:
            try:
                snap = self.vm.snapshot()
            except Exception as exc:  # noqa: BLE001 - UI must never crash
                self.statusBar().showMessage(f"Snapshot error: {exc}")
                return
            running = snap["running"] and not snap["paused"]
            self.status_pill.setText(
                "KILL SWITCH" if snap["kill_switch"] else (
                    "RUNNING" if running else ("PAUSED" if snap["paused"] else "STOPPED")))
            money = lambda v: f"${v:,.2f}"
            self.cards["balance"].set_value(money(snap["balance"]))
            self.cards["equity"].set_value(money(snap["equity"]))
            self.cards["floating"].set_value(
                money(snap["floating"]), "good" if snap["floating"] >= 0 else "bad")
            self.cards["basket"].set_value(
                money(snap["basket_profit"]), "good" if snap["basket_profit"] >= 0 else "bad")
            self.cards["target"].set_value(money(snap["basket_target"]))
            self.cards["highest"].set_value(money(snap["basket_highest"]))
            self.cards["winrate"].set_value(f"{snap['win_rate']:.1f}%")
            dd = snap["drawdown_pct"]
            self.cards["drawdown"].set_value(f"{dd:.2f}%", "bad" if dd >= 5 else ("warn" if dd >= 2 else "good"))
            self.cards["signal"].set_value(snap["last_signal"])
            self.cards["confidence"].set_value(f"{snap['last_confidence']:.1f}")
            self.cards["session"].set_value(str(snap["session"] or "--"))
            self.cards["mode"].set_value(str(snap["mode"]))
            positions = snap["open_positions"]
            self.pos_table.setRowCount(len(positions))
            for row, pos in enumerate(positions):
                cells = [pos["ticket"], pos["symbol"], pos["action"],
                         f"{pos['volume']:.2f}", f"{pos['entry']:.5f}",
                         f"{pos['current']:.5f}", f"{pos['sl']:.5f}/{pos['tp']:.5f}",
                         f"{pos['profit']:+.2f}"]
                for col, text in enumerate(cells):
                    item = QtWidgets.QTableWidgetItem(str(text))
                    if col == 7:
                        item.setForeground(QtWidgets.QColor(
                            "#22c55e" if pos["profit"] >= 0 else "#ef4444"))
                    self.pos_table.setItem(row, col, item)
            curve = snap["equity_curve"]
            self.ax.clear()
            if len(curve) > 1:
                self.ax.plot(curve, color="#22c55e", linewidth=1.6)
                self.ax.fill_between(range(len(curve)), curve, alpha=0.12, color="#22c55e")
            self.ax.set_facecolor("#0b0f14")
            self.ax.grid(alpha=0.2)
            self.ax.set_title("Live Equity", color="#e6edf3", fontsize=11)
            self.figure.tight_layout()
            self.canvas.draw()
            history = snap["recent_trades"]
            self.hist_table.setRowCount(len(history))
            for row, trade in enumerate(history):
                cells = [str(trade.get("time", ""))[:19], str(trade.get("symbol", "")),
                         str(trade.get("action", "")), f"{float(trade.get('profit', 0.0)):+.2f}",
                         str(trade.get("reason", ""))[:60]]
                for col, text in enumerate(cells):
                    self.hist_table.setItem(row, col, QtWidgets.QTableWidgetItem(text))
            status = snap["status_message"]
            extra = f" | Basket {snap['basket_direction']} x{len(positions)}" if positions else ""
            self.statusBar().showMessage(f"{status}{extra}")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = _MainWindow(viewmodel)
    window.show()
    return int(app.exec())
