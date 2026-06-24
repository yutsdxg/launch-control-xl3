import logging

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid

from .colors import instrument_button_rgb
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER, CUSTOM_PARAMETER_APPEND_REST
from .custom_parameter_utils import (
    DEVICE_ON_PARAMETER_NAME,
    build_device_order_index,
    normalize_device_key,
    order_named_items,
)
from .display import send_display
from .led import LedSender
from .track_resolver import selected_track

ASSIGNMENT_UPDATE_INTERVAL = 0.1
TARGET_DEVICE_INDEX = 2
ENCODER_COUNT = 24
FADER_COUNT = 8
BUTTON_COUNT = 16
FADER_PARAMETER_OFFSET = ENCODER_COUNT
BUTTON_PARAMETER_OFFSET = ENCODER_COUNT + FADER_COUNT
LOGGER = logging.getLogger(__name__)
CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)


class InstrumentAssignmentsComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._active = False
        self._controls = {}
        self._connected_parameters = {}
        self._connected_parameter_signatures = {}
        self._control_slots = {}
        self._buttons = [None] * BUTTON_COUNT
        self._button_slots = [None] * BUTTON_COUNT
        self._display_commands = {}
        self._target_parameter_cache_signature = None
        self._target_parameter_cache = ()
        self._led_sender = LedSender()
        self._assignment_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_assignments),
                    task.delay(ASSIGNMENT_UPDATE_INTERVAL),
                )
            )
        )

    def set_active(self, active):
        active = bool(active)
        if self._active == active:
            if active:
                self._update_assignments(force=True)
                self.refresh_led_feedback()
            return
        self._active = active
        if self._active:
            self._clear_target_parameter_cache()
            self._update_assignments(force=True)
            self.refresh_led_feedback()
        else:
            self._clear_target_parameter_cache()
            self._release_all_parameter_controls()
            self._turn_button_leds_off(force=True)

    def set_midi_sender(self, midi_sender):
        self._led_sender.set_midi_sender(midi_sender)
        self.refresh_led_feedback()

    def refresh_led_feedback(self):
        if not self._active:
            return
        for offset in range(BUTTON_COUNT):
            self._update_button_led(offset, force=True)

    def _set_display_command(self, name, command):
        self._display_commands[name] = command

    def _set_parameter_control(self, name, control):
        previous = self._controls.get(name)
        if previous is control:
            return
        slot = self._control_slots.pop(name, None)
        if slot is not None:
            slot.disconnect()
        self._release_parameter_control(name, previous)
        self._controls[name] = control
        if control is not None:
            self._control_slots[name] = self.register_slot(
                control,
                lambda value, *a, _name=name: self._on_parameter_control_value(_name, value),
                "value",
            )
        self._update_parameter_assignment(name, force=True)

    def _set_button(self, offset, button):
        previous = self._buttons[offset]
        slot = self._button_slots[offset]
        if slot is not None:
            slot.disconnect()
            self._button_slots[offset] = None
        if previous is not None:
            self._led_sender.forget(previous)
        self._buttons[offset] = button
        if button is not None:
            self._button_slots[offset] = self.register_slot(
                button,
                lambda value, *a, _offset=offset: self._on_button_value(_offset, value),
                "value",
            )
        self._update_button_led(offset, force=True)

    def _update_assignments(self, force=False):
        if not self._active:
            return
        for name in tuple(self._controls):
            self._update_parameter_assignment(name, force=force)
        for offset in range(BUTTON_COUNT):
            self._update_button_led(offset)

    def _update_parameter_assignment(self, name, force=False):
        control = self._controls.get(name)
        if not self._active:
            if name in self._connected_parameters:
                self._release_parameter_control(name, control)
            return
        parameter = self._parameter_for_control(name)
        parameter_signature = self._parameter_signature(name, parameter)
        if (
            not force
            and parameter_signature is not None
            and parameter_signature == self._connected_parameter_signatures.get(name)
            and self._parameter_is_enabled(parameter)
        ):
            return
        self._release_parameter_control(name, control)
        if control is None:
            return
        if not self._parameter_is_enabled(parameter):
            return
        try:
            control.connect_to(parameter)
        except RuntimeError:
            return
        self._connected_parameters[name] = parameter
        self._connected_parameter_signatures[name] = parameter_signature

    def _release_all_parameter_controls(self):
        for name, control in tuple(self._controls.items()):
            self._release_parameter_control(name, control)

    def _release_parameter_control(self, name, control):
        self._connected_parameters.pop(name, None)
        self._connected_parameter_signatures.pop(name, None)
        if control is None:
            return
        try:
            control.release_parameter()
        except (AttributeError, RuntimeError):
            pass

    def _on_parameter_control_value(self, name, value):
        if not self._active:
            return
        if name.startswith("encoder_") and value == 64:
            return
        parameter = self._connected_parameters.get(name)
        if self._parameter_is_enabled(parameter):
            self._display_parameter(name, parameter)

    def _on_button_value(self, offset, value):
        if not self._active:
            return
        if value <= 0:
            return
        parameter = self._button_parameter(offset)
        if not self._parameter_is_enabled(parameter):
            self._update_button_led(offset, force=True)
            return
        target_value = self._toggled_parameter_value(parameter)
        if target_value is None:
            self._update_button_led(offset, force=True)
            return
        try:
            parameter.value = target_value
        except (RuntimeError, ValueError, TypeError):
            return
        self._update_button_led(offset, force=True)

    def _button_parameter(self, offset):
        return self._parameter_by_number(BUTTON_PARAMETER_OFFSET + offset + 1)

    def _parameter_for_control(self, name):
        number = self._parameter_number_for_control(name)
        return self._parameter_by_number(number)

    def _parameter_number_for_control(self, name):
        if name.startswith("encoder_"):
            return self._number_suffix(name)
        if name.startswith("fader_"):
            number = self._number_suffix(name)
            return FADER_PARAMETER_OFFSET + number if number is not None else None
        return None

    def _number_suffix(self, name):
        try:
            return int(name.split("_")[1])
        except (IndexError, TypeError, ValueError):
            return None

    def _parameter_by_number(self, parameter_number):
        if parameter_number is None or parameter_number < 1:
            return None
        parameters = self._target_parameters()
        index = parameter_number - 1
        return parameters[index] if index < len(parameters) else None

    def _target_parameters(self):
        device = self._target_device()
        if not liveobj_valid(device):
            self._clear_target_parameter_cache()
            return ()
        signature = self._target_signature(device)
        if signature != self._target_parameter_cache_signature:
            self._target_parameter_cache_signature = signature
            self._target_parameter_cache = self._ordered_device_parameters(device)
        return self._target_parameter_cache

    def _clear_target_parameter_cache(self):
        self._target_parameter_cache_signature = None
        self._target_parameter_cache = ()

    def _target_signature(self, device):
        track = selected_track(self.song)
        device_count = None
        if liveobj_valid(track):
            try:
                device_count = len(tuple(track.devices))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                device_count = None
        return (
            self._track_index(track),
            self._object_name(track),
            TARGET_DEVICE_INDEX,
            device_count,
            self._object_name(device),
            self._object_attr(device, "class_name"),
            self._object_attr(device, "class_display_name"),
        )

    def _target_device(self):
        track = selected_track(self.song)
        if not liveobj_valid(track):
            return None
        try:
            devices = tuple(track.devices)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        if len(devices) <= TARGET_DEVICE_INDEX:
            return None
        device = devices[TARGET_DEVICE_INDEX]
        return device if liveobj_valid(device) else None

    def _ordered_device_parameters(self, device):
        try:
            parameters = tuple(device.parameters)
        except (AttributeError, RuntimeError):
            return ()
        parameters = tuple(parameter for parameter in parameters if self._is_assignable_device_parameter(parameter))
        custom_order = self._resolve_custom_order(device)
        if custom_order is None:
            return parameters
        ordered, missing_requested_names = order_named_items(
            parameters,
            custom_order,
            append_rest=CUSTOM_PARAMETER_APPEND_REST,
            get_name=self._parameter_name,
            is_valid_item=self._is_assignable_device_parameter,
            keep_missing_slots=True,
        )
        try:
            if missing_requested_names:
                LOGGER.info(
                    "LCXL3 instrument custom order missing names: device=%s names=%s",
                    self._object_name(device),
                    ", ".join(str(name) for name in missing_requested_names),
                )
        except Exception:
            pass
        return ordered

    def _parameter_signature(self, name, parameter):
        if not self._parameter_is_enabled(parameter):
            return None
        device = self._target_device()
        track = selected_track(self.song)
        return (
            name,
            self._parameter_number_for_control(name),
            self._track_index(track),
            self._object_name(track),
            TARGET_DEVICE_INDEX,
            self._object_name(device),
            self._object_attr(device, "class_name"),
            self._object_attr(device, "class_display_name"),
            self._object_name(parameter),
            self._parameter_attr(parameter, "min"),
            self._parameter_attr(parameter, "max"),
        )

    def _track_index(self, track):
        if not liveobj_valid(track):
            return None
        try:
            tracks = tuple(self.song.tracks)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        for index, candidate in enumerate(tracks):
            try:
                if candidate == track:
                    return index
            except RuntimeError:
                continue
        return None

    def _object_attr(self, obj, attr):
        try:
            return str(getattr(obj, attr, ""))
        except (AttributeError, RuntimeError):
            return ""

    def _parameter_device(self, parameter):
        try:
            parent = getattr(parameter, "canonical_parent", None)
        except RuntimeError:
            return None
        if parent is None:
            return None
        for attr in ("parameters", "class_name", "class_display_name"):
            try:
                getattr(parent, attr)
                return parent
            except (AttributeError, RuntimeError):
                pass
        return None

    def _parameter_attr(self, parameter, attr):
        try:
            return getattr(parameter, attr)
        except (AttributeError, RuntimeError):
            return None

    def _resolve_custom_order(self, device):
        name_keys = (
            getattr(device, "name", ""),
            getattr(device, "class_name", ""),
            getattr(device, "class_display_name", ""),
        )
        for key in name_keys:
            normalized = normalize_device_key(key)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
        return None

    def _is_assignable_device_parameter(self, parameter):
        if not liveobj_valid(parameter):
            return False
        return self._parameter_name(parameter) not in ("", DEVICE_ON_PARAMETER_NAME)

    def _parameter_name(self, parameter):
        try:
            return getattr(parameter, "name", "") or ""
        except RuntimeError:
            return ""

    def _parameter_is_enabled(self, parameter):
        if not liveobj_valid(parameter):
            return False
        try:
            return bool(getattr(parameter, "is_enabled", True))
        except RuntimeError:
            return False

    def _toggled_parameter_value(self, parameter):
        try:
            min_value = parameter.min
            max_value = parameter.max
            minimum = float(min_value)
            maximum = float(max_value)
            current = float(parameter.value)
            if maximum <= minimum:
                return None
            midpoint = minimum + ((maximum - minimum) / 2.0)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        return min_value if current > midpoint else max_value

    def _button_state(self, offset):
        parameter = self._button_parameter(offset)
        if not self._parameter_is_enabled(parameter):
            return None
        try:
            minimum = float(parameter.min)
            maximum = float(parameter.max)
            current = float(parameter.value)
            if maximum <= minimum:
                return None
            midpoint = minimum + ((maximum - minimum) / 2.0)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        return current > midpoint

    def _update_button_led(self, offset, force=False):
        button = self._buttons[offset]
        if button is None:
            return
        if not self._active:
            return
        state = self._button_state(offset)
        rgb = instrument_button_rgb(state)
        self._led_sender.send_rgb(button, rgb, force=force)

    def _turn_button_leds_off(self, force=False):
        for button in self._buttons:
            if button is not None:
                self._led_sender.send_rgb(button, instrument_button_rgb(None), force=force)

    def _display_parameter(self, control_name, parameter):
        send_display(
            self._display_commands.get(control_name),
            (
                self._object_name(self._target_device()) or "-",
                self._object_name(parameter) or "-",
                self._parameter_value_text(parameter) or "-",
            ),
            trigger=True,
        )

    def _object_name(self, obj):
        for attr in ("name", "class_display_name", "class_name"):
            try:
                value = getattr(obj, attr, "")
            except RuntimeError:
                value = ""
            if value:
                return str(value)
        return ""

    def _parameter_value_text(self, parameter):
        try:
            return str(parameter)
        except RuntimeError:
            return ""

    def disconnect(self):
        for slot in tuple(self._control_slots.values()):
            slot.disconnect()
        self._control_slots = {}
        for slot in tuple(self._button_slots):
            if slot is not None:
                slot.disconnect()
        self._button_slots = [None] * BUTTON_COUNT
        self._release_all_parameter_controls()
        try:
            super().disconnect()
        except AttributeError:
            pass


def _make_parameter_control_setter(name):
    def _setter(self, control):
        self._set_parameter_control(name, control)

    return _setter


def _make_display_setter(name):
    def _setter(self, command):
        self._set_display_command(name, command)

    return _setter


def _make_button_setter(offset):
    def _setter(self, button):
        self._set_button(offset, button)

    return _setter


for _number in range(1, ENCODER_COUNT + 1):
    _name = "encoder_{}".format(_number)
    setattr(InstrumentAssignmentsComponent, "set_{}".format(_name), _make_parameter_control_setter(_name))
    setattr(InstrumentAssignmentsComponent, "set_{}_display".format(_name), _make_display_setter(_name))

for _number in range(1, FADER_COUNT + 1):
    _name = "fader_{}".format(_number)
    setattr(InstrumentAssignmentsComponent, "set_{}".format(_name), _make_parameter_control_setter(_name))
    setattr(InstrumentAssignmentsComponent, "set_{}_display".format(_name), _make_display_setter(_name))

for _number in range(1, BUTTON_COUNT + 1):
    setattr(
        InstrumentAssignmentsComponent,
        "set_button_{}".format(_number),
        _make_button_setter(_number - 1),
    )
