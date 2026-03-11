import time

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from .colors import Rgb
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER, CUSTOM_PARAMETER_APPEND_REST
from .custom_parameter_utils import (
    DEVICE_ON_PARAMETER_NAME,
    build_device_order_index,
    normalize_device_key,
    order_named_items,
)

TOGGLE_PARAMETER_START_INDEX = 21
LEGACY_TOGGLE_PARAMETER_START_INDEX = TOGGLE_PARAMETER_START_INDEX - 1
LED_FEEDBACK_UPDATE_INTERVAL = 0.1
LED_FORCE_HOLD_SEC = 0.15
PIGMENTS_NAME_KEYWORD = "pigments"
PIGMENTS_INVERTED_LED_OFFSETS = (0, 1)
BUTTON_LED_OFF_VALUE = Rgb.OFF.midi_value
BUTTON_LED_ON_VALUE = Rgb.WHITE_HALF.midi_value


CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)


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
        selected_device = self._selected_device()
        parameter = self._parameter_for_offset(offset, selected_device=selected_device)
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
        forced_led_is_on = self._led_is_on(selected_device, offset, target_is_on)
        forced_led_value = BUTTON_LED_ON_VALUE if forced_led_is_on else BUTTON_LED_OFF_VALUE
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
        selected_device = self._selected_device()
        parameter = self._parameter_for_offset(offset, selected_device=selected_device)
        if not liveobj_valid(parameter):
            return BUTTON_LED_OFF_VALUE
        if not getattr(parameter, "is_enabled", True):
            return BUTTON_LED_OFF_VALUE
        try:
            min_value = parameter.min
            max_value = parameter.max
            current = parameter.value
        except RuntimeError:
            return BUTTON_LED_OFF_VALUE
        if max_value <= min_value:
            return BUTTON_LED_OFF_VALUE
        midpoint = min_value + (max_value - min_value) / 2.0
        parameter_is_on = current > midpoint
        led_is_on = self._led_is_on(selected_device, offset, parameter_is_on)
        return BUTTON_LED_ON_VALUE if led_is_on else BUTTON_LED_OFF_VALUE

    def _parameter_for_offset(self, offset, selected_device=None):
        if not liveobj_valid(selected_device):
            selected_device = self._selected_device()
        if not liveobj_valid(selected_device):
            return None
        parameters = self._ordered_parameters(selected_device)
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

    def _ordered_parameters(self, selected_device):
        try:
            base_parameters = tuple(selected_device.parameters)
        except RuntimeError:
            return ()
        base_parameters = tuple(
            p for p in base_parameters if p is not None and getattr(p, "name", "") != DEVICE_ON_PARAMETER_NAME
        )
        custom_order = self._resolve_custom_order(selected_device)
        if not custom_order:
            return base_parameters
        ordered, _ = order_named_items(
            base_parameters,
            custom_order,
            append_rest=CUSTOM_PARAMETER_APPEND_REST,
            get_name=lambda parameter: getattr(parameter, "name", "") or "",
            is_valid_item=lambda parameter: parameter is not None
            and getattr(parameter, "name", "") not in ("", DEVICE_ON_PARAMETER_NAME),
            keep_missing_slots=True,
        )
        return ordered

    def _resolve_custom_order(self, selected_device):
        name_keys = (
            getattr(selected_device, "name", ""),
            getattr(selected_device, "class_name", ""),
            getattr(selected_device, "class_display_name", ""),
        )
        for key in name_keys:
            normalized = normalize_device_key(key)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
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

    def _selected_device(self):
        selected_track = self.song.view.selected_track
        if not liveobj_valid(selected_track):
            return None
        return self._resolve_device_for_track(selected_track)

    def _led_is_on(self, selected_device, offset, parameter_is_on):
        if self._should_invert_led(selected_device, offset):
            return not parameter_is_on
        return parameter_is_on

    def _should_invert_led(self, selected_device, offset):
        return offset in PIGMENTS_INVERTED_LED_OFFSETS and self._is_pigments_device(selected_device)

    def _is_pigments_device(self, selected_device):
        if not liveobj_valid(selected_device):
            return False
        try:
            device_name = selected_device.name or ""
        except RuntimeError:
            return False
        return PIGMENTS_NAME_KEYWORD in device_name.lower()
