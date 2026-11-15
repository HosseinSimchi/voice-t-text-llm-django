"""Right-to-left text layout for ReportLab.

ReportLab has no complete bidi/shaping support, so this module:

1. shapes Arabic-script letters into their contextual forms (arabic-reshaper),
2. breaks lines in *logical* order while measuring the shaped width,
3. reorders each finished line to *visual* order (python-bidi), and
4. draws it right-aligned.

Breaking lines before reordering is essential: reordering a whole paragraph and
then wrapping it would put the lines of a multi-line paragraph in reverse order.
"""

from __future__ import annotations

import re
import unicodedata

import arabic_reshaper
from reportlab.lib.colors import Color, black
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable

try:  # python-bidi >= 0.5
    from bidi import get_display
except ImportError:  # pragma: no cover
    from bidi.algorithm import get_display

_RESHAPER = arabic_reshaper.ArabicReshaper(configuration={"delete_harakat": False, "support_ligatures": True})
_WS = re.compile(r"\s+")


def is_rtl(text: str) -> bool:
    """True when the first strong directional character is right-to-left."""
    for ch in text:
        bidi = unicodedata.bidirectional(ch)
        if bidi in ("R", "AL"):
            return True
        if bidi == "L":
            return False
    return False


def shape(text: str) -> str:
    return _RESHAPER.reshape(text)


def visual(line: str, rtl: bool) -> str:
    """Shape and reorder one already-broken line for drawing."""
    return get_display(shape(line), base_dir="R" if rtl else "L")


def break_lines(text: str, font: str, size: float, width: float) -> list[str]:
    """Greedy line breaking in logical order, measuring shaped glyph widths."""
    words = _WS.split(text.strip())
    lines: list[str] = []
    current = ""
    for word in words:
        if not word:
            continue
        candidate = f"{current} {word}" if current else word
        if stringWidth(shape(candidate), font, size) <= width or not current:
            if not current and stringWidth(shape(word), font, size) > width:
                lines.extend(_hard_break(word, font, size, width))
                continue
            current = candidate
        else:
            lines.append(current)
            if stringWidth(shape(word), font, size) > width:
                pieces = _hard_break(word, font, size, width)
                lines.extend(pieces[:-1])
                current = pieces[-1]
            else:
                current = word
    if current:
        lines.append(current)
    return lines


def _hard_break(word: str, font: str, size: float, width: float) -> list[str]:
    pieces, buf = [], ""
    for ch in word:
        if buf and stringWidth(shape(buf + ch), font, size) > width:
            pieces.append(buf)
            buf = ch
        else:
            buf += ch
    if buf:
        pieces.append(buf)
    return pieces


class BidiParagraph(Flowable):
    """A wrapped paragraph that supports RTL and LTR text and page splitting."""

    def __init__(self, text: str, font: str, size: float, leading: float, *, color: Color = black,
                 rtl: bool | None = None, space_before: float = 0, space_after: float = 4,
                 indent: float = 0, align_right: bool | None = None, _lines: list[str] | None = None):
        super().__init__()
        self.text = unicodedata.normalize("NFC", text or "")
        self.font, self.size, self.leading = font, size, leading
        self.color = color
        self.rtl = is_rtl(self.text) if rtl is None else rtl
        self.space_before, self.space_after = space_before, space_after
        self.indent = indent
        self.align_right = self.rtl if align_right is None else align_right
        self._lines = _lines
        self._width = 0.0

    def wrap(self, avail_width, avail_height):
        self._width = avail_width
        if self._lines is None:
            self._lines = []
            for para in self.text.split("\n"):
                self._lines.extend(break_lines(para, self.font, self.size, avail_width - self.indent) or [""])
        return avail_width, len(self._lines) * self.leading

    def split(self, avail_width, avail_height):
        self.wrap(avail_width, avail_height)
        fit = int(avail_height // self.leading)
        if fit <= 0 or fit >= len(self._lines):
            return [] if fit <= 0 else [self]
        common = dict(color=self.color, rtl=self.rtl, indent=self.indent, align_right=self.align_right)
        first = BidiParagraph(self.text, self.font, self.size, self.leading, space_before=self.space_before,
                              space_after=0, _lines=self._lines[:fit], **common)
        rest = BidiParagraph(self.text, self.font, self.size, self.leading, space_before=0,
                             space_after=self.space_after, _lines=self._lines[fit:], **common)
        return [first, rest]

    def getSpaceBefore(self):
        return self.space_before

    def getSpaceAfter(self):
        return self.space_after

    def draw(self):
        canvas = self.canv
        canvas.setFont(self.font, self.size)
        canvas.setFillColor(self.color)
        y = len(self._lines) * self.leading - self.size
        for line in self._lines:
            shown = visual(line, self.rtl)
            if self.align_right:
                canvas.drawRightString(self._width - self.indent, y, shown)
            else:
                canvas.drawString(self.indent, y, shown)
            y -= self.leading
