"""Hand-painted Qt widgets for the ZeroTrace terminal.

Imported lazily by :mod:`dashboard.app` so the platform keeps working on
machines without PySide6. Everything here is presentational: widgets read
plain python values (floats, strings, tones) and never touch engine state.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from dashboard import theme


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def color(hex_color: str, alpha: int = 255) -> QtGui.QColor:
    """Parse ``#rrggbb`` and apply an alpha (0-255)."""
    c = QtGui.QColor(hex_color)
    c.setAlpha(alpha)
    return c


def ui_font(size: float = 12, weight: int = 500, mono: bool = False,
            spacing: float = 100.0) -> QtGui.QFont:
    """Build a font from the theme stacks."""
    font = QtGui.QFont()
    font.setFamilies(theme.MONO_STACK if mono else theme.FONT_STACK)
    font.setPointSizeF(size)
    font.setWeight(QtGui.QFont.Weight(weight))
    if spacing != 100.0:
        spacing_type = getattr(QtGui.QFont, "SpacingType", None) or getattr(
            QtGui.QFont, "LetterSpacingType")
        font.setLetterSpacing(spacing_type.PercentageSpacing, spacing)
    return font


def add_shadow(widget: QtWidgets.QWidget, blur: int = 26, y: int = 8,
               alpha: int = 90) -> QtWidgets.QGraphicsDropShadowEffect:
    effect = QtWidgets.QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QtGui.QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(effect)
    return effect


class SectionTitle(QtWidgets.QLabel):
    """Uppercase, letter-spaced micro heading."""

    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text.upper(), parent)
        self.setObjectName("sectionTitle")
        self.setFont(ui_font(8.5, 700, spacing=116))


class MetaRow(QtWidgets.QWidget):
    """`label ......... value` row used inside side panels."""

    def __init__(self, label: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(8)
        self.label = QtWidgets.QLabel(label)
        self.label.setObjectName("metaLabel")
        self.label.setFont(ui_font(9, 500))
        self.value = QtWidgets.QLabel("--")
        self.value.setObjectName("metaValue")
        self.value.setFont(ui_font(9, 600, mono=True))
        self.value.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight |
                                QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.value)

    def set_value(self, text: str, tone: str = theme.NEUTRAL) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(f"color: {theme.tone_color(tone)};")


# ---------------------------------------------------------------------------
# status pill (animated dot)
# ---------------------------------------------------------------------------

class Pill(QtWidgets.QWidget):
    """Rounded status chip with an optional pulsing dot."""

    _STYLES: dict[str, tuple[str, str]] = {
        theme.GOOD: (theme.ACCENT, "RUNNING"),
        theme.BAD: (theme.LOSS, "STOPPED"),
        theme.WARN_TONE: (theme.WARN, "PAUSED"),
        theme.INFO_TONE: (theme.INFO, "INFO"),
        theme.NEUTRAL: (theme.MUTED, "IDLE"),
    }

    def __init__(self, text: str = "", tone: str = theme.NEUTRAL,
                 dot: bool = True, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._text = text
        self._tone = tone
        self._dot = dot
        self._phase = 0.0
        self.setMinimumHeight(24)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60)

    # -- api -----------------------------------------------------------
    def set_state(self, text: str, tone: str) -> None:
        if text != self._text or tone != self._tone:
            self._text, self._tone = text, tone
            self.updateGeometry()
            self.update()

    # -- internals -----------------------------------------------------
    def _tick(self) -> None:
        self._phase = (self._phase + 0.08) % (2 * math.pi)
        if self._dot:
            self.update()

    def _base_color(self) -> str:
        return theme.tone_color(self._tone)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt API
        font = ui_font(8.5, 700, spacing=110)
        width = QtGui.QFontMetrics(font).horizontalAdvance(self._text.upper())
        width += 22 + (14 if self._dot else 0)
        return QtCore.QSize(width, 24)

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        base = color(self._base_color())
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QtGui.QPen(color(self._base_color(), 90), 1))
        painter.setBrush(color(self._base_color(), 30))
        painter.drawRoundedRect(rect, 12, 12)
        x = 12.0
        if self._dot:
            glow = 0.35 + 0.30 * (0.5 + 0.5 * math.sin(self._phase))
            center = QtCore.QPointF(x + 3.5, rect.center().y())
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color(self._base_color(), int(70 * glow)))
            painter.drawEllipse(center, 7.0, 7.0)
            painter.setBrush(base)
            painter.drawEllipse(center, 3.2, 3.2)
            x += 14.0
        painter.setPen(base)
        painter.setFont(ui_font(8.5, 700, spacing=110))
        painter.drawText(QtCore.QRectF(x, 0, rect.width() - x - 10, rect.height()),
                         QtCore.Qt.AlignmentFlag.AlignVCenter, self._text.upper())
        painter.end()


# ---------------------------------------------------------------------------
# sparkline & progress track
# ---------------------------------------------------------------------------

class Sparkline(QtWidgets.QWidget):
    """Tiny area chart used inside KPI cards."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._data: list[float] = []
        self._tone = theme.GOOD
        self.setFixedSize(74, 26)

    def set_data(self, data: list[float], tone: str = theme.GOOD) -> None:
        self._data = list(data[-48:])
        self._tone = tone
        self.update()

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if len(self._data) < 2:
            painter.end()
            return
        base = color(theme.tone_color(self._tone))
        w, h = self.width(), self.height()
        lo, hi = min(self._data), max(self._data)
        span = (hi - lo) or 1.0
        pad = 3.0
        step = (w - 2 * pad) / (len(self._data) - 1)
        points = [QtCore.QPointF(pad + i * step,
                                 h - pad - (v - lo) / span * (h - 2 * pad))
                  for i, v in enumerate(self._data)]
        path = QtGui.QPainterPath(points[0])
        for p in points[1:]:
            path.lineTo(p)
        fill = QtGui.QPainterPath(path)
        fill.lineTo(points[-1].x(), h)
        fill.lineTo(points[0].x(), h)
        fill.closeSubpath()
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, color(theme.tone_color(self._tone), 80))
        grad.setColorAt(1.0, color(theme.tone_color(self._tone), 0))
        painter.fillPath(fill, QtGui.QBrush(grad))
        painter.setPen(QtGui.QPen(base, 1.4, QtCore.Qt.PenStyle.SolidLine,
                                  QtCore.Qt.PenCapStyle.RoundCap,
                                  QtCore.Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(base)
        painter.drawEllipse(points[-1], 2.2, 2.2)
        painter.end()


class ProgressTrack(QtWidgets.QWidget):
    """Rounded 0-100% track with gradient fill (basket vs target, drawdown...)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None,
                 height: int = 8) -> None:
        super().__init__(parent)
        self._progress = 0.0
        self._tone = theme.GOOD
        self.setFixedHeight(height)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)

    def set_progress(self, ratio: float, tone: str = theme.GOOD) -> None:
        self._progress = max(0.0, min(1.0, ratio))
        self._tone = tone
        self.update()

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        radius = rect.height() / 2
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color("#1B2432"))
        painter.drawRoundedRect(rect, radius, radius)
        if self._progress > 0.004:
            fill = QtCore.QRectF(rect.x(), rect.y(),
                                 rect.width() * self._progress, rect.height())
            grad = QtGui.QLinearGradient(rect.left(), 0, rect.right(), 0)
            grad.setColorAt(0.0, color(theme.ACCENT_DEEP))
            grad.setColorAt(1.0, color(theme.tone_color(self._tone)))
            painter.setBrush(QtGui.QBrush(grad))
            painter.drawRoundedRect(fill, radius, radius)
        painter.end()


# ---------------------------------------------------------------------------
# confidence gauge
# ---------------------------------------------------------------------------

class ConfidenceGauge(QtWidgets.QWidget):
    """270° arc gauge for the AI confidence score (0-100)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._threshold = 85.0
        self.setFixedSize(132, 108)

    def set_value(self, value: float, threshold: float = 85.0) -> None:
        self._value = max(0.0, min(100.0, value))
        self._threshold = threshold
        self.update()

    def _tone(self) -> str:
        if self._value >= self._threshold:
            return theme.GOOD
        if self._value >= 60.0:
            return theme.WARN_TONE
        return theme.BAD

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pad = 10.0
        rect = QtCore.QRectF(self.rect()).adjusted(pad, pad, -pad, -pad + 14)
        start = 225 * 16
        full = -270 * 16
        painter.setPen(QtGui.QPen(color("#1B2432"), 9, QtCore.Qt.PenStyle.SolidLine,
                                  QtCore.Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, start, full)
        # The value arc sweeps clockwise from 225°, i.e. against the conic
        # gradient's direction, so the ramp is laid out reversed: the arc tip
        # (high confidence) lands on mint, the tail on red.
        grad = QtGui.QConicalGradient(rect.center(), 225.0)
        grad.setColorAt(0.00, color(theme.LOSS))
        grad.setColorAt(0.25, color(theme.ACCENT))
        grad.setColorAt(0.50, color(theme.ACCENT_DEEP))
        grad.setColorAt(0.75, color(theme.WARN))
        grad.setColorAt(1.00, color(theme.LOSS))
        span = full * (self._value / 100.0)
        if span < -1:
            painter.setPen(QtGui.QPen(QtGui.QBrush(grad), 9,
                                      QtCore.Qt.PenStyle.SolidLine,
                                      QtCore.Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, start, int(span))
        # threshold tick
        angle = math.radians(225 - 270 * (self._threshold / 100.0))
        c = rect.center()
        r_out = rect.width() / 2 + 5
        r_in = rect.width() / 2 - 5
        painter.setPen(QtGui.QPen(color(theme.TEXT, 110), 1.6))
        painter.drawLine(QtCore.QPointF(c.x() + r_in * math.cos(angle),
                                        c.y() - r_in * math.sin(angle)),
                         QtCore.QPointF(c.x() + r_out * math.cos(angle),
                                        c.y() - r_out * math.sin(angle)))
        # value text
        painter.setPen(color(theme.tone_color(self._tone)))
        painter.setFont(ui_font(21, 700))
        painter.drawText(QtCore.QRectF(0, rect.center().y() - 20,
                                       self.width(), 30),
                         QtCore.Qt.AlignmentFlag.AlignCenter,
                         f"{self._value:.0f}")
        painter.setPen(color(theme.FAINT))
        painter.setFont(ui_font(7.5, 600, spacing=118))
        painter.drawText(QtCore.QRectF(0, rect.center().y() + 8,
                                       self.width(), 14),
                         QtCore.Qt.AlignmentFlag.AlignCenter, "CONFIDENCE / 100")
        painter.end()


# ---------------------------------------------------------------------------
# stat card
# ---------------------------------------------------------------------------

class StatCard(QtWidgets.QFrame):
    """KPI tile: micro title, big value, caption and an optional side widget."""

    def __init__(self, title: str, side: Optional[QtWidgets.QWidget] = None,
                 parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        self.title = QtWidgets.QLabel(title.upper())
        self.title.setObjectName("cardTitle")
        self.title.setFont(ui_font(8, 700, spacing=116))
        head.addWidget(self.title)
        head.addStretch(1)
        self.side = side
        if side is not None:
            head.addWidget(side)
        layout.addLayout(head)
        self.value = QtWidgets.QLabel("--")
        self.value.setObjectName("cardValue")
        self.value.setFont(ui_font(19, 700))
        layout.addWidget(self.value)
        self.sub = QtWidgets.QLabel("")
        self.sub.setObjectName("cardSub")
        self.sub.setFont(ui_font(8.5, 500))
        layout.addWidget(self.sub)
        self.setMinimumHeight(96)

    def set_value(self, text: str, tone: str = theme.NEUTRAL) -> None:
        self.value.setText(text)
        self.value.setStyleSheet(
            f"color: {theme.tone_color(tone) if tone != theme.NEUTRAL else theme.TEXT};")

    def set_sub(self, text: str, tone: str = theme.NEUTRAL) -> None:
        self.sub.setText(text)
        self.sub.setStyleSheet(f"color: {theme.tone_color(tone) if tone != theme.NEUTRAL else theme.FAINT};")


class ReasonList(QtWidgets.QWidget):
    """Painted list of AI reasoning bullets with hairline separators.

    Qt rich-text CSS is too limited for the row styling we want, so the list
    is painted directly: coloured dot + elided line + full text as tooltip.
    """

    ROW = 30

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: list[tuple[str, str]] = []
        self.setMouseTracking(True)

    def set_lines(self, rows: list[tuple[str, str]]) -> None:
        self._rows = rows
        self.setToolTip("\n".join(text for _, text in rows))
        self.setMinimumHeight(max(1, len(rows)) * self.ROW + 6)
        self.update()

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        font = ui_font(9.5, 500)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        for index, (tone, text) in enumerate(self._rows):
            top = index * self.ROW
            if index:
                painter.setPen(color(theme.BORDER_SOFT))
                painter.drawLine(QtCore.QPointF(0, top + 0.5),
                                 QtCore.QPointF(self.width(), top + 0.5))
            center_y = top + self.ROW / 2
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color(tone))
            painter.drawEllipse(QtCore.QPointF(5.0, center_y), 3.0, 3.0)
            painter.setPen(color(theme.TEXT))
            elided = metrics.elidedText(
                text, QtCore.Qt.TextElideMode.ElideRight, self.width() - 26)
            painter.drawText(QtCore.QRectF(18, top, self.width() - 26, self.ROW),
                             QtCore.Qt.AlignmentFlag.AlignVCenter, elided)
        painter.end()


class BrandMark(QtWidgets.QWidget):
    """Rounded mint square with the ZeroTrace crosshair glyph."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(38, 38)

    def paintEvent(self, _: Optional[QtGui.QPaintEvent]) -> None:  # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        grad = QtGui.QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0.0, color(theme.ACCENT))
        grad.setColorAt(1.0, color(theme.ACCENT_DEEP))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(grad))
        p.drawRoundedRect(rect, 11, 11)
        # crosshair / trace glyph
        c = rect.center()
        p.setPen(QtGui.QPen(color("#06281F"), 2.2, QtCore.Qt.PenStyle.SolidLine,
                            QtCore.Qt.PenCapStyle.RoundCap))
        p.drawEllipse(c, 6.5, 6.5)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            p.drawLine(QtCore.QPointF(c.x() + dx * 9.5, c.y() + dy * 9.5),
                       QtCore.QPointF(c.x() + dx * 13.0, c.y() + dy * 13.0))
        p.setBrush(color("#06281F"))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.drawEllipse(c, 2.2, 2.2)
        p.end()


def table_pill_item(text: str, tone: str) -> QtWidgets.QTableWidgetItem:
    """Centred, tinted table cell used for BUY/SELL badges."""
    item = QtWidgets.QTableWidgetItem(text)
    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    item.setForeground(color(theme.tone_color(tone)))
    item.setBackground(color(theme.tone_color(tone), 26))
    font = ui_font(8.5, 700, spacing=108)
    item.setFont(font)
    return item


def numeric_item(text: str, tone: str = theme.NEUTRAL,
                 mono: bool = True) -> QtWidgets.QTableWidgetItem:
    item = QtWidgets.QTableWidgetItem(text)
    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight |
                          QtCore.Qt.AlignmentFlag.AlignVCenter)
    if tone != theme.NEUTRAL:
        item.setForeground(color(theme.tone_color(tone)))
    if mono:
        item.setFont(ui_font(9, 500, mono=True))
    return item


def text_item(text: str, tone: str = theme.NEUTRAL, bold: bool = False,
              mono: bool = False) -> QtWidgets.QTableWidgetItem:
    item = QtWidgets.QTableWidgetItem(text)
    if tone != theme.NEUTRAL:
        item.setForeground(color(theme.tone_color(tone)))
    if mono:
        item.setFont(ui_font(9, 500, mono=True))
    elif bold:
        item.setFont(ui_font(9, 700))
    return item


def apply_typography(widget: QtWidgets.QWidget) -> None:
    """Set the window-wide default font from the theme stack."""
    widget.setFont(ui_font(9.5, 500))


def icon_path() -> Optional[str]:
    """Absolute path to the repo window icon, if present."""
    import os
    candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "assets", "icon.png")
    return candidate if os.path.exists(candidate) else None
