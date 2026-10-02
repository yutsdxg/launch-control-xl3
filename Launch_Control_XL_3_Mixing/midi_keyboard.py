"""Discrete preset navigation via Bome; all channels here are zero based."""

import logging

CHANNEL = 15
NAVIGATION_CC = 119
FOCUS_CC = 118
UP_VALUE = 1
DOWN_VALUE = 2
FOCUS_QUERY_VALUE = 0
LOGGER = logging.getLogger(__name__)


class MidiKeyboardSender:
    def __init__(self, midi_sender=None):
        self._midi_sender = midi_sender
        self._frontmost = False
        self._send_failed = False

    def set_midi_sender(self, midi_sender):
        self._midi_sender = midi_sender
        self._frontmost = False
        self._send_failed = False

    def set_focus(self, value):
        if value not in (0, 1):
            return False
        frontmost = value == 1
        changed = self._frontmost != frontmost
        self._frontmost = frontmost
        if changed:
            LOGGER.info("LCXL3 Bome keyboard navigation: Live frontmost=%s", frontmost)
        return changed

    def is_frontmost(self):
        return self._midi_sender is not None and self._frontmost

    def request_focus(self):
        self._frontmost = False
        return self._send(FOCUS_QUERY_VALUE)

    def press(self, direction):
        if not self.is_frontmost() or direction not in (-1, 1):
            return False
        return self._send(UP_VALUE if direction < 0 else DOWN_VALUE)

    def _send(self, value):
        if self._midi_sender is None:
            return False
        try:
            # ControlSurface's callback may return None on successful delivery.
            sent = self._midi_sender((0xB0 | CHANNEL, NAVIGATION_CC, value))
            if sent is False:
                raise RuntimeError("MIDI output unavailable")
        except Exception as error:
            self._frontmost = False
            if not self._send_failed:
                LOGGER.warning("LCXL3 Bome keyboard navigation: MIDI send failed: %s", error)
            self._send_failed = True
            return False
        self._send_failed = False
        return True
