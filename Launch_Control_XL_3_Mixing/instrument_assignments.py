import logging

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid

from .colors import instrument_button_rgb, mode_button_rgb, Theme
from .custom_parameter_order import (
    CUSTOM_DEVICE_PARAMETER_ORDER,
    CUSTOM_DEVICE_PARAMETER_OVERRIDES,
    CUSTOM_PARAMETER_APPEND_REST,
)
from .custom_parameter_utils import (
    DEVICE_ON_PARAMETER_NAME,
    build_device_order_index,
    extract_custom_entry_name_and_options,
    normalize_device_key,
    order_named_items,
)
from .display import send_display, send_locked_display, send_unassigned_display
from .keyboard_navigation import EncoderKeyboardNavigation
from .led import LedSender
from .parameter_actions import apply_left_turn_action, bind_left_turn_actions, bind_relative_targets
from .parameter_overrides import apply_overrides, bind_overrides, matching_overrides
from .special_parameters import (
    REDUCED_SENSITIVITY_INPUT_THRESHOLD,
    _parameter_index,
    _parameter_value_for_index,
)
from .track_resolver import selected_track

ASSIGNMENT_UPDATE_INTERVAL = 0.1
TARGET_DEVICE_INDEX = 2
ENCODER_COUNT = 24
FADER_COUNT = 8
BUTTON_COUNT = 16
FADER_PARAMETER_OFFSET = ENCODER_COUNT
BUTTON_PARAMETER_OFFSET = ENCODER_COUNT + FADER_COUNT
KEYBOARD_ENCODER = "encoder_24"
LOGGER = logging.getLogger(__name__)
CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)
CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_OVERRIDES)


class InstrumentAssignmentsComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._active = False
        self._shift_pressed = False
        self._locked = False
        self._controls = {}
        self._connected_parameters = {}
        self._connected_parameter_signatures = {}
        self._discrete_encoder_inputs = {}
        self._control_slots = {}
        self._buttons = [None] * BUTTON_COUNT
        self._button_slots = [None] * BUTTON_COUNT
        self._display_commands = {}
        self._keyboard_control = None
        self._keyboard_navigation = EncoderKeyboardNavigation()
        self._clear_target_parameter_cache()
        self._led_sender = LedSender()
        self._assignment_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_assignments),
                    task.delay(ASSIGNMENT_UPDATE_INTERVAL),
                )
            )
        )

    def set_locked(self, locked):
        locked = bool(locked)
        if self._locked == locked:
            return
        self._locked = locked
        self._led_sender.set_locked(locked)
        self._keyboard_navigation.reset()
        self._discrete_encoder_inputs.clear()
        if self._active:
            self._update_assignments(force=True)
            self.refresh_led_feedback()

    def set_active(self, active):
        active = bool(active)
        if self._active == active:
            if active:
                self._update_assignments(force=True)
                self.refresh_led_feedback()
            return
        self._active = active
        self._keyboard_navigation.reset()
        if self._active:
            self._clear_target_parameter_cache()
            self._update_assignments(force=True)
            self.refresh_led_feedback()
        else:
            self._clear_target_parameter_cache()
            self._release_all_parameter_controls()
            self._turn_button_leds_off(force=True)

    def start_keyboard_navigation(self):
        """Start once from the surface lifecycle, never while constructing controls."""
        return self._keyboard_navigation.start()

    def reset_keyboard_navigation(self):
        self._keyboard_navigation.reset()
        if self._active:
            self._display_keyboard_navigation(trigger=False)

    def set_midi_sender(self, midi_sender):
        self._led_sender.set_midi_sender(midi_sender)
        self.refresh_led_feedback()

    def set_shift_pressed(self, pressed):
        pressed = bool(pressed)
        if self._shift_pressed == pressed:
            return
        self._shift_pressed = pressed
        self._keyboard_navigation.reset()
        self._discrete_encoder_inputs.clear()
        if self._active:
            self._update_assignments(force=True)

    def refresh_led_feedback(self):
        if not self._active:
            return
        for offset in range(BUTTON_COUNT):
            self._update_button_led(offset, force=True)
        self._update_keyboard_assignment(force=True)

    def _set_display_command(self, name, command):
        self._display_commands[name] = command
        self._prepare_control_display(name)

    def _prepare_control_display(self, name):
        if not self._active:
            return
        if self._locked:
            send_locked_display(self._display_commands.get(name))
            return
        if name == KEYBOARD_ENCODER:
            self._display_keyboard_navigation(trigger=False)
            return
        parameter = self._connected_parameters.get(name)
        if self._parameter_is_enabled(parameter):
            self._display_parameter(name, parameter, trigger=False)
        else:
            send_unassigned_display(self._display_commands.get(name), name, trigger=False)

    def refresh_display_feedback(self):
        if not self._active:
            return
        for name, command in self._display_commands.items():
            try:
                command.clear_send_cache()
            except (AttributeError, RuntimeError):
                pass
        self._update_assignments()

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
        self._prepare_control_display(name)

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
        # Drain worker replies every 100 ms even while Mixing owns the controls.
        self._keyboard_navigation.poll()
        if not self._active:
            return
        self._refresh_target_parameter_cache(check_overrides=True)
        for name in tuple(self._controls):
            self._update_parameter_assignment(name, force=force)
        for offset in range(BUTTON_COUNT):
            self._update_button_led(offset)
        for name in self._controls:
            self._prepare_control_display(name)

    def _update_parameter_assignment(self, name, force=False):
        control = self._controls.get(name)
        if not self._active:
            if name in self._connected_parameters or (
                name == KEYBOARD_ENCODER and self._keyboard_control is not None
            ):
                self._release_parameter_control(name, control)
            return
        if name == KEYBOARD_ENCODER:
            self._update_keyboard_assignment(force=force)
            return
        parameter = self._parameter_for_control(name)
        parameter_signature = self._parameter_signature(name, parameter)
        if (
            not force
            and parameter_signature is not None
            and parameter_signature == self._connected_parameter_signatures.get(name)
            and self._parameter_is_enabled(parameter)
        ):
            if self._locked or self._shift_pressed or self._encoder_uses_manual_mapping(name):
                self._refresh_manual_led_feedback(control)
            return
        self._discrete_encoder_inputs.pop(name, None)
        if (
            (self._locked or self._shift_pressed or self._encoder_uses_manual_mapping(name))
            and control is not None
            and self._parameter_is_enabled(parameter)
        ):
            # Keep a display/LED assignment while removing Live's native MIDI mapping.
            # Set the LED source first so release_parameter() does not turn it off.
            self._set_manual_led_parameter(control, parameter)
            try:
                control.release_parameter()
            except (AttributeError, RuntimeError):
                pass
            self._connected_parameters[name] = parameter
            self._connected_parameter_signatures[name] = parameter_signature
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
        owns_keyboard_control = control is not None and control is self._keyboard_control
        if not self._active and name not in self._connected_parameters and not owns_keyboard_control:
            return
        self._connected_parameters.pop(name, None)
        self._connected_parameter_signatures.pop(name, None)
        self._discrete_encoder_inputs.pop(name, None)
        if owns_keyboard_control:
            self._keyboard_control = None
            self._keyboard_navigation.reset()
            try:
                control.clear_manual_led_rgb()
            except (AttributeError, RuntimeError):
                pass
        if control is None:
            return
        try:
            control.clear_manual_led_parameter()
        except (AttributeError, RuntimeError):
            pass
        try:
            control.release_parameter()
        except (AttributeError, RuntimeError):
            pass

    def _set_manual_led_parameter(self, control, parameter):
        try:
            control.set_manual_led_parameter(parameter)
        except (AttributeError, RuntimeError):
            pass

    def _refresh_manual_led_feedback(self, control):
        try:
            control.refresh_manual_led_feedback()
        except (AttributeError, RuntimeError):
            pass

    def _update_keyboard_assignment(self, force=False):
        control = self._controls.get(KEYBOARD_ENCODER)
        if not self._active or control is None:
            return
        try:
            control.set_manual_led_rgb(mode_button_rgb(True, Theme.MODE_INSTRUMENT), force=force)
        except (AttributeError, RuntimeError):
            pass
        if self._keyboard_control is not control:
            # Reserving this encoder must also remove Live's native parameter map.
            self._keyboard_control = control
            self._connected_parameters.pop(KEYBOARD_ENCODER, None)
            self._connected_parameter_signatures.pop(KEYBOARD_ENCODER, None)
            try:
                control.release_parameter()
            except (AttributeError, RuntimeError):
                pass

    def _display_keyboard_navigation(self, trigger=True):
        if self._locked:
            return send_locked_display(self._display_commands.get(KEYBOARD_ENCODER), trigger=trigger)
        return send_display(
            self._display_commands.get(KEYBOARD_ENCODER),
            ("Keyboard", "Preset Up-Down", self._keyboard_navigation.last_action),
            trigger=trigger,
        )

    def _on_parameter_control_value(self, name, value):
        if not self._active:
            return
        if self._locked:
            send_locked_display(self._display_commands.get(name), trigger=True)
            return
        if name.startswith("encoder_") and value == 64:
            return
        if self._shift_pressed and name.startswith("encoder_"):
            self.preview_encoder(name)
            return
        if name == KEYBOARD_ENCODER:
            sent = self._keyboard_navigation.receive_value(value)
            self._display_keyboard_navigation(trigger=sent)
            return
        if self._shift_pressed:
            self._update_parameter_assignment(name)
        elif self._encoder_uses_manual_mapping(name):
            # A turn can arrive before the periodic track/model refresh. Keep
            # manual primaries and companions on the same current assignment,
            # including a model that adds an action to a manual control.
            self._refresh_target_parameter_cache(check_overrides=True)
            self._update_parameter_assignment(name)
        parameter = self._connected_parameters.get(name)
        if self._parameter_is_enabled(parameter):
            if not self._shift_pressed and self._encoder_uses_manual_mapping(name):
                # Physical left is evaluated before the primary's inversion.
                if value < 64:
                    for binding in self._left_turn_actions.get(name, ()):
                        apply_left_turn_action(binding)
                self._apply_encoder_value(name, parameter, value)
                for target, options in self._relative_targets.get(name, ()):
                    if target != parameter and self._parameter_is_enabled(target):
                        self._apply_encoder_value(name, target, value, options=options)
                self._refresh_manual_led_feedback(self._controls.get(name))
            self._display_parameter(name, parameter)
        elif self._shift_pressed:
            send_unassigned_display(self._display_commands.get(name), name)

    def preview_encoder(self, name):
        """Touch input is display-only and must never enter a parameter value path."""
        if self._active and self._locked:
            send_locked_display(self._display_commands.get(name), trigger=True)
            return
        if not self._active or not self._shift_pressed or name not in self._controls:
            return
        if not name.startswith("encoder_"):
            return
        if name == KEYBOARD_ENCODER:
            self._display_keyboard_navigation()
            return
        self._refresh_target_parameter_cache(check_overrides=True)
        self._update_parameter_assignment(name)
        parameter = self._connected_parameters.get(name)
        if self._parameter_is_enabled(parameter):
            self._display_parameter(name, parameter)
        else:
            send_unassigned_display(self._display_commands.get(name), name)

    def _on_button_value(self, offset, value):
        if not self._active or self._locked:
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
        if name == KEYBOARD_ENCODER:
            return None
        number = self._parameter_number_for_control(name)
        return self._parameter_by_number(number)

    def _encoder_uses_manual_mapping(self, name):
        if not name.startswith("encoder_"):
            return False
        options = self._custom_parameter_options(self._parameter_number_for_control(name))
        return bool(
            options.get("invert_direction")
            or options.get("discrete_values") is not None
            or options.get("discrete_count")
            or options.get("on_left") is not None
            or options.get("relative_targets") is not None
        )

    def _discrete_encoder_input_is_ready(self, name, direction):
        accumulator = self._discrete_encoder_inputs.get(name, 0)
        if accumulator and (accumulator > 0) != (direction > 0):
            accumulator = 0
        accumulator += direction
        if abs(accumulator) >= REDUCED_SENSITIVITY_INPUT_THRESHOLD:
            self._discrete_encoder_inputs[name] = 0
            return True
        self._discrete_encoder_inputs[name] = accumulator
        return False

    def _apply_encoder_value(self, name, parameter, value, options=None):
        # These encoders have no native MIDI map. Apply the configured direction
        # once, preserving the parameter's real display value.
        try:
            minimum = float(parameter.min)
            maximum = float(parameter.max)
            current = float(parameter.value)
            if options is None:
                options = self._custom_parameter_options(self._parameter_number_for_control(name))
            delta = int(value) - 64
            if options.get("invert_direction"):
                delta = -delta
            if maximum <= minimum or delta == 0:
                return
            raw_values = options.get("discrete_values")
            if raw_values is not None:
                # Explicit raw values bypass Live's display conversion entirely.
                # Invalid lists must not fall back to continuous pitch changes.
                raw_values = tuple(float(raw) for raw in raw_values)
                if (
                    len(raw_values) < 2
                    or not all(minimum <= raw <= maximum for raw in raw_values)
                    or not all(left < right for left, right in zip(raw_values, raw_values[1:]))
                ):
                    return
                direction = 1 if delta > 0 else -1
                if not self._discrete_encoder_input_is_ready(name, direction):
                    return
                current_index = min(
                    range(len(raw_values)), key=lambda index: abs(raw_values[index] - current)
                )
                target_index = max(0, min(len(raw_values) - 1, current_index + direction))
                target = raw_values[target_index]
                # Live may round the stored raw value to float32 precision.
                if abs(target - current) > 1e-7:
                    parameter.value = target
                return
            item_count = options.get("discrete_count")
            if item_count:
                current_index = _parameter_index(parameter, item_count)
                if current_index is None:
                    return
                direction = 1 if delta > 0 else -1
                if not self._discrete_encoder_input_is_ready(name, direction):
                    return
                # Share Saturn's normalized index mapping, without probing
                # the plug-in's display formatter or applying CC acceleration.
                target_index = max(0, min(item_count - 1, current_index + direction))
                target = _parameter_value_for_index(parameter, target_index, item_count)
                if abs(target - current) > 1e-9:
                    parameter.value = target
                return
            step = (maximum - minimum) / 127.0
            if getattr(parameter, "is_quantized", False):
                items = tuple(getattr(parameter, "value_items", ()) or ())
                step = (maximum - minimum) / (len(items) - 1) if len(items) > 1 else 1.0
                target = minimum + (round((current - minimum) / step) + delta) * step
            else:
                target = current + delta * step
            target = max(minimum, min(maximum, target))
            if target != current:
                parameter.value = target
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _custom_parameter_options(self, parameter_number):
        device = self._target_device()
        if not liveobj_valid(device) or parameter_number is None or parameter_number < 1:
            return {}
        self._target_parameters()
        order = self._effective_custom_order
        if order is None or parameter_number > len(order):
            return {}
        _, options = extract_custom_entry_name_and_options(order[parameter_number - 1])
        return options if isinstance(options, dict) else {}

    def _custom_parameter_option(self, parameter_number, option):
        return bool(self._custom_parameter_options(parameter_number).get(option, False))

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
        self._refresh_target_parameter_cache()
        return self._target_parameter_cache

    def _refresh_target_parameter_cache(self, check_overrides=False):
        device = self._target_device()
        if not liveobj_valid(device):
            self._clear_target_parameter_cache()
            return
        signature = self._target_signature(device)
        if signature != self._target_parameter_cache_signature:
            self._clear_target_parameter_cache()
            self._target_parameter_cache_signature = signature
            try:
                self._source_parameters = tuple(device.parameters)
            except (AttributeError, RuntimeError, TypeError):
                self._source_parameters = ()
            self._base_custom_order = self._resolve_custom_order(device)
            rules = self._resolve_device_config(device, CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX)
            self._override_bindings = bind_overrides(self._source_parameters, rules, self._parameter_name)
            check_overrides = True
        if check_overrides:
            matching = matching_overrides(self._override_bindings)
            if matching != self._matching_overrides:
                self._matching_overrides = matching
                self._effective_custom_order = apply_overrides(
                    self._base_custom_order, self._override_bindings, matching
                )
                self._target_parameter_cache = self._ordered_device_parameters(
                    device, self._source_parameters, self._effective_custom_order
                )
                self._left_turn_actions = bind_left_turn_actions(
                    self._source_parameters, self._effective_custom_order, self._parameter_name
                )
                self._relative_targets = bind_relative_targets(
                    self._source_parameters, self._effective_custom_order, self._parameter_name
                )

    def _clear_target_parameter_cache(self):
        self._target_parameter_cache_signature = None
        self._target_parameter_cache = ()
        self._source_parameters = ()
        self._left_turn_actions = {}
        self._relative_targets = {}
        self._base_custom_order = None
        self._effective_custom_order = None
        self._override_bindings = ()
        self._matching_overrides = None

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
            device,
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

    def _ordered_device_parameters(self, device, parameters, custom_order):
        parameters = tuple(parameter for parameter in parameters if self._is_assignable_device_parameter(parameter))
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
            device,
            self._object_name(device),
            self._object_attr(device, "class_name"),
            self._object_attr(device, "class_display_name"),
            parameter,
            self._object_name(parameter),
            self._parameter_attr(parameter, "min"),
            self._parameter_attr(parameter, "max"),
            self._custom_parameter_options(self._parameter_number_for_control(name)),
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
        return self._resolve_device_config(device, CUSTOM_DEVICE_PARAMETER_ORDER_INDEX)

    def _resolve_device_config(self, device, index):
        name_keys = (
            getattr(device, "name", ""),
            getattr(device, "class_name", ""),
            getattr(device, "class_display_name", ""),
        )
        for key in name_keys:
            normalized = normalize_device_key(key)
            if normalized and normalized in index:
                return index[normalized]
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
        is_on = current > midpoint
        if self._custom_parameter_option(BUTTON_PARAMETER_OFFSET + offset + 1, "invert_led"):
            return not is_on
        return is_on

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

    def _display_parameter(self, control_name, parameter, trigger=True):
        if self._locked:
            send_locked_display(self._display_commands.get(control_name), trigger=trigger)
            return
        send_display(
            self._display_commands.get(control_name),
            (
                self._object_name(self._target_device()) or "-",
                self._object_name(parameter) or "-",
                self._parameter_value_text(parameter) or "-",
            ),
            trigger=trigger,
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
        self._keyboard_navigation.close()
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
