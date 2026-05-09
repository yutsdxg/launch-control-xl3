from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from . import midi
from .colors import Rgb

LED_FEEDBACK_UPDATE_INTERVAL = 0.1
RGB_LED_SYSEX_PREFIX = midi.SYSEX_HEADER + (1, 83)
BUTTON_CONTROL_INDICES = {
    "solo": 65,
    "track_on": 66,
}
SOLO_LED_ON_VALUE = Rgb.BLUE.midi_value
SOLO_LED_OFF_VALUE = (0, 1, 8)
TRACK_ON_LED_VALUE = Rgb.YELLOW.midi_value
TRACK_OFF_LED_VALUE = (8, 6, 0)


class SelectedTrackControlComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._solo_button = None
        self._track_on_button = None
        self._solo_button_slot = None
        self._track_on_button_slot = None
        self._last_solo_led_value = None
        self._last_track_on_led_value = None
        self._midi_sender = None
        self._led_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_led_feedback),
                    task.delay(LED_FEEDBACK_UPDATE_INTERVAL),
                )
            )
        )

    def set_solo_button(self, button):
        self._set_button("solo", button)

    def set_track_on_button(self, button):
        self._set_button("track_on", button)

    def set_midi_sender(self, midi_sender):
        self._midi_sender = midi_sender

    def refresh_led_feedback(self):
        self._update_led("solo", force=True)
        self._update_led("track_on", force=True)

    def _set_button(self, control_name, button):
        slot_attr = "_{}_button_slot".format(control_name)
        slot = getattr(self, slot_attr)
        if slot is not None:
            slot.disconnect()
            setattr(self, slot_attr, None)
        setattr(self, "_{}_button".format(control_name), button)
        setattr(self, "_last_{}_led_value".format(control_name), None)
        if button is not None:
            setattr(
                self,
                slot_attr,
                self.register_slot(
                    button,
                    lambda value, *a, _control_name=control_name: self._on_button_value(_control_name, value),
                    "value",
                ),
            )
        self._update_led(control_name, force=True)

    def _on_button_value(self, control_name, value):
        if value > 0:
            if control_name == "solo":
                self._toggle_selected_track_bool("solo")
            elif control_name == "track_on":
                self._toggle_selected_track_bool("mute")
        self._update_led(control_name, force=True)

    def _toggle_selected_track_bool(self, attribute):
        track = self._selected_track()
        current = self._track_bool(track, attribute)
        if current is None:
            return
        try:
            setattr(track, attribute, not current)
        except (AttributeError, RuntimeError):
            return

    def _update_led_feedback(self):
        self._update_led("solo")
        self._update_led("track_on")

    def _update_led(self, control_name, force=False):
        if control_name == "solo":
            led_value = self._solo_led_value()
        elif control_name == "track_on":
            led_value = self._track_on_led_value()
        else:
            return
        self._send_led_value(control_name, led_value, force=force)

    def _send_led_value(self, control_name, led_value, force=False):
        button = getattr(self, "_{}_button".format(control_name))
        if button is None:
            return
        last_led_attr = "_last_{}_led_value".format(control_name)
        if not force and getattr(self, last_led_attr) == led_value:
            return
        try:
            if self._is_rgb_led_value(led_value):
                if not self._send_led_rgb(control_name, button, led_value):
                    return
            else:
                button.send_value(led_value)
            setattr(self, last_led_attr, led_value)
        except RuntimeError:
            return

    def _is_rgb_led_value(self, led_value):
        return isinstance(led_value, tuple) and len(led_value) == 3

    def _send_led_rgb(self, control_name, button, rgb):
        control_index = self._control_index_for_button(control_name, button)
        if control_index is None:
            return False
        message = RGB_LED_SYSEX_PREFIX + (control_index,) + tuple(int(value) for value in rgb) + (midi.SYSEX_END,)
        sender = self._midi_sender or getattr(button, "send_midi", None)
        if sender is None:
            return False
        try:
            sender(message)
        except RuntimeError:
            return False
        return True

    def _control_index_for_button(self, control_name, button):
        try:
            return button.message_identifier()
        except (AttributeError, RuntimeError):
            return BUTTON_CONTROL_INDICES.get(control_name)

    def _solo_led_value(self):
        track = self._selected_track()
        solo = self._track_bool(track, "solo")
        return SOLO_LED_ON_VALUE if solo else SOLO_LED_OFF_VALUE

    def _track_on_led_value(self):
        track = self._selected_track()
        mute = self._track_bool(track, "mute")
        if mute is None:
            return TRACK_OFF_LED_VALUE
        return TRACK_OFF_LED_VALUE if mute else TRACK_ON_LED_VALUE

    def _selected_track(self):
        try:
            selected_track = self.song.view.selected_track
        except (AttributeError, RuntimeError):
            return None
        return selected_track if liveobj_valid(selected_track) else None

    def _track_bool(self, track, attribute):
        if not liveobj_valid(track):
            return None
        try:
            return bool(getattr(track, attribute))
        except (AttributeError, RuntimeError):
            return None
