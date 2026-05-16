from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from . import midi
from .colors import Rgb

LED_FEEDBACK_UPDATE_INTERVAL = 0.1
RGB_LED_SYSEX_PREFIX = midi.SYSEX_HEADER + (1, 83)
PITCH_DEVICE_INDEX = 1
PITCH_PARAMETER_NAME = "pitch"
PITCH_STEP = 12.0
PITCH_LED_LEVELS = (
    (36.0, (64, 10, 10), (10, 34, 96)),
    (24.0, (127, 12, 12), (14, 54, 127)),
    (12.0, (127, 42, 42), (44, 84, 127)),
)
ENCODER_MIN_LED_VALUE = (6, 6, 6)
BUTTON_LED_OFF_VALUE = Rgb.OFF.midi_value
PITCH_LED_OFF_VALUE = (0, 0, 0)
PITCH_NEUTRAL_LED_VALUE = ENCODER_MIN_LED_VALUE
MOMENTARY_BUTTON_LED_ON_VALUE = Rgb.WHITE.midi_value
BUTTON_CONTROL_INDICES = {
    "cursor_up": 43,
    "cursor_down": 51,
    "pitch_up": 44,
    "pitch_down": 52,
}


class PerformanceButtonsComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._cursor_up_button = None
        self._cursor_down_button = None
        self._pitch_up_button = None
        self._pitch_down_button = None
        self._cursor_up_button_slot = None
        self._cursor_down_button_slot = None
        self._pitch_up_button_slot = None
        self._pitch_down_button_slot = None
        self._last_cursor_up_led_value = None
        self._last_cursor_down_led_value = None
        self._last_pitch_up_led_value = None
        self._last_pitch_down_led_value = None
        self._midi_sender = None
        self._monitored_pitch_parameter = None
        self._pitch_parameter_listener_attached = False
        self._led_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_pitch_led_feedback),
                    task.delay(LED_FEEDBACK_UPDATE_INTERVAL),
                )
            )
        )

    def set_cursor_up_button(self, button):
        self._set_button("cursor_up", button, self._on_cursor_button_value)

    def set_cursor_down_button(self, button):
        self._set_button("cursor_down", button, self._on_cursor_button_value)

    def set_pitch_up_button(self, button):
        self._set_button("pitch_up", button, self._on_pitch_up_button_value)

    def set_pitch_down_button(self, button):
        self._set_button("pitch_down", button, self._on_pitch_down_button_value)

    def set_midi_sender(self, midi_sender):
        self._midi_sender = midi_sender
        self.refresh_led_feedback()

    def refresh_led_feedback(self):
        self._update_led("cursor_up", force=True)
        self._update_led("cursor_down", force=True)
        self._update_pitch_led_feedback(force=True)

    def _set_button(self, control_name, button, listener):
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
                    lambda value, *a, _control_name=control_name: listener(_control_name, value),
                    "value",
                ),
            )
        self._update_led(control_name, force=True)

    def _on_cursor_button_value(self, control_name, value):
        led_value = MOMENTARY_BUTTON_LED_ON_VALUE if value > 0 else ENCODER_MIN_LED_VALUE
        self._send_led_value(control_name, led_value, force=True)

    def _on_pitch_up_button_value(self, control_name, value):
        if value > 0:
            self._step_pitch(PITCH_STEP)
        self._update_led(control_name, force=True)
        self._update_led("pitch_down", force=True)

    def _on_pitch_down_button_value(self, control_name, value):
        if value > 0:
            self._step_pitch(-PITCH_STEP)
        self._update_led(control_name, force=True)
        self._update_led("pitch_up", force=True)

    def _step_pitch(self, delta):
        parameter = self._pitch_parameter()
        if not liveobj_valid(parameter):
            return
        if not getattr(parameter, "is_enabled", True):
            return
        try:
            min_value = parameter.min
            max_value = parameter.max
            current_value = parameter.value
        except (AttributeError, RuntimeError):
            return
        try:
            target_value = min(max(current_value + delta, min_value), max_value)
            parameter.value = target_value
        except RuntimeError:
            return

    def _update_pitch_led_feedback(self, force=False):
        target_changed = self._update_pitch_monitor()
        self._update_led("pitch_up", force=force or target_changed)
        self._update_led("pitch_down", force=force or target_changed)

    def _update_pitch_monitor(self):
        parameter = self._pitch_parameter()
        if parameter is self._monitored_pitch_parameter:
            return False
        self._disconnect_pitch_parameter_listener()
        if not liveobj_valid(parameter):
            return False
        self._monitored_pitch_parameter = parameter
        try:
            parameter.add_value_listener(self._on_pitch_parameter_value_changed)
            self._pitch_parameter_listener_attached = True
        except (AttributeError, RuntimeError):
            self._pitch_parameter_listener_attached = False
        return True

    def _disconnect_pitch_parameter_listener(self):
        parameter = self._monitored_pitch_parameter
        if parameter is not None and self._pitch_parameter_listener_attached:
            try:
                parameter.remove_value_listener(self._on_pitch_parameter_value_changed)
            except (AttributeError, RuntimeError, ValueError):
                pass
        self._monitored_pitch_parameter = None
        self._pitch_parameter_listener_attached = False

    def _on_pitch_parameter_value_changed(self, *a):
        self._update_pitch_led_feedback()

    def _update_led(self, control_name, force=False):
        if control_name in ("cursor_up", "cursor_down"):
            led_value = ENCODER_MIN_LED_VALUE
        elif control_name == "pitch_up":
            self._update_pitch_monitor()
            led_value = self._pitch_up_led_value()
        elif control_name == "pitch_down":
            self._update_pitch_monitor()
            led_value = self._pitch_down_led_value()
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

    def _pitch_up_led_value(self):
        pitch_value = self._pitch_value()
        if pitch_value is None:
            return PITCH_LED_OFF_VALUE
        for threshold, red_value, _ in PITCH_LED_LEVELS:
            if pitch_value >= threshold:
                return red_value
        return PITCH_NEUTRAL_LED_VALUE

    def _pitch_down_led_value(self):
        pitch_value = self._pitch_value()
        if pitch_value is None:
            return PITCH_LED_OFF_VALUE
        for threshold, _, blue_value in PITCH_LED_LEVELS:
            if pitch_value <= -threshold:
                return blue_value
        return PITCH_NEUTRAL_LED_VALUE

    def _pitch_value(self):
        parameter = self._pitch_parameter()
        if not liveobj_valid(parameter):
            return None
        if not getattr(parameter, "is_enabled", True):
            return None
        try:
            return parameter.value
        except RuntimeError:
            return None

    def _pitch_parameter(self):
        device = self._pitch_device()
        if not liveobj_valid(device):
            return None
        try:
            parameters = tuple(device.parameters)
        except (AttributeError, RuntimeError):
            return None
        for parameter in parameters:
            try:
                if str(getattr(parameter, "name", "")).strip().lower() == PITCH_PARAMETER_NAME:
                    return parameter
            except RuntimeError:
                continue
        return None

    def _pitch_device(self):
        track = self._selected_track()
        if not liveobj_valid(track):
            return None
        try:
            devices = tuple(track.devices)
        except (AttributeError, RuntimeError):
            return None
        if len(devices) <= PITCH_DEVICE_INDEX:
            return None
        return devices[PITCH_DEVICE_INDEX]

    def _selected_track(self):
        try:
            selected_track = self.song.view.selected_track
        except (AttributeError, RuntimeError):
            return None
        return selected_track if liveobj_valid(selected_track) else None

    def disconnect(self):
        self._disconnect_pitch_parameter_listener()
        try:
            super().disconnect()
        except AttributeError:
            pass
