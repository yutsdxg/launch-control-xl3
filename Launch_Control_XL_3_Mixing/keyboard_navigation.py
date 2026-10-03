"""Encoder gestures for discrete keyboard navigation; no queued repeats."""

from time import monotonic

from .jxa_keyboard import JxaKeyboardSender

# Tune these after checking small, slow and fast turns on the hardware.
# Every gesture's first input and every direction change always press once.
REPEAT_INPUTS_PER_PRESS = 1
MIN_PRESS_INTERVAL = 0.0  # Seconds, applied only to continued turns.
GESTURE_GAP = 0.25  # Seconds without input before a new gesture.
INPUT_MAX_AGE = JxaKeyboardSender.PRESS_TTL


class EncoderKeyboardNavigation:
    def __init__(
        self,
        sender=None,
        clock=None,
        inputs_per_press=REPEAT_INPUTS_PER_PRESS,
        min_press_interval=MIN_PRESS_INTERVAL,
        gesture_gap=GESTURE_GAP,
    ):
        self._sender = sender if sender is not None else JxaKeyboardSender()
        self._clock = clock if clock is not None else monotonic
        self._inputs_per_press = max(1, int(inputs_per_press))
        self._min_press_interval = max(0.0, float(min_press_interval))
        self._gesture_gap = max(0.001, float(gesture_gap))
        self._focus_epoch = self._sender.focus_epoch
        self.reset(cancel=False)

    def start(self):
        return self._sender.start()

    def close(self):
        self.reset()
        self._sender.close()

    def reset(self, cancel=True):
        if cancel:
            self._sender.cancel()
        self._direction = None
        self._last_input_time = None
        self._last_press_time = None
        self._inputs = 0
        self.last_action = ""

    def poll(self):
        """Observe focus/idle transitions without ever generating a key."""
        frontmost = self._sender.is_frontmost()
        epoch = self._sender.focus_epoch
        if epoch != self._focus_epoch:
            self._focus_epoch = epoch
            self.reset()
        if not frontmost:
            self.reset()
            return False
        if (
            self._last_input_time is not None
            and self._clock() - self._last_input_time >= self._gesture_gap
        ):
            self.reset()
        return True

    def receive_value(self, value):
        received_at = self._clock()
        if type(value) is not int or not 0 <= value <= 127 or value == 64:
            return False
        if not self.poll():
            return False
        direction = -1 if value < 64 else 1
        now = self._clock()
        if now - received_at >= INPUT_MAX_AGE:
            self.reset(cancel=False)
            return False
        first_input = self._last_input_time is None or direction != self._direction
        self._last_input_time = now
        self._direction = direction
        if not first_input:
            self._inputs += 1
            if self._inputs < self._inputs_per_press:
                return False
            if now - self._last_press_time < self._min_press_interval:
                return False
        if not self._sender.press(direction, at=received_at):
            # Busy/expired input is dropped; do not cancel the earlier press
            # that is still in flight merely because another input arrived.
            self.reset(cancel=False)
            return False
        self._inputs = 0
        self._last_press_time = now
        self.last_action = "Up" if direction < 0 else "Down"
        return True
