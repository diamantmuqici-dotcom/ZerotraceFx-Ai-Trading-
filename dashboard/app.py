"""ZeroTrace FX AI desktop dashboard (PySide6, dark institutional theme).

Launched directly by the Windows executable. Imports PySide6 lazily so the
rest of the platform (and the test-suite) works without Qt installed.

Layout: header bar (brand + live status), KPI strip, workspace tabs
(positions / equity / history / reasoning) and a control rail with the
basket, AI decision and risk panels.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from dashboard import theme
from dashboard.viewmodel import DashboardViewModel


def _require_qt() -> Any:
    """Import PySide6 on demand with a friendly error when missing."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore[import]
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg  # type: ignore[import]
        return QtCore, QtGui, QtWidgets, FigureCanvasQTAgg
    except ImportError as exc:  # pragma: no cover - Qt is Windows-runtime only
        raise RuntimeError(
            "The dashboard requires PySide6 and matplotlib. "
            "Install with: pip install PySide6 matplotlib"
        ) from exc


class MainWindow:  # created dynamically inside launch_dashboard (Qt-bound)
    """Placeholder for type checkers; the real window is built by the factory."""


def create_application(viewmodel: DashboardViewModel, refresh_ms: int = 1000):
    """Build the Qt application and main window without running the loop.

    Returns ``(app, window)``; :func:`launch_dashboard` wraps this with
    ``show()`` + ``exec()``. Exposed separately so headless tooling (demo,
    screenshots, UI tests) can drive the window directly.
    """
    QtCore, QtGui, QtWidgets, FigureCanvasQTAgg = _require_qt()
    from config.constants import APP_VERSION
    from dashboard import widgets as W
    from matplotlib.figure import Figure

    Qt = QtCore.Qt

    # ------------------------------------------------------------------
    # chart helpers
    # ------------------------------------------------------------------
    def _style_axis(ax: Any, show_x: bool = False) -> None:
        ax.set_facecolor(theme.BG)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(theme.BORDER)
        ax.spines["bottom"].set_linewidth(0.8)
        ax.tick_params(axis="both", colors=theme.FAINT, labelsize=8, length=0,
                       pad=6)
        ax.grid(axis="y", color=theme.BORDER_SOFT, linewidth=0.7)
        if not show_x:
            ax.tick_params(labelbottom=False)
            ax.set_xticklabels([])

    def _draw_equity(fig: Any, axes: Any, curve: list[float],
                     times: list[str]) -> None:
        ax, ax_dd = axes
        ax.clear()
        ax_dd.clear()
        _style_axis(ax)
        _style_axis(ax_dd, show_x=True)
        if len(curve) > 1:
            xs = list(range(len(curve)))
            tone = theme.pnl_tone(curve[-1] - curve[0])
            hexc = theme.tone_color(tone)
            ax.plot(xs, curve, color=hexc, linewidth=1.7, zorder=3)
            ax.fill_between(xs, curve, min(curve), color=hexc, alpha=0.10, zorder=2)
            ax.fill_between(xs, curve, min(curve), color=hexc, alpha=0.06, zorder=1)
            ax.axhline(curve[0], color=theme.BORDER, linewidth=0.8,
                       linestyle=(0, (4, 4)), zorder=1)
            ax.annotate(f"{curve[-1]:,.2f}", xy=(xs[-1], curve[-1]),
                        xytext=(-8, 10), textcoords="offset points",
                        ha="right", color=hexc, fontsize=9, fontweight="bold",
                        bbox=dict(boxstyle="round,pad=0.35", fc=theme.SURFACE_2,
                                  ec=theme.BORDER, lw=0.8))
            peak, dd = curve[0], [0.0]
            for value in curve:
                peak = max(peak, value)
                dd.append(min(dd[-1], (value - peak) / peak * 100.0))
            dd = dd[1:]
            ax_dd.fill_between(xs, dd, 0, color=theme.LOSS, alpha=0.16)
            ax_dd.plot(xs, dd, color=theme.LOSS, linewidth=1.0)
            ax_dd.set_ylim(min(dd) * 1.25 - 0.1, 0.1)
            if times and len(times) == len(curve):
                step = max(1, len(times) // 5)
                idx = list(range(0, len(times), step))
                ax_dd.set_xticks(idx)
                ax_dd.set_xticklabels([times[i] for i in idx])
        else:
            ax.text(0.5, 0.5, "waiting for equity ticks…", color=theme.FAINT,
                    ha="center", va="center", fontsize=10, transform=ax.transAxes)
            ax_dd.set_yticks([])
        ax.set_title("LIVE EQUITY", color=theme.FAINT, fontsize=8.5,
                     fontweight="bold", loc="left", pad=10)
        ax_dd.set_title("DRAWDOWN %", color=theme.FAINT, fontsize=8.5,
                        fontweight="bold", loc="left", pad=8)
        fig.tight_layout(pad=1.1, h_pad=1.6)

    # ------------------------------------------------------------------
    # diagnostics worker (runs the report off the UI thread)
    # ------------------------------------------------------------------
    class _DiagThread(QtCore.QThread):
        done = QtCore.Signal(str)

        def __init__(self, vm: DashboardViewModel) -> None:
            super().__init__()
            self.vm = vm

        def run(self) -> None:
            try:
                text = self.vm.diagnostics()
            except Exception as exc:  # noqa: BLE001 - report, never crash
                text = f"Diagnostics failed: {exc}"
            self.done.emit(text or (
                "Diagnostics are not wired in this mode.\n"
                "Run `python main.py doctor` from the repo folder instead."))

    # ------------------------------------------------------------------
    # window
    # ------------------------------------------------------------------
    class _MainWindow(QtWidgets.QMainWindow):
        def __init__(self, vm: DashboardViewModel) -> None:
            super().__init__()
            self.vm = vm
            self.setWindowTitle("ZeroTrace FX AI — Institutional Trading Terminal")
            self.resize(1440, 900)
            self.setMinimumSize(1180, 760)
            icon = W.icon_path()
            if icon:
                self.setWindowIcon(QtGui.QIcon(icon))
            self.setStyleSheet(theme.qss())
            W.apply_typography(self)

            central = QtWidgets.QWidget()
            self.setCentralWidget(central)
            root = QtWidgets.QVBoxLayout(central)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            root.addWidget(self._build_header())
            self.kill_banner = self._build_kill_banner()
            root.addWidget(self.kill_banner)

            body = QtWidgets.QHBoxLayout()
            body.setContentsMargins(16, 14, 16, 10)
            body.setSpacing(14)
            left, right = self._build_workspace()
            body.addLayout(left, 1)
            body.addLayout(right, 0)
            root.addLayout(body, 1)

            self.statusBar().setSizeGripEnabled(False)
            self._status_version = QtWidgets.QLabel("")
            self._status_version.setObjectName("metaLabel")
            self.statusBar().addPermanentWidget(self._status_version)
            self._status_clock = QtWidgets.QLabel("")
            self._status_clock.setObjectName("metaLabel")
            self.statusBar().addPermanentWidget(self._status_clock)

            self.clock_timer = QtCore.QTimer(self)
            self.clock_timer.timeout.connect(self._tick_clock)
            self.clock_timer.start(1000)
            self._diag_loaded = False
            self._diag_thread = None
            self.timer = QtCore.QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(refresh_ms)
            self._tick_clock()
            self.refresh()

        # -- construction ------------------------------------------------
        def _build_header(self) -> QtWidgets.QWidget:
            bar = QtWidgets.QFrame()
            bar.setObjectName("headerBar")
            bar.setFixedHeight(66)
            layout = QtWidgets.QHBoxLayout(bar)
            layout.setContentsMargins(18, 0, 18, 0)
            layout.setSpacing(12)
            layout.addWidget(W.BrandMark())
            titles = QtWidgets.QVBoxLayout()
            titles.setSpacing(1)
            title = QtWidgets.QLabel("ZeroTrace FX AI")
            title.setObjectName("brandTitle")
            title.setFont(W.ui_font(12.5, 700))
            sub = QtWidgets.QLabel("SMART MONEY AUTONOMOUS TERMINAL")
            sub.setObjectName("brandSub")
            sub.setFont(W.ui_font(7.5, 600, spacing=124))
            titles.addWidget(title)
            titles.addWidget(sub)
            layout.addLayout(titles)
            layout.addSpacing(10)
            self.mode_pill = W.Pill("PAPER", theme.INFO_TONE, dot=False)
            self.symbol_pill = W.Pill("—", theme.NEUTRAL, dot=False)
            self.session_pill = W.Pill("NO SESSION", theme.NEUTRAL, dot=False)
            layout.addWidget(self.mode_pill)
            layout.addWidget(self.symbol_pill)
            layout.addWidget(self.session_pill)
            layout.addStretch(1)
            self.clock = QtWidgets.QLabel("--:--:--")
            self.clock.setObjectName("clock")
            self.clock.setFont(W.ui_font(9.5, 600, mono=True))
            layout.addWidget(self.clock)
            sep = QtWidgets.QFrame()
            sep.setObjectName("divider")
            sep.setFixedSize(1, 26)
            layout.addWidget(sep)
            self.status_pill = W.Pill("STOPPED", theme.BAD)
            layout.addWidget(self.status_pill)
            return bar

        def _build_kill_banner(self) -> QtWidgets.QWidget:
            bar = QtWidgets.QFrame()
            bar.setObjectName("killBanner")
            bar.setFixedHeight(40)
            layout = QtWidgets.QHBoxLayout(bar)
            layout.setContentsMargins(18, 0, 18, 0)
            glyph = QtWidgets.QLabel("⚠")
            glyph.setStyleSheet(f"color: {theme.LOSS}; font-size: 15px; font-weight: 800;")
            text = QtWidgets.QLabel(
                "KILL SWITCH ENGAGED — new entries blocked and basket protected. "
                "Review the risk state, then reset when ready.")
            text.setObjectName("killBannerText")
            text.setFont(W.ui_font(9, 600))
            layout.addWidget(glyph)
            layout.addWidget(text, 1)
            btn = QtWidgets.QPushButton("Reset Kill Switch")
            btn.setObjectName("danger")
            btn.setFixedHeight(26)
            btn.clicked.connect(self._reset_kill)
            layout.addWidget(btn)
            bar.hide()
            return bar

        def _build_workspace(self) -> tuple[QtWidgets.QBoxLayout, QtWidgets.QBoxLayout]:
            left = QtWidgets.QVBoxLayout()
            left.setSpacing(12)

            grid = QtWidgets.QGridLayout()
            grid.setSpacing(10)
            self.spark = W.Sparkline()
            self.pos_pill = W.Pill("0 POS", theme.NEUTRAL, dot=False)
            defs = [
                ("balance", "Balance", None),
                ("equity", "Equity", self.spark),
                ("floating", "Floating PnL", self.pos_pill),
                ("daily", "Daily PnL", None),
                ("winrate", "Win Rate", None),
                ("drawdown", "Drawdown", None),
            ]
            self.cards: dict[str, W.StatCard] = {}
            for idx, (key, label, side) in enumerate(defs):
                card = W.StatCard(label, side=side)
                W.add_shadow(card, blur=22, y=6, alpha=70)
                self.cards[key] = card
                grid.addWidget(card, 0, idx)
            grid.setColumnStretch(0, 1)
            for idx in range(len(defs)):
                grid.setColumnStretch(idx, 1)
            left.addLayout(grid)

            panel = QtWidgets.QFrame()
            panel.setObjectName("panel")
            W.add_shadow(panel, blur=28, y=8, alpha=80)
            panel_layout = QtWidgets.QVBoxLayout(panel)
            panel_layout.setContentsMargins(6, 4, 6, 6)
            panel_layout.setSpacing(0)
            self.tabs = QtWidgets.QTabWidget()
            panel_layout.addWidget(self.tabs)

            # positions
            pos_wrap = QtWidgets.QWidget()
            pos_layout = QtWidgets.QVBoxLayout(pos_wrap)
            pos_layout.setContentsMargins(12, 10, 12, 12)
            pos_layout.setSpacing(8)
            self.pos_hint = QtWidgets.QLabel(
                "No open positions — the engine is scanning for A+ setups.")
            self.pos_hint.setObjectName("emptyHint")
            self.pos_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.pos_hint.setMinimumHeight(120)
            self.pos_table = QtWidgets.QTableWidget(0, 10)
            self.pos_table.setHorizontalHeaderLabels(
                ["TICKET", "SYMBOL", "SIDE", "LOTS", "ENTRY", "PRICE",
                 "STOP", "TARGET", "P&L", "AI"])
            self._configure_table(self.pos_table)
            pos_header = self.pos_table.horizontalHeader()
            pos_header.setStretchLastSection(False)
            for col in range(self.pos_table.columnCount()):
                pos_header.setSectionResizeMode(
                    col, QtWidgets.QHeaderView.ResizeMode.Stretch)
                item = self.pos_table.horizontalHeaderItem(col)
                if col >= 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight |
                                          Qt.AlignmentFlag.AlignVCenter)
                elif col == 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            pos_layout.addWidget(self.pos_hint)
            pos_layout.addWidget(self.pos_table, 1)
            self.pos_footer = QtWidgets.QLabel("")
            self.pos_footer.setObjectName("metaLabel")
            self.pos_footer.setFont(W.ui_font(8.5, 500, mono=True))
            pos_layout.addWidget(self.pos_footer)
            self.tabs.addTab(pos_wrap, "Positions")

            # equity
            chart_wrap = QtWidgets.QWidget()
            chart_layout = QtWidgets.QVBoxLayout(chart_wrap)
            chart_layout.setContentsMargins(10, 8, 10, 8)
            self.figure = Figure(figsize=(8.6, 4.0), dpi=110)
            self.figure.patch.set_alpha(0.0)
            self.ax_equity = self.figure.add_subplot(2, 1, 1)
            self.ax_dd = self.figure.add_subplot(2, 1, 2, sharex=self.ax_equity)
            self.canvas = FigureCanvasQTAgg(self.figure)
            self.canvas.setMinimumHeight(260)
            chart_layout.addWidget(self.canvas)
            self.tabs.addTab(chart_wrap, "Equity Curve")

            # history
            hist_wrap = QtWidgets.QWidget()
            hist_layout = QtWidgets.QVBoxLayout(hist_wrap)
            hist_layout.setContentsMargins(12, 10, 12, 12)
            hist_layout.setSpacing(8)
            self.hist_hint = QtWidgets.QLabel("No closed trades yet this session.")
            self.hist_hint.setObjectName("emptyHint")
            self.hist_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.hist_hint.setMinimumHeight(120)
            self.hist_table = QtWidgets.QTableWidget(0, 5)
            self.hist_table.setHorizontalHeaderLabels(
                ["TIME", "SYMBOL", "ACTION", "P&L", "REASON"])
            self._configure_table(self.hist_table)
            hist_layout.addWidget(self.hist_hint)
            hist_layout.addWidget(self.hist_table, 1)
            self.tabs.addTab(hist_wrap, "History")

            # reasoning
            reason_wrap = QtWidgets.QWidget()
            reason_layout = QtWidgets.QVBoxLayout(reason_wrap)
            reason_layout.setContentsMargins(14, 12, 14, 12)
            reason_layout.setSpacing(10)
            self.reason_head = QtWidgets.QLabel("")
            self.reason_head.setFont(W.ui_font(9.5, 600))
            self.reason_head.setTextFormat(Qt.TextFormat.RichText)
            self.reason_head.setWordWrap(True)
            self.reason_list = W.ReasonList()
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.reason_list)
            reason_layout.addWidget(self.reason_head)
            reason_layout.addWidget(scroll, 1)
            self.tabs.addTab(reason_wrap, "AI Reasoning")

            # diagnostics ("why isn't it trading?")
            diag_wrap = QtWidgets.QWidget()
            diag_layout = QtWidgets.QVBoxLayout(diag_wrap)
            diag_layout.setContentsMargins(14, 12, 14, 12)
            diag_layout.setSpacing(10)
            diag_head = QtWidgets.QHBoxLayout()
            diag_head.addWidget(W.SectionTitle("Gate-by-gate report"))
            diag_head.addStretch(1)
            self.btn_diag = QtWidgets.QPushButton("Run")
            self.btn_diag.setObjectName("ghost")
            self.btn_diag.setFixedSize(96, 28)
            self.btn_diag.clicked.connect(self._run_diagnostics)
            diag_head.addWidget(self.btn_diag)
            diag_layout.addLayout(diag_head)
            self.diag_view = QtWidgets.QTextEdit()
            self.diag_view.setObjectName("diagView")
            self.diag_view.setReadOnly(True)
            self.diag_view.setPlainText(
                "Click “Run Diagnostics” (or run `python main.py doctor` in the "
                "repo folder) to see every gate between the market and an order: "
                "mode/venue, MT5 connection and demo-vs-real, symbol data, "
                "spread/news/session filters, AI confidence and risk locks.")
            diag_layout.addWidget(self.diag_view, 1)
            self._diag_tab_index = self.tabs.addTab(diag_wrap, "Diagnostics")
            self.tabs.currentChanged.connect(self._on_tab_changed)

            left.addWidget(panel, 1)

            # ---------------- right rail ----------------
            right = QtWidgets.QVBoxLayout()
            right.setSpacing(12)
            right.addWidget(self._build_basket_panel())
            right.addWidget(self._build_ai_panel())
            right.addWidget(self._build_risk_panel())
            right.addStretch(1)
            return left, right

        def _build_basket_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QFrame()
            panel.setObjectName("panel")
            W.add_shadow(panel, blur=24, y=6, alpha=70)
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)
            head = QtWidgets.QHBoxLayout()
            head.addWidget(W.SectionTitle("Basket"))
            head.addStretch(1)
            self.direction_pill = W.Pill("NEUTRAL", theme.NEUTRAL, dot=False)
            head.addWidget(self.direction_pill)
            layout.addLayout(head)
            self.basket_value = QtWidgets.QLabel("$0.00")
            self.basket_value.setObjectName("bigValue")
            self.basket_value.setFont(W.ui_font(23, 700))
            layout.addWidget(self.basket_value)
            self.basket_track = W.ProgressTrack(height=8)
            layout.addWidget(self.basket_track)
            self.basket_progress_label = QtWidgets.QLabel("")
            self.basket_progress_label.setObjectName("cardSub")
            self.basket_progress_label.setFont(W.ui_font(8, 500))
            layout.addWidget(self.basket_progress_label)
            layout.addSpacing(2)
            for key, label in (("target", "Profit target"),
                               ("peak", "Session peak"),
                               ("trailing", "Trailing basket"),
                               ("count", "Open positions")):
                row = W.MetaRow(label)
                setattr(self, f"meta_{key}", row)
                layout.addWidget(row)
            layout.addSpacing(4)
            buttons = QtWidgets.QHBoxLayout()
            buttons.setSpacing(8)
            self.btn_pause = QtWidgets.QPushButton("Pause Entries")
            self.btn_pause.setObjectName("ghost")
            self.btn_close = QtWidgets.QPushButton("Close All")
            self.btn_close.setObjectName("danger")
            self.btn_reset = QtWidgets.QPushButton("Reset Kill")
            self.btn_reset.setObjectName("ghost")
            self.btn_pause.clicked.connect(self._toggle_pause)
            self.btn_close.clicked.connect(self._close_all)
            self.btn_reset.clicked.connect(self._reset_kill)
            buttons.addWidget(self.btn_pause, 1)
            buttons.addWidget(self.btn_reset, 1)
            buttons.addWidget(self.btn_close, 1)
            layout.addLayout(buttons)
            return panel

        def _build_ai_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QFrame()
            panel.setObjectName("panel")
            W.add_shadow(panel, blur=24, y=6, alpha=70)
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)
            head = QtWidgets.QHBoxLayout()
            head.addWidget(W.SectionTitle("AI Decision"))
            head.addStretch(1)
            self.signal_pill = W.Pill("HOLD", theme.NEUTRAL, dot=False)
            head.addWidget(self.signal_pill)
            layout.addLayout(head)
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(10)
            self.gauge = W.ConfidenceGauge()
            row.addWidget(self.gauge, 0, Qt.AlignmentFlag.AlignHCenter)
            meta = QtWidgets.QVBoxLayout()
            meta.setSpacing(0)
            for key, label in (("symbol", "Symbol"),
                               ("threshold", "Exec threshold"),
                               ("learned", "Trades learned")):
                widget = W.MetaRow(label)
                setattr(self, f"ai_{key}", widget)
                meta.addWidget(widget)
            meta.addStretch(1)
            row.addLayout(meta, 1)
            layout.addLayout(row)
            return panel

        def _build_risk_panel(self) -> QtWidgets.QWidget:
            panel = QtWidgets.QFrame()
            panel.setObjectName("panel")
            W.add_shadow(panel, blur=24, y=6, alpha=70)
            layout = QtWidgets.QVBoxLayout(panel)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(6)
            head = QtWidgets.QHBoxLayout()
            head.addWidget(W.SectionTitle("Risk & Session"))
            head.addStretch(1)
            self.dd_value = QtWidgets.QLabel("0.00%")
            self.dd_value.setFont(W.ui_font(10, 700, mono=True))
            head.addWidget(self.dd_value)
            layout.addLayout(head)
            self.dd_track = W.ProgressTrack(height=6)
            layout.addWidget(self.dd_track)
            layout.addSpacing(4)
            for key, label in (("daily", "Daily PnL"),
                               ("weekly", "Weekly PnL"),
                               ("margin", "Free margin"),
                               ("session", "Active session")):
                widget = W.MetaRow(label)
                setattr(self, f"risk_{key}", widget)
                layout.addWidget(widget)
            return panel

        @staticmethod
        def _configure_table(table: QtWidgets.QTableWidget) -> None:
            table.verticalHeader().setVisible(False)
            table.horizontalHeader().setVisible(True)
            table.setShowGrid(False)
            table.setAlternatingRowColors(True)
            table.setEditTriggers(
                QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(
                QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
            table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            table.setWordWrap(False)
            table.verticalHeader().setDefaultSectionSize(34)
            table.horizontalHeader().setHighlightSections(False)
            table.horizontalHeader().setDefaultAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.horizontalHeader().setSectionResizeMode(
                QtWidgets.QHeaderView.ResizeMode.Interactive)
            table.horizontalHeader().setStretchLastSection(True)
            table.setVerticalScrollMode(
                QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.setHorizontalScrollMode(
                QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel)
            header_font = W.ui_font(8, 700, spacing=116)
            table.horizontalHeader().setFont(header_font)

        # -- actions -------------------------------------------------------
        def _toggle_pause(self) -> None:
            snap = self.vm.snapshot()
            self.vm.set_paused(not snap["paused"])
            self.refresh()

        def _close_all(self) -> None:
            confirm = QtWidgets.QMessageBox(self)
            confirm.setIcon(QtWidgets.QMessageBox.Icon.Warning)
            confirm.setWindowTitle("Flatten the book?")
            confirm.setText("Close every open position at market, right now?")
            confirm.setInformativeText(
                "This sends immediate close orders for the whole basket. "
                "It cannot be undone.")
            confirm.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.Cancel)
            confirm.setDefaultButton(
                QtWidgets.QMessageBox.StandardButton.Cancel)
            if confirm.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            result = self.vm.close_all()
            message = result.get("message", result) if isinstance(result, dict) else result
            self.statusBar().showMessage(f"Close-all: {message}", 8000)

        def _reset_kill(self) -> None:
            self.vm.reset_kill_switch()
            self.statusBar().showMessage("Kill switch reset by operator", 8000)
            self.refresh()

        def _on_tab_changed(self, index: int) -> None:
            if index == self._diag_tab_index and not self._diag_loaded:
                self._run_diagnostics()

        def _run_diagnostics(self) -> None:
            self._diag_loaded = True
            self.btn_diag.setEnabled(False)
            self.btn_diag.setText("Running…")
            self.diag_view.setPlainText("Collecting gates…")
            self._diag_thread = _DiagThread(self.vm)
            self._diag_thread.done.connect(self._show_diagnostics)
            self._diag_thread.start()

        def _show_diagnostics(self, text: str) -> None:
            self.diag_view.setPlainText(text)
            self.btn_diag.setEnabled(True)
            self.btn_diag.setText("Re-run")

        def _tick_clock(self) -> None:
            now = datetime.now(timezone.utc)
            self.clock.setText(now.strftime("%H:%M:%S UTC"))

        # -- refresh ---------------------------------------------------------
        def refresh(self) -> None:
            try:
                snap = self.vm.snapshot()
            except Exception as exc:  # noqa: BLE001 - UI must never crash
                self.statusBar().showMessage(f"Snapshot error: {exc}")
                return

            running = snap["running"] and not snap["paused"]
            if snap["kill_switch"]:
                self.status_pill.set_state("Kill switch", theme.BAD)
            elif running:
                self.status_pill.set_state("Running", theme.GOOD)
            elif snap["paused"]:
                self.status_pill.set_state("Paused", theme.WARN_TONE)
            else:
                self.status_pill.set_state("Stopped", theme.NEUTRAL)
            self.kill_banner.setVisible(bool(snap["kill_switch"]))
            self.mode_pill.set_state(str(snap["mode"]),
                                     theme.BAD if snap["mode"] == "LIVE" else theme.INFO_TONE)
            self.symbol_pill.set_state(str(snap.get("active_symbol") or "NO SYMBOL"),
                                       theme.NEUTRAL)
            self.session_pill.set_state(str(snap.get("session") or "OFF SESSION"),
                                        theme.INFO_TONE if snap.get("session") else theme.NEUTRAL)

            positions = snap["open_positions"]
            trades = snap["recent_trades"]

            # KPI strip
            self.cards["balance"].set_value(theme.money(snap["balance"]))
            self.cards["balance"].set_sub(
                f"{str(snap['mode']).lower()} account · margin {theme.money(snap.get('margin', 0.0))}")
            curve = snap["equity_curve"]
            self.spark.set_data(curve, theme.pnl_tone(curve[-1] - curve[0]) if len(curve) > 1 else theme.GOOD)
            self.cards["equity"].set_value(theme.money(snap["equity"]))
            self.cards["equity"].set_sub(f"{len(curve)} ticks this session")
            self.cards["floating"].set_value(theme.money(snap["floating"], sign=True),
                                             theme.pnl_tone(snap["floating"]))
            self.cards["floating"].set_sub("unrealised, all symbols")
            self.pos_pill.set_state(f"{len(positions)} OPEN",
                                    theme.GOOD if positions else theme.NEUTRAL)
            daily = snap.get("daily_pnl", 0.0)
            self.cards["daily"].set_value(theme.money(daily, sign=True),
                                          theme.pnl_tone(daily))
            weekly = snap.get("weekly_pnl", 0.0)
            self.cards["daily"].set_sub(f"week {theme.money(weekly, sign=True)}",
                                        theme.pnl_tone(weekly))
            self.cards["winrate"].set_value(theme.percent(snap["win_rate"], 1))
            wins = int(round(snap["win_rate"] * snap["total_trades"] / 100.0)) \
                if snap["total_trades"] else 0
            self.cards["winrate"].set_sub(f"{wins} of {snap['total_trades']} closed trades")
            dd = snap["drawdown_pct"]
            self.cards["drawdown"].set_value(theme.percent(dd), theme.drawdown_tone(dd))
            self.cards["drawdown"].set_sub("hard stop at 8.00%",
                                           theme.drawdown_tone(dd))

            # basket panel
            basket = snap["basket_profit"]
            self.basket_value.setText(theme.money(basket, sign=True))
            self.basket_value.setStyleSheet(
                f"color: {theme.tone_color(theme.pnl_tone(basket))};")
            target = snap["basket_target"] or 0.0
            ratio = (basket / target) if target > 0 else 0.0
            self.basket_track.set_progress(ratio, theme.pnl_tone(basket))
            self.basket_progress_label.setText(
                f"{max(0.0, ratio) * 100:.0f}% of target" if target > 0 else "no target set")
            self.direction_pill.set_state(
                str(snap["basket_direction"]),
                theme.GOOD if snap["basket_direction"] == "BULLISH"
                else (theme.BAD if snap["basket_direction"] == "BEARISH" else theme.NEUTRAL))
            self.meta_target.set_value(theme.money(target))
            self.meta_peak.set_value(theme.money(snap["basket_highest"], sign=True),
                                     theme.pnl_tone(snap["basket_highest"]))
            self.meta_trailing.set_value(
                "ACTIVE" if snap.get("trailing_active") else "off",
                theme.GOOD if snap.get("trailing_active") else theme.NEUTRAL)
            self.meta_count.set_value(f"{len(positions)}")
            self.btn_pause.setText("Resume Entries" if snap["paused"] else "Pause Entries")
            self.btn_pause.setObjectName(
                "primary" if snap["paused"] else "ghost")
            self.btn_pause.style().unpolish(self.btn_pause)
            self.btn_pause.style().polish(self.btn_pause)
            self.btn_reset.setEnabled(bool(snap["kill_switch"]))

            # AI panel
            signal = str(snap["last_signal"]).upper()
            self.signal_pill.set_state(
                signal,
                theme.GOOD if signal == "BUY"
                else (theme.BAD if signal == "SELL" else theme.NEUTRAL))
            self.gauge.set_value(float(snap["last_confidence"]))
            self.ai_symbol.set_value(str(snap.get("active_symbol") or "—"))
            self.ai_threshold.set_value("85.0")
            self.ai_learned.set_value(f"{snap.get('ai_trades_learned', 0)}")

            # risk panel
            self.dd_value.setText(theme.percent(dd))
            self.dd_value.setStyleSheet(f"color: {theme.tone_color(theme.drawdown_tone(dd))};")
            self.dd_track.set_progress(dd / 8.0, theme.drawdown_tone(dd))
            self.risk_daily.set_value(theme.money(daily, sign=True), theme.pnl_tone(daily))
            self.risk_weekly.set_value(theme.money(weekly, sign=True), theme.pnl_tone(weekly))
            self.risk_margin.set_value(theme.money(snap.get("free_margin", 0.0)))
            self.risk_session.set_value(str(snap.get("session") or "—"),
                                        theme.INFO_TONE if snap.get("session") else theme.NEUTRAL)

            # positions table
            self.pos_hint.setVisible(not positions)
            self.pos_table.setVisible(bool(positions))
            self.pos_table.setRowCount(len(positions))
            for row, pos in enumerate(positions):
                tone = theme.pnl_tone(pos["profit"])
                self.pos_table.setItem(row, 0, W.text_item(str(pos["ticket"])))
                self.pos_table.setItem(row, 1, W.text_item(str(pos["symbol"]), bold=True))
                self.pos_table.setItem(
                    row, 2,
                    W.table_pill_item(str(pos["action"]),
                                      theme.GOOD if str(pos["action"]).upper() == "BUY"
                                      else theme.BAD))
                self.pos_table.setItem(row, 3, W.numeric_item(f"{pos['volume']:.2f}"))
                self.pos_table.setItem(row, 4, W.numeric_item(f"{pos['entry']:.5f}"))
                self.pos_table.setItem(row, 5, W.numeric_item(f"{pos['current']:.5f}"))
                self.pos_table.setItem(row, 6, W.numeric_item(f"{pos['sl']:.5f}"))
                self.pos_table.setItem(row, 7, W.numeric_item(f"{pos['tp']:.5f}"))
                self.pos_table.setItem(row, 8, W.numeric_item(
                    f"{pos['profit']:+,.2f}", tone))
                self.pos_table.setItem(row, 9, W.numeric_item(
                    f"{pos.get('confidence', 0.0):.0f}",
                    theme.GOOD if pos.get("confidence", 0.0) >= 85 else theme.WARN_TONE))
            if positions:
                lots = sum(p["volume"] for p in positions)
                symbols = " · ".join(dict.fromkeys(p["symbol"] for p in positions))
                self.pos_footer.setText(
                    f"{len(positions)} positions  ·  {lots:.2f} lots gross  ·  {symbols}   "
                    f"Σ P&L {theme.money(sum(p['profit'] for p in positions), sign=True)}")
            else:
                self.pos_footer.setText("flat — no market exposure")

            # history table
            self.hist_hint.setVisible(not trades)
            self.hist_table.setVisible(bool(trades))
            self.hist_table.setRowCount(len(trades))
            for row, trade in enumerate(trades):
                profit = float(trade.get("profit", 0.0))
                stamp = str(trade.get("time", ""))
                self.hist_table.setItem(row, 0, W.text_item(
                    stamp[5:16] if len(stamp) > 16 else stamp, mono=True))
                self.hist_table.setItem(row, 1, W.text_item(str(trade.get("symbol", "")), bold=True))
                self.hist_table.setItem(row, 2, W.text_item(str(trade.get("action", ""))))
                self.hist_table.setItem(row, 3, W.numeric_item(f"{profit:+,.2f}",
                                                               theme.pnl_tone(profit)))
                self.hist_table.setItem(row, 4, W.text_item(str(trade.get("reason", ""))[:80]))
            for col in (0, 1, 2, 3):
                self.hist_table.resizeColumnToContents(col)

            # reasoning
            lines = list(snap.get("last_reasoning", []))
            conf = float(snap["last_confidence"])
            self.reason_head.setText(
                f"<span style='color:{theme.MUTED};'>Latest decision</span> "
                f"<span style='color:{theme.TEXT};font-weight:700;'>{signal}</span> "
                f"<span style='color:{theme.FAINT};'>on</span> "
                f"<span style='color:{theme.TEXT};font-weight:700;'>"
                f"{snap.get('active_symbol') or '—'}</span> "
                f"<span style='color:{theme.FAINT};'>at confidence</span> "
                f"<span style='color:{theme.tone_color(theme.GOOD if conf >= 85 else theme.WARN_TONE)};"
                f"font-weight:700;'>{conf:.1f}</span>")
            self.reason_list.set_lines(
                [self._reason_line(line) for line in lines]
                if lines else [(theme.FAINT, "Waiting for the next decision cycle…")])

            # chart
            _draw_equity(self.figure, (self.ax_equity, self.ax_dd),
                         curve, list(snap.get("equity_times", [])))
            self.canvas.draw_idle()

            # tabs + status bar
            self.tabs.setTabText(0, f"Positions ({len(positions)})")
            self.tabs.setTabText(2, f"History ({len(trades)})")
            extra = f"  |  basket {snap['basket_direction']} × {len(positions)}" if positions else ""
            self.statusBar().showMessage(f"{snap['status_message']}{extra}")
            self._status_version.setText(f"v{APP_VERSION}")
            self._status_clock.setText(
                f"updated {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC")

        @staticmethod
        def _reason_line(line: str) -> tuple[str, str]:
            """Map a reasoning sentence to (dot tone colour, text)."""
            text = str(line).strip()
            low = text.lower()
            if any(k in low for k in ("✓", "pass", "confirmed", "aligned", "approved")):
                col = theme.ACCENT
            elif any(k in low for k in ("✗", "fail", "blocked", "against", "reject")):
                col = theme.LOSS
            elif any(k in low for k in ("watch", "caution", "partial")):
                col = theme.WARN
            else:
                col = theme.INFO
            return col, text

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle("Fusion")
    window = _MainWindow(viewmodel)
    return app, window


def launch_dashboard(viewmodel: DashboardViewModel, refresh_ms: int = 1000) -> int:
    """Build the Qt application, run the event loop and return the exit code."""
    app, window = create_application(viewmodel, refresh_ms)
    window.show()
    return int(app.exec())
