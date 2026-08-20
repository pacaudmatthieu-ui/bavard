"""Floating recording indicator: a small rounded panel with a Matrix-style
digital-rain waveform (green 0/1 columns on near-black), shown while the
push-to-talk chord is held. After recording it switches to a spinner until
the text is injected. Pure AppKit via pyobjc.

Under the label sits a row of mode chips — the same setting as the menu bar's
mode picker, within reach while you speak. Clicking one must NOT move the
keyboard focus: the panel is a non-activating panel and answers first mouse,
so the app you are dictating into stays focused and still receives the paste.
"""
import math
import random

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMutableParagraphStyle,
    NSPanel,
    NSParagraphStyleAttributeName,
    NSScreen,
    NSTimer,
    NSView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSString

from modes import AUTO as AUTO_KEY

BAR_COUNT = 36
PANEL_W, PANEL_H = 260, 74
LABEL_H = 20   # strip reserved for the app-name label
MODE_H = 26    # strip below it, for the mode chips (0 when modes are off)
CHIP_W, CHIP_H = 52, 18
CHAR_H = 7     # height of one Matrix glyph row
# half-width katakana + digits, like the film's digital rain
MATRIX_CHARS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"
MAX_ROWS = 7   # max glyphs per column in the wave area


def _green(r, g, bl, a):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, bl, a)


class WaveView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(WaveView, self).initWithFrame_(frame)
        if self is None:
            return None
        # fixed equalizer: one level per column (bass left, treble right)
        self.cols = [0.0] * BAR_COUNT
        self.mode = "wave"  # wave (recording) | processing (STT + LLM running)
        self.phase = 0.0    # spinner rotation phase
        self.chips = []     # [(mode_key, short_label)], empty = no chip strip
        self.active = None  # the pinned setting (a mode key, or "auto")
        self.detected = None  # what automatic mode picks for the app in front
        self.on_pick = None  # called with the clicked mode key
        # per-column glyph grid; rows scroll downward for the falling-rain effect
        self.grid = [
            [random.choice(MATRIX_CHARS) for _ in range(MAX_ROWS)]
            for _ in range(BAR_COUNT)
        ]
        self._font = NSFont.fontWithName_size_("Menlo-Bold", CHAR_H) or \
            NSFont.boldSystemFontOfSize_(CHAR_H)
        self._chip_font = NSFont.fontWithName_size_("Menlo-Bold", 9) or \
            NSFont.boldSystemFontOfSize_(9)
        return self

    @objc.python_method
    def chip_height(self):
        return MODE_H if self.chips else 0

    @objc.python_method
    def chip_rects(self):
        """One rect per chip, laid out in a centered row. Single source of
        truth for both drawing and hit-testing."""
        if not self.chips:
            return []
        total = CHIP_W * len(self.chips)
        x0 = (self.bounds().size.width - total) / 2
        y = (MODE_H - CHIP_H) / 2
        return [(key, short, ((x0 + i * CHIP_W, y), (CHIP_W - 3, CHIP_H)))
                for i, (key, short) in enumerate(self.chips)]

    @objc.python_method
    def draw_chips(self):
        for key, short, rect in self.chip_rects():
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, 7, 7)
            if key == self.active:
                _green(0.25, 0.85, 0.4, 0.85).setFill()   # the pinned choice
                path.fill()
                text_color = _green(0.02, 0.12, 0.04, 1.0)
            else:
                _green(0.2, 0.6, 0.3, 0.13).setFill()
                path.fill()
                if self.active == AUTO_KEY and key == self.detected:
                    # automatic is on: outline what it resolves to right now
                    _green(0.4, 1.0, 0.55, 0.75).setStroke()
                    path.setLineWidth_(1.0)
                    path.stroke()
                text_color = _green(0.5, 1.0, 0.65, 0.85)
            style = NSMutableParagraphStyle.alloc().init()
            style.setAlignment_(1)
            attrs = {
                NSFontAttributeName: self._chip_font,
                NSForegroundColorAttributeName: text_color,
                NSParagraphStyleAttributeName: style,
            }
            (origin, size) = rect
            NSString.stringWithString_(short).drawInRect_withAttributes_(
                ((origin[0], origin[1] + 4), (size[0], CHIP_H - 4)), attrs)

    # Clicks must work while another app is active (Bavard never is), and must
    # not activate Bavard — hence acceptsFirstMouse + the non-activating panel.
    def acceptsFirstMouse_(self, event):
        return True

    def mouseDown_(self, event):
        point = self.convertPoint_fromView_(event.locationInWindow(), None)
        for key, _short, ((x, y), (w, h)) in self.chip_rects():
            if x <= point.x <= x + w and y <= point.y <= y + h:
                if self.on_pick is not None:
                    self.on_pick(key)
                return

    def scroll_grid(self):
        """Shift every column's glyphs one row toward the bottom (Matrix rain)."""
        for col in self.grid:
            col.pop(0)
            col.append(random.choice(MATRIX_CHARS))
        for _ in range(8):
            self.grid[random.randrange(BAR_COUNT)][random.randrange(MAX_ROWS)] = \
                random.choice(MATRIX_CHARS)

    def drawRect_(self, rect):
        b = self.bounds()
        # near-black background with a faint green tint (Matrix terminal)
        _green(0.01, 0.05, 0.02, 0.94).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 16, 16).fill()
        # bottom-up: chip strip, then the label, then the wave area
        mode_h = self.chip_height()
        wave_h = b.size.height - LABEL_H - mode_h
        if self.mode == "processing":
            # spinner: 12 green dots on a ring, brightness trailing the head
            cx, cy = b.size.width / 2, mode_h + LABEL_H + wave_h / 2
            ring_r, dot_r = 13, 3
            for i in range(12):
                angle = i * math.pi * 2 / 12
                trail = ((self.phase - i) % 12) / 12
                _green(0.25, 1.0, 0.45, 0.15 + 0.85 * (1 - trail)).setFill()
                x = cx + ring_r * math.cos(-angle) - dot_r
                y = cy + ring_r * math.sin(-angle) - dot_r
                NSBezierPath.bezierPathWithOvalInRect_(
                    ((x, y), (dot_r * 2, dot_r * 2))
                ).fill()
        else:
            # fixed equalizer: each column sits at its own frequency band and
            # rises from the bottom with that band's energy; glyphs inside
            # stream downward like the film's digital rain
            pad = 16
            col_w = (b.size.width - 2 * pad) / BAR_COUNT
            base = mode_h + LABEL_H + 2
            for i, lv in enumerate(self.cols):
                n = max(1, int(round(min(1.0, lv) * MAX_ROWS)))
                x = pad + i * col_w
                for r in range(n):
                    t = r / (n - 1) if n > 1 else 1.0
                    if r == n - 1 and n > 1:
                        color = _green(0.75, 1.0, 0.8, 1.0)   # glowing tip
                    else:
                        color = _green(0.2, 0.9, 0.35, 0.25 + 0.6 * t)
                    attrs = {
                        NSFontAttributeName: self._font,
                        NSForegroundColorAttributeName: color,
                    }
                    NSString.stringWithString_(self.grid[i][r]).drawAtPoint_withAttributes_(
                        (x, base + r * CHAR_H), attrs
                    )
        # label — Matrix green, centered at the bottom
        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(1)  # center
        attrs = {
            NSFontAttributeName: self._font.fontWithSize_(11) if hasattr(self._font, "fontWithSize_") else NSFont.boldSystemFontOfSize_(11),
            NSForegroundColorAttributeName: _green(0.45, 1.0, 0.6, 0.9),
            NSParagraphStyleAttributeName: style,
        }
        label = "Traitement…" if self.mode == "processing" else "Bavard"
        NSString.stringWithString_(label).drawInRect_withAttributes_(
            ((0, mode_h + 4), (b.size.width, 14)), attrs
        )
        self.draw_chips()


class Overlay:
    """show()/hide() must be called on the main thread (use AppHelper.callAfter)."""

    def __init__(self, bands_fn, chips=(), on_pick=None):
        """chips: [(mode_key, short_label)] for the picker row, () to hide it.
        on_pick(key) is called on the main thread when one is clicked."""
        self.bands_fn = bands_fn   # bands_fn(n) -> n raw band magnitudes
        self._peak = 0.5           # adaptive normalization reference
        self._frame = 0
        chips = list(chips)
        width = max(PANEL_W, CHIP_W * len(chips) + 24) if chips else PANEL_W
        height = PANEL_H + (MODE_H if chips else 0)
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - width) / 2
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, 110), (width, height)),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        self.panel.setLevel_(25)  # above normal windows (status level)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        # clickable only when there is something to click; a non-activating
        # panel that never becomes key, so the app being dictated into keeps
        # the keyboard focus and still receives the paste
        self.panel.setIgnoresMouseEvents_(not chips)
        self.panel.setBecomesKeyOnlyIfNeeded_(True)
        self.panel.setCollectionBehavior_(1)  # visible on all Spaces
        self.view = WaveView.alloc().initWithFrame_(((0, 0), (width, height)))
        self.view.chips = chips
        self.view.on_pick = on_pick
        self.panel.setContentView_(self.view)
        self._timer = None

    def set_mode_state(self, active, detected):
        """Which chip is pinned, and what automatic resolves to right now."""
        self.view.active = active
        self.view.detected = detected
        self.view.setNeedsDisplay_(True)

    def _tick(self, _timer):
        if self.view.mode == "processing":
            self.view.phase += 0.35  # spinner speed
        else:
            raw = self.bands_fn(BAR_COUNT)
            # adaptive peak with slow decay so quiet and loud voices both fill
            self._peak = max(0.3, self._peak * 0.99, max(raw))
            for i, v in enumerate(raw):
                target = min(1.0, v / self._peak)
                # fast attack, slow decay — columns jump up then fall smoothly
                self.view.cols[i] = max(target, self.view.cols[i] * 0.78)
            self._frame += 1
            if self._frame % 2 == 0:
                self.view.scroll_grid()  # glyphs fall one row, ~15 rows/s
        self.view.setNeedsDisplay_(True)

    def show(self):
        self.view.mode = "wave"
        self.view.cols = [0.0] * BAR_COUNT
        self._peak = 0.5
        self.panel.orderFrontRegardless()
        self._timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1 / 30.0, True, self._tick
        )

    def processing(self):
        """Keep the panel up with a spinner while STT + cleanup run."""
        self.view.mode = "processing"
        self.view.phase = 0.0
        self.view.setNeedsDisplay_(True)

    def hide(self):
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
        self.panel.orderOut_(None)
