import time

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from .colors import Rgb

TOGGLE_PARAMETER_START_INDEX = 22
LEGACY_TOGGLE_PARAMETER_START_INDEX = TOGGLE_PARAMETER_START_INDEX - 1
LED_FEEDBACK_UPDATE_INTERVAL = 0.1
LED_FORCE_HOLD_SEC = 0.15


class DeviceToggleComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._buttons = [None] * 8
        self._button_slots = [None] * 8
        self._last_led_values = [None] * 8
        self._forced_led_values = [None] * 8
        self._forced_led_until = [0.0] * 8
        self._led_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_led_feedback),
                    task.delay(LED_FEEDBACK_UPDATE_INTERVAL),
                )
            )
        )

    def set_toggle_button_1(self, button):
        self._set_toggle_button(0, button)

    def set_toggle_button_2(self, button):
        self._set_toggle_button(1, button)

    def set_toggle_button_3(self, button):
        self._set_toggle_button(2, button)

    def set_toggle_button_4(self, button):
        self._set_toggle_button(3, button)

    def set_toggle_button_5(self, button):
        self._set_toggle_button(4, button)

    def set_toggle_button_6(self, button):
        self._set_toggle_button(5, button)

    def set_toggle_button_7(self, button):
        self._set_toggle_button(6, button)

    def set_toggle_button_8(self, button):
        self._set_toggle_button(7, button)

    def _toggle_parameter(self, offset):
        parameter = self._parameter_for_offset(offset)
        if not liveobj_valid(parameter):
            return
        if not getattr(parameter, "is_enabled", True):
            return
        try:
            min_value = parameter.min
            max_value = parameter.max
            current = parameter.value
        except RuntimeError:
            return
        if max_value <= min_value:
            return
        midpoint = min_value + (max_value - min_value) / 2.0
        target_is_on = not (current > midpoint)
        target_value = max_value if target_is_on else min_value
        try:
            parameter.value = target_value
        except RuntimeError:
            return
        forced_led_value = Rgb.WHITE.midi_value if target_is_on else Rgb.WHITE_DIM.midi_value
        self._forced_led_values[offset] = forced_led_value
        self._forced_led_until[offset] = time.monotonic() + LED_FORCE_HOLD_SEC
        self._send_led_value_for_offset(offset, forced_led_value, force=True)

    def _set_toggle_button(self, offset, button):
        slot = self._button_slots[offset]
        if slot is not None:
            slot.disconnect()
            self._button_slots[offset] = None
        self._buttons[offset] = button
        self._last_led_values[offset] = None
        self._forced_led_values[offset] = None
        self._forced_led_until[offset] = 0.0
        if button is not None:
            self._button_slots[offset] = self.register_slot(
                button,
                lambda value, *a, _offset=offset: self._on_toggle_button_value(_offset, value),
                "value",
            )
        self._update_led_for_offset(offset, force=True)

    def _on_toggle_button_value(self, offset, value):
        if value > 0:
            self._toggle_parameter(offset)
        self._update_led_for_offset(offset, force=True)

    def _update_led_feedback(self):
        for offset in range(8):
            self._update_led_for_offset(offset)

    def _update_led_for_offset(self, offset, force=False):
        led_value = self._led_value_for_offset(offset)
        self._send_led_value_for_offset(offset, led_value, force=force)

    def _send_led_value_for_offset(self, offset, led_value, force=False):
        button = self._buttons[offset]
        if button is None:
            return
        if not force and self._last_led_values[offset] == led_value:
            return
        try:
            button.send_value(led_value)
            self._last_led_values[offset] = led_value
        except RuntimeError:
            return

    def _led_value_for_offset(self, offset):
        if time.monotonic() < self._forced_led_until[offset]:
            forced_led = self._forced_led_values[offset]
            if forced_led is not None:
                return forced_led
        parameter = self._parameter_for_offset(offset)
        if not liveobj_valid(parameter):
            return Rgb.OFF.midi_value
        if not getattr(parameter, "is_enabled", True):
            return Rgb.OFF.midi_value
        try:
            min_value = parameter.min
            max_value = parameter.max
            current = parameter.value
        except RuntimeError:
            return Rgb.OFF.midi_value
        if max_value <= min_value:
            return Rgb.OFF.midi_value
        midpoint = min_value + (max_value - min_value) / 2.0
        return Rgb.WHITE.midi_value if current > midpoint else Rgb.WHITE_DIM.midi_value

    def _parameter_for_offset(self, offset):
        selected_track = self.song.view.selected_track
        if not liveobj_valid(selected_track):
            return None
        selected_device = self._resolve_device_for_track(selected_track)
        if not liveobj_valid(selected_device):
            return None
        try:
            parameters = tuple(selected_device.parameters)
        except RuntimeError:
            return None
        start_index = self._resolve_start_index(parameters)
        if start_index is None:
            return None
        parameter_index = start_index + offset
        if not 0 <= parameter_index < len(parameters):
            return None
        parameter = parameters[parameter_index]
        # Guard: never map one Live parameter to multiple toggle buttons.
        for previous_offset in range(offset):
            previous_index = start_index + previous_offset
            if 0 <= previous_index < len(parameters) and parameters[previous_index] is parameter:
                return None
        return parameter

    def _resolve_start_index(self, parameters):
        if len(parameters) > TOGGLE_PARAMETER_START_INDEX:
            return TOGGLE_PARAMETER_START_INDEX
        if len(parameters) > LEGACY_TOGGLE_PARAMETER_START_INDEX:
            return LEGACY_TOGGLE_PARAMETER_START_INDEX
        return None

    def _resolve_device_for_track(self, selected_track):
        try:
            selected_device = selected_track.view.selected_device
        except RuntimeError:
            selected_device = None
        if liveobj_valid(selected_device):
            return selected_device
        try:
            appointed_device = self.song.appointed_device
        except RuntimeError:
            appointed_device = None
        if liveobj_valid(appointed_device):
            return appointed_device
        try:
            devices = tuple(selected_track.devices)
        except RuntimeError:
            devices = ()
        if len(devices) > 0 and liveobj_valid(devices[0]):
            return devices[0]
        return None
