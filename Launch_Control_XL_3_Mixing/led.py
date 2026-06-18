from . import midi


class LedSender:
    def __init__(self, midi_sender=None):
        self._midi_sender = midi_sender
        self._last_messages = {}

    def set_midi_sender(self, midi_sender):
        self._midi_sender = midi_sender

    def send_rgb(self, control, rgb, control_index=None, force=False):
        index = control_index if control_index is not None else self._control_index(control)
        if index is None:
            return False
        message = midi.make_rgb_led_message(index, rgb)
        if not force and self._last_messages.get(index) == message:
            return True
        sender = self._midi_sender or getattr(control, "send_midi", None)
        if sender is None:
            return False
        try:
            sender(message)
        except RuntimeError:
            return False
        self._last_messages[index] = message
        return True

    def forget(self, control, control_index=None):
        index = control_index if control_index is not None else self._control_index(control)
        if index is not None:
            self._last_messages.pop(index, None)

    def _control_index(self, control):
        try:
            return control.message_identifier()
        except (AttributeError, RuntimeError):
            return None
