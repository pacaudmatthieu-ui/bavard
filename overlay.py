"""Floating recording indicator: a small rounded panel with a live waveform,
shown while the push-to-talk chord is held. After recording it switches to a
spinner until the text is injected. Pure AppKit via pyobjc."""
import collections
import math

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
LABEL_H = 20  # bottom strip reserved for the "VoiceBud" label


class WaveView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(WaveView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.levels = collections.deque([0.02] * BAR_COUNT, maxlen=BAR_COUNT)
        self.mode = "wave"  # wave (recording) | processing (STT + LLM running)
        self.phase = 0.0    # spinner rotation phase
        return self

    def drawRect_(self, rect):
        b = self.bounds()
        # black rounded background (high alpha for readability)
        NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.92).setFill()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 16, 16).fill()
        wave_h = b.size.height - LABEL_H
        if self.mode == "processing":
            # spinner: 12 purple dots on a ring, brightness trailing the head
            cx, cy = b.size.width / 2, LABEL_H + wave_h / 2
            ring_r, dot_r = 13, 3
            for i in range(12):
                angle = i * math.pi * 2 / 12
                trail = ((self.phase - i) % 12) / 12
                NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.64, 0.42, 1.0, 0.15 + 0.85 * (1 - trail)
                ).setFill()
                x = cx + ring_r * math.cos(-angle) - dot_r
                y = cy + ring_r * math.sin(-angle) - dot_r
                NSBezierPath.bezierPathWithOvalInRect_(
                    ((x, y), (dot_r * 2, dot_r * 2))
                ).fill()
        else:
            # purple waveform bars, drawn above the label strip
            pad, gap = 16, 3
            bw = (b.size.width - 2 * pad - gap * (BAR_COUNT - 1)) / BAR_COUNT
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.64, 0.42, 1.0, 1.0).setFill()
            for i, lv in enumerate(self.levels):
                bh = max(4, min(1.0, lv * 10) * (wave_h - 18))
                x = pad + i * (bw + gap)
                y = LABEL_H + (wave_h - bh) / 2
                NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    ((x, y), (bw, bh)), bw / 2, bw / 2
                ).fill()
        # label — white, centered at the bottom
        style = NSMutableParagraphStyle.alloc().init()
        style.setAlignment_(1)  # center
        attrs = {
            NSFontAttributeName: NSFont.boldSystemFontOfSize_(11),
            NSForegroundColorAttributeName: NSColor.whiteColor(),
            NSParagraphStyleAttributeName: style,
        }
        label = "Traitement…" if self.mode == "processing" else "VoiceBud"
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
