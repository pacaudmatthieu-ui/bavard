"""Floating recording indicator: a small rounded panel with a Matrix-style
digital-rain waveform (green 0/1 columns on near-black), shown while the
push-to-talk chord is held. After recording it switches to a spinner until
the text is injected. Pure AppKit via pyobjc."""
import collections
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

BAR_COUNT = 24
PANEL_W, PANEL_H = 260, 74
LABEL_H = 20   # bottom strip reserved for the app-name label
CHAR_H = 9     # height of one Matrix glyph row
# half-width katakana + digits, like the film's digital rain
MATRIX_CHARS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜﾝ0123456789"
MAX_ROWS = 6   # max glyphs per column in the wave area


def _green(r, g, bl, a):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, bl, a)


class WaveView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(WaveView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.levels = collections.deque([0.02] * BAR_COUNT, maxlen=BAR_COUNT)
        self.mode = "wave"  # wave (recording) | processing (STT + LLM running)
        self.phase = 0.0    # spinner rotation phase
        # per-column glyph grid; a few cells mutate each tick for the rain effect
        self.grid = [
            [random.choice(MATRIX_CHARS) for _ in range(MAX_ROWS)]
            for _ in range(BAR_COUNT)
        ]
        self._font = NSFont.fontWithName_size_("Menlo-Bold", CHAR_H) or \
            NSFont.boldSystemFontOfSize_(CHAR_H)
        return self

    def mutate_grid(self):
        for _ in range(8):
            self.grid[random.randrange(BAR_COUNT)][random.randrange(MAX_ROWS)] = \
                random.choice(MATRIX_CHARS)

    def drawRect_(self, rect):
        b = self.bounds()
        # near-black background with a faint green tint (Matrix terminal)
        _green(0.01, 0.05, 0.02, 0.94).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 16, 16).fill()
        wave_h = b.size.height - LABEL_H
        if self.mode == "processing":
            # spinner: 12 green dots on a ring, brightness trailing the head
            cx, cy = b.size.width / 2, LABEL_H + wave_h / 2
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
            # digital-rain waveform: columns of green 0/1, height follows the
            # audio level, brightest glyph at the head (top), dimmer below
            pad = 16
            col_w = (b.size.width - 2 * pad) / BAR_COUNT
            for i, lv in enumerate(self.levels):
                n = max(1, int(round(min(1.0, lv * 10) * MAX_ROWS)))
                x = pad + i * col_w
                y0 = LABEL_H + (wave_h - n * CHAR_H) / 2
                for r in range(n):
                    t = r / (n - 1) if n > 1 else 1.0
                    if r == n - 1:
                        color = _green(0.75, 1.0, 0.8, 1.0)   # glowing head
                    else:
                        color = _green(0.2, 0.9, 0.35, 0.25 + 0.6 * t)
                    attrs = {
                        NSFontAttributeName: self._font,
                        NSForegroundColorAttributeName: color,
                    }
                    NSString.stringWithString_(self.grid[i][r]).drawAtPoint_withAttributes_(
                        (x, y0 + r * CHAR_H), attrs
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
            ((0, 4), (b.size.width, 14)), attrs
        )


class Overlay:
    """show()/hide() must be called on the main thread (use AppHelper.callAfter)."""

    def __init__(self, level_fn):
        self.level_fn = level_fn
        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - PANEL_W) / 2
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            ((x, 110), (PANEL_W, PANEL_H)),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        self.panel.setLevel_(25)  # above normal windows (status level)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setIgnoresMouseEvents_(True)
        self.panel.setCollectionBehavior_(1)  # visible on all Spaces
        self.view = WaveView.alloc().initWithFrame_(((0, 0), (PANEL_W, PANEL_H)))
        self.panel.setContentView_(self.view)
        self._timer = None

    def _tick(self, _timer):
        if self.view.mode == "processing":
            self.view.phase += 0.35  # spinner speed
        else:
            self.view.levels.append(self.level_fn())
            self.view.mutate_grid()  # keep the digital rain alive
        self.view.setNeedsDisplay_(True)

    def show(self):
        self.view.mode = "wave"
        self.view.levels.extend([0.02] * BAR_COUNT)
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
