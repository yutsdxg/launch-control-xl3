import logging

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid

from .colors import device_toggle_encoder_rgb, encoder_rgb_for_parameter, loopcloud_metric_submode_rgb
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER, CUSTOM_PARAMETER_APPEND_REST
from .custom_parameter_utils import (
    DEVICE_ON_PARAMETER_NAME,
    build_device_order_index,
    normalize_device_key,
    order_named_items,
)
from .display import send_display
from .led import LedSender
from .special_parameters import (
    handle_special_parameter_input,
    is_handled_special_parameter,
    is_special_parameter_candidate,
    parameter_debug_info,
    special_parameter_step_threshold,
)
from .track_resolver import first_named_track, selected_track

ASSIGNMENT_UPDATE_INTERVAL = 0.1
LOGGER = logging.getLogger(__name__)
CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)
LOOPCLOUD_SUBMODE = "loopcloud"
METRIC_AB_SUBMODE = "metric_ab"
METRIC_AB_DEVICE_NAME = "ADPTR MetricAB"
METRIC_AB_PARAMETER_CONTROLS = {
    "fader_1": 1,
    "encoder_17": 2,
    "encoder_9": 3,
}
ON_OFF_ENCODER_DEVICES = {
    2: 1,
    3: 4,
    4: 5,
    5: 6,
    6: 7,
    7: 9,
}


class FixedAssignmentsComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._active = True
        self._controls = {}
        self._connected_parameters = {}
        self._connected_parameter_signatures = {}
        self._on_off_slots = {}
        self._parameter_encoder_slots = {}
        self._submode_switch_slot = None
        self._loopcloud_metric_submode = LOOPCLOUD_SUBMODE
        self._special_parameter_input_accumulators = {}
        self._logged_parameter_assignments = {}
        self._device_parameter_cache = {}
        self._display_commands = {}
        self._led_sender = LedSender()
        self._assignment_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_assignments),
                    task.delay(ASSIGNMENT_UPDATE_INTERVAL),
                )
            )
        )

    def set_midi_sender(self, midi_sender):
        self._led_sender.set_midi_sender(midi_sender)
        self.refresh_led_feedback()

    def set_active(self, active):
        active = bool(active)
        if self._active == active:
            if active:
                self._update_assignments()
                self.refresh_led_feedback()
            return
        self._active = active
        if self._active:
            self._clear_device_parameter_cache()
            self._update_assignments()
            self.refresh_led_feedback()
        else:
            self._clear_device_parameter_cache()
            self._release_all_parameter_controls()
            self._clear_manual_led_rgb(self._controls.get("encoder_1"))
            for encoder_number in ON_OFF_ENCODER_DEVICES:
                self._clear_manual_led_rgb(self._controls.get("encoder_{}".format(encoder_number)))

    def _set_display_command(self, name, command):
        self._display_commands[name] = command

    def refresh_led_feedback(self):
        if not self._active:
            return
        self._update_submode_switch_encoder_led(force=True)
        for encoder_number in ON_OFF_ENCODER_DEVICES:
            self._update_on_off_encoder_led(encoder_number, force=True)

    def _set_parameter_control(self, name, control):
        previous = self._controls.get(name)
        if previous is control:
            return
        slot = self._parameter_encoder_slots.pop(name, None)
        if slot is not None:
            slot.disconnect()
        self._release_parameter_control(name, previous)
        self._controls[name] = control
        if control is not None and self._is_parameter_display_control(name):
            self._parameter_encoder_slots[name] = self.register_slot(
                control,
                lambda value, *a, _name=name: self._on_parameter_control_value(_name, value),
                "value",
            )
        self._update_parameter_assignment(name, force=True)

    def _set_on_off_encoder(self, encoder_number, control):
        name = "encoder_{}".format(encoder_number)
        previous = self._controls.get(name)
        if previous is control:
            return
        slot = self._on_off_slots.pop(encoder_number, None)
        if slot is not None:
            slot.disconnect()
        self._clear_manual_led_rgb(previous)
        self._controls[name] = control
        if control is not None:
            self._on_off_slots[encoder_number] = self.register_slot(
                control,
                lambda value, *a, _number=encoder_number: self._on_on_off_encoder_value(_number, value),
                "value",
            )
        self._update_on_off_encoder_led(encoder_number, force=True)

    def set_encoder_2(self, control):
        self._set_on_off_encoder(2, control)

    def set_encoder_1(self, control):
        self._set_submode_switch_encoder(control)

    def set_encoder_1_display(self, command):
        self._set_display_command("encoder_1", command)

    def set_encoder_2_display(self, command):
        self._set_display_command("encoder_2", command)

    def set_encoder_3(self, control):
        self._set_on_off_encoder(3, control)

    def set_encoder_3_display(self, command):
        self._set_display_command("encoder_3", command)

    def set_encoder_4(self, control):
        self._set_on_off_encoder(4, control)

    def set_encoder_4_display(self, command):
        self._set_display_command("encoder_4", command)

    def set_encoder_5(self, control):
        self._set_on_off_encoder(5, control)

    def set_encoder_5_display(self, command):
        self._set_display_command("encoder_5", command)

    def set_encoder_6(self, control):
        self._set_on_off_encoder(6, control)

    def set_encoder_6_display(self, command):
        self._set_display_command("encoder_6", command)

    def set_encoder_7(self, control):
        self._set_on_off_encoder(7, control)

    def set_encoder_7_display(self, command):
        self._set_display_command("encoder_7", command)

    def set_encoder_8(self, control):
        self._set_parameter_control("encoder_8", control)

    def set_encoder_8_display(self, command):
        self._set_display_command("encoder_8", command)

    def set_encoder_9(self, control):
        self._set_parameter_control("encoder_9", control)

    def set_encoder_9_display(self, command):
        self._set_display_command("encoder_9", command)

    def set_encoder_11(self, control):
        self._set_parameter_control("encoder_11", control)

    def set_encoder_11_display(self, command):
        self._set_display_command("encoder_11", command)

    def set_encoder_12(self, control):
        self._set_parameter_control("encoder_12", control)

    def set_encoder_12_display(self, command):
        self._set_display_command("encoder_12", command)

    def set_encoder_13(self, control):
        self._set_parameter_control("encoder_13", control)

    def set_encoder_13_display(self, command):
        self._set_display_command("encoder_13", command)

    def set_encoder_14(self, control):
        self._set_parameter_control("encoder_14", control)

    def set_encoder_14_display(self, command):
        self._set_display_command("encoder_14", command)

    def set_encoder_15(self, control):
        self._set_parameter_control("encoder_15", control)

    def set_encoder_15_display(self, command):
        self._set_display_command("encoder_15", command)

    def set_encoder_16(self, control):
        self._set_parameter_control("encoder_16", control)

    def set_encoder_16_display(self, command):
        self._set_display_command("encoder_16", command)

    def set_encoder_17(self, control):
        self._set_parameter_control("encoder_17", control)

    def set_encoder_17_display(self, command):
        self._set_display_command("encoder_17", command)

    def set_encoder_19(self, control):
        self._set_parameter_control("encoder_19", control)

    def set_encoder_19_display(self, command):
        self._set_display_command("encoder_19", command)

    def set_encoder_20(self, control):
        self._set_parameter_control("encoder_20", control)

    def set_encoder_20_display(self, command):
        self._set_display_command("encoder_20", command)

    def set_encoder_21(self, control):
        self._set_parameter_control("encoder_21", control)

    def set_encoder_21_display(self, command):
        self._set_display_command("encoder_21", command)

    def set_encoder_22(self, control):
        self._set_parameter_control("encoder_22", control)

    def set_encoder_22_display(self, command):
        self._set_display_command("encoder_22", command)

    def set_encoder_23(self, control):
        self._set_parameter_control("encoder_23", control)

    def set_encoder_23_display(self, command):
        self._set_display_command("encoder_23", command)

    def set_encoder_24(self, control):
        self._set_parameter_control("encoder_24", control)

    def set_encoder_24_display(self, command):
        self._set_display_command("encoder_24", command)

    def set_fader_1(self, control):
        self._set_parameter_control("fader_1", control)

    def set_fader_1_display(self, command):
        self._set_display_command("fader_1", command)

    def set_fader_3(self, control):
        self._set_parameter_control("fader_3", control)

    def set_fader_3_display(self, command):
        self._set_display_command("fader_3", command)

    def set_fader_4(self, control):
        self._set_parameter_control("fader_4", control)

    def set_fader_4_display(self, command):
        self._set_display_command("fader_4", command)

    def set_fader_5(self, control):
        self._set_parameter_control("fader_5", control)

    def set_fader_5_display(self, command):
        self._set_display_command("fader_5", command)

    def set_fader_6(self, control):
        self._set_parameter_control("fader_6", control)

    def set_fader_6_display(self, command):
        self._set_display_command("fader_6", command)

    def set_fader_7(self, control):
        self._set_parameter_control("fader_7", control)

    def set_fader_7_display(self, command):
        self._set_display_command("fader_7", command)

    def set_fader_8(self, control):
        self._set_parameter_control("fader_8", control)

    def set_fader_8_display(self, command):
        self._set_display_command("fader_8", command)

    def _set_submode_switch_encoder(self, control):
        name = "encoder_1"
        previous = self._controls.get(name)
        if previous is control:
            return
        if self._submode_switch_slot is not None:
            self._submode_switch_slot.disconnect()
            self._submode_switch_slot = None
        self._release_parameter_control(name, previous)
        self._controls[name] = control
        if control is not None:
            self._submode_switch_slot = self.register_slot(
                control,
                self._on_submode_switch_encoder_value,
                "value",
            )
        self._update_submode_switch_encoder_led(force=True)

    def _update_assignments(self):
        if not self._active:
            return
        for name in tuple(self._controls):
            if name == "encoder_1":
                continue
            if not name.startswith("encoder_") or int(name.split("_")[1]) not in ON_OFF_ENCODER_DEVICES:
                self._update_parameter_assignment(name)
        for encoder_number in ON_OFF_ENCODER_DEVICES:
            self._update_on_off_encoder_led(encoder_number, force=True)

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
        if self._is_parameter_encoder_control(name) and is_handled_special_parameter(parameter):
            self._connected_parameters[name] = parameter
            self._connected_parameter_signatures[name] = parameter_signature
            self._set_manual_led_parameter(control, parameter)
            self._log_parameter_assignment(name, parameter)
            self._update_parameter_encoder_led(name, parameter, force=True)
            return
        try:
            control.connect_to(parameter)
        except RuntimeError:
            return
        self._connected_parameters[name] = parameter
        self._connected_parameter_signatures[name] = parameter_signature
        self._log_parameter_assignment(name, parameter)

    def _release_parameter_control(self, name, control):
        parameter = self._connected_parameters.get(name)
        self._connected_parameters.pop(name, None)
        self._connected_parameter_signatures.pop(name, None)
        self._special_parameter_input_accumulators.pop(name, None)
        if control is None:
            return
        if parameter is not None:
            self._clear_manual_led_parameter(control, parameter)
        try:
            control.release_parameter()
        except (AttributeError, RuntimeError):
            pass

    def _release_all_parameter_controls(self):
        for name, control in tuple(self._controls.items()):
            self._release_parameter_control(name, control)

    def _set_manual_led_parameter(self, control, parameter):
        try:
            control.set_manual_led_parameter(parameter)
        except (AttributeError, RuntimeError):
            pass

    def _clear_manual_led_parameter(self, control, parameter=None):
        try:
            control.clear_manual_led_parameter(parameter)
        except (AttributeError, RuntimeError):
            pass

    def _set_manual_led_rgb(self, control, rgb, force=False):
        try:
            control.set_manual_led_rgb(rgb, force=force)
            return True
        except (AttributeError, RuntimeError):
            return False

    def _clear_manual_led_rgb(self, control):
        if control is None:
            return
        try:
            control.clear_manual_led_rgb()
        except (AttributeError, RuntimeError):
            pass

    def _is_parameter_encoder_control(self, name):
        if not name.startswith("encoder_"):
            return False
        try:
            encoder_number = int(name.split("_")[1])
        except (IndexError, TypeError, ValueError):
            return False
        return encoder_number not in ON_OFF_ENCODER_DEVICES

    def _is_encoder_control(self, name):
        return name.startswith("encoder_")

    def _is_parameter_display_control(self, name):
        return self._is_parameter_encoder_control(name) or name.startswith("fader_")

    def _on_parameter_encoder_value(self, name, value):
        self._on_parameter_control_value(name, value)

    def _on_parameter_control_value(self, name, value):
        if not self._active:
            return
        if self._is_encoder_control(name) and value == 64:
            return
        parameter = self._connected_parameters.get(name)
        if parameter is None:
            if name == "encoder_22":
                try:
                    LOGGER.info("LCXL3 mixing parameter encoder input without assignment: control=%s value=%s", name, value)
                except Exception:
                    pass
            return
        if not self._is_parameter_encoder_control(name):
            self._display_parameter(name, parameter)
            return
        if value == 64:
            return
        should_log = self._should_log_parameter(name, parameter)
        before_value = self._parameter_value(parameter) if should_log else None
        if should_log:
            try:
                LOGGER.info(
                    "LCXL3 mixing parameter encoder input: control=%s value=%s before=%s info=%s",
                    name,
                    value,
                    before_value,
                    parameter_debug_info(parameter),
                )
            except Exception:
                pass
        if not self._special_parameter_input_is_ready(name, value, parameter):
            self._display_parameter(name, parameter)
            return
        handled = handle_special_parameter_input(parameter, value)
        if handled:
            after_value = self._parameter_value(parameter)
            if should_log:
                try:
                    LOGGER.info(
                        "LCXL3 mixing special parameter handled: control=%s value=%s before=%s after=%s info=%s",
                        name,
                        value,
                        before_value,
                        after_value,
                        parameter_debug_info(parameter),
                    )
                except Exception:
                    pass
            control = self._controls.get(name)
            try:
                control._parameter_value_changed()
            except (AttributeError, RuntimeError):
                pass
            self._update_parameter_encoder_led(name, parameter, force=True)
            self._display_parameter(name, parameter)
        elif should_log:
            try:
                LOGGER.info(
                    "LCXL3 mixing special parameter not matched: control=%s value=%s info=%s",
                    name,
                    value,
                    parameter_debug_info(parameter),
                )
            except Exception:
                pass
            self._display_parameter(name, parameter)
        else:
            self._display_parameter(name, parameter)

    def _special_parameter_input_is_ready(self, name, value, parameter):
        threshold = special_parameter_step_threshold(parameter)
        if threshold <= 1:
            return True
        direction = self._relative_input_direction(value)
        if direction == 0:
            return False
        accumulator = self._special_parameter_input_accumulators.get(name, 0)
        if accumulator and (accumulator > 0) != (direction > 0):
            accumulator = 0
        accumulator += direction
        if abs(accumulator) >= threshold:
            self._special_parameter_input_accumulators[name] = 0
            return True
        self._special_parameter_input_accumulators[name] = accumulator
        return False

    def _relative_input_direction(self, value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            return 0
        if value > 64:
            return 1
        if value < 64:
            return -1
        return 0

    def _should_log_parameter(self, name, parameter):
        return name == "encoder_22" or is_special_parameter_candidate(parameter)

    def _parameter_value(self, parameter):
        try:
            return getattr(parameter, "value")
        except (AttributeError, RuntimeError):
            return None

    def _on_submode_switch_encoder_value(self, value, *a):
        if not self._active:
            return
        if value == 64:
            return
        self._set_loopcloud_metric_submode(METRIC_AB_SUBMODE if value > 64 else LOOPCLOUD_SUBMODE)

    def _set_loopcloud_metric_submode(self, submode):
        submode = METRIC_AB_SUBMODE if submode == METRIC_AB_SUBMODE else LOOPCLOUD_SUBMODE
        if submode == self._loopcloud_metric_submode:
            self._update_submode_switch_encoder_led(force=True)
            self._display_loopcloud_metric_submode()
            return
        self._loopcloud_metric_submode = submode
        for name in METRIC_AB_PARAMETER_CONTROLS:
            self._update_parameter_assignment(name, force=True)
        self._update_submode_switch_encoder_led(force=True)
        self._display_loopcloud_metric_submode()

    def _display_loopcloud_metric_submode(self):
        send_display(
            self._display_commands.get("encoder_1"),
            (
                "Mode",
                self._loopcloud_metric_submode_display_name(),
                "",
            ),
            trigger=True,
        )

    def _loopcloud_metric_submode_display_name(self):
        return "MetricAB" if self._loopcloud_metric_submode == METRIC_AB_SUBMODE else "Loopcloud"

    def _parameter_signature(self, name, parameter):
        if not self._parameter_is_enabled(parameter):
            return None
        track = self._display_track_for_control(name)
        device = self._parameter_device(parameter)
        return (
            name,
            self._track_index(track),
            self._object_name(track),
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
        try:
            if track == self.song.master_track:
                return "master"
        except (AttributeError, RuntimeError):
            pass
        return None

    def _object_attr(self, obj, attr):
        try:
            return str(getattr(obj, attr, ""))
        except (AttributeError, RuntimeError):
            return ""

    def _parameter_attr(self, parameter, attr):
        try:
            return getattr(parameter, attr)
        except (AttributeError, RuntimeError):
            return None

    def _log_parameter_assignment(self, name, parameter):
        if not self._should_log_parameter(name, parameter):
            return
        info = parameter_debug_info(parameter)
        signature = (
            info.get("parameter_name"),
            info.get("device_name"),
            info.get("device_class_name"),
            info.get("device_class_display_name"),
            info.get("min"),
            info.get("max"),
            info.get("value_items_count"),
            info.get("allowed_indexes"),
            info.get("matched"),
        )
        if self._logged_parameter_assignments.get(name) == signature:
            return
        self._logged_parameter_assignments[name] = signature
        try:
            LOGGER.info("LCXL3 mixing parameter assignment: control=%s info=%s", name, info)
        except Exception:
            pass

    def _update_parameter_encoder_led(self, name, parameter, force=False):
        control = self._controls.get(name)
        if control is None or parameter is None:
            return
        try:
            control_index = control.message_identifier() - 64
        except (AttributeError, RuntimeError):
            return
        self._led_sender.send_rgb(
            control,
            encoder_rgb_for_parameter(parameter, is_device_parameter=True),
            control_index=control_index,
            force=force,
        )

    def _parameter_for_control(self, name):
        track = selected_track(self.song)
        loopcloud = first_named_track(self.song, "Loopcloud")
        if name == "encoder_1":
            return None
        if self._loopcloud_metric_submode == METRIC_AB_SUBMODE and name in METRIC_AB_PARAMETER_CONTROLS:
            return self._metric_ab_parameter(METRIC_AB_PARAMETER_CONTROLS[name])
        if name == "encoder_8":
            return self._cue_parameter()
        if name == "encoder_9":
            return self._device_parameter(loopcloud, 2, 2)
        if name == "encoder_11":
            return self._device_parameter(track, 4, 3)
        if name == "encoder_12":
            return self._device_parameter(track, 5, 3)
        if name == "encoder_13":
            return self._device_parameter(track, 6, 3)
        if name == "encoder_14":
            return self._device_parameter(track, 7, 3)
        if name == "encoder_15":
            return self._device_parameter(track, 9, 3)
        if name == "encoder_16":
            return self._send_parameter(track, 1)
        if name == "encoder_17":
            return self._device_parameter(loopcloud, 2, 1)
        if name == "encoder_19":
            return self._device_parameter(track, 4, 2)
        if name == "encoder_20":
            return self._device_parameter(track, 5, 2)
        if name == "encoder_21":
            return self._device_parameter(track, 6, 2)
        if name == "encoder_22":
            return self._device_parameter(track, 7, 2)
        if name == "encoder_23":
            return self._device_parameter(track, 9, 2)
        if name == "encoder_24":
            return self._mixer_parameter(track, "panning")
        if name == "fader_1":
            return self._mixer_parameter(first_named_track(self.song, "Loopcloud"), "volume")
        if name == "fader_3":
            return self._device_parameter(track, 4, 1)
        if name == "fader_4":
            return self._device_parameter(track, 5, 1)
        if name == "fader_5":
            return self._device_parameter(track, 6, 1)
        if name == "fader_6":
            return self._device_parameter(track, 7, 1)
        if name == "fader_7":
            return self._device_parameter(track, 9, 1)
        if name == "fader_8":
            return self._mixer_parameter(track, "volume")
        return None

    def _on_on_off_encoder_value(self, encoder_number, value):
        if not self._active:
            return
        if value == 64:
            return
        parameter = self.device_on_parameter(ON_OFF_ENCODER_DEVICES[encoder_number])
        if not self._parameter_is_enabled(parameter):
            return
        try:
            parameter.value = parameter.max if value > 64 else parameter.min
        except (AttributeError, RuntimeError, ValueError):
            return
        self._update_on_off_encoder_led(encoder_number, force=True)
        self._display_parameter("encoder_{}".format(encoder_number), parameter)

    def _display_parameter(self, control_name, parameter):
        if not self._parameter_is_enabled(parameter):
            return
        send_display(
            self._display_commands.get(control_name),
            (
                self._display_header(control_name, parameter),
                self._object_name(parameter) or "-",
                self._parameter_value_text(parameter) or "-",
            ),
            trigger=True,
        )

    def _display_header(self, control_name, parameter):
        device = self._parameter_device(parameter)
        if liveobj_valid(device):
            return self._object_name(device) or "-"
        track = self._display_track_for_control(control_name)
        if liveobj_valid(track):
            return self._object_name(track) or "-"
        return "-"

    def _parameter_device(self, parameter):
        parent = getattr(parameter, "canonical_parent", None)
        if parent is None:
            return None
        if any(hasattr(parent, attr) for attr in ("parameters", "class_name", "class_display_name")):
            return parent
        return None

    def _display_track_for_control(self, control_name):
        if self._loopcloud_metric_submode == METRIC_AB_SUBMODE and control_name in METRIC_AB_PARAMETER_CONTROLS:
            try:
                return self.song.master_track
            except (AttributeError, RuntimeError):
                return None
        if control_name == "fader_1":
            return first_named_track(self.song, "Loopcloud")
        if control_name == "encoder_8":
            try:
                return self.song.master_track
            except (AttributeError, RuntimeError):
                return None
        return selected_track(self.song)

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

    def _update_on_off_encoder_led(self, encoder_number, force=False):
        if not self._active:
            return
        control = self._controls.get("encoder_{}".format(encoder_number))
        if control is None:
            return
        parameter = self.device_on_parameter(ON_OFF_ENCODER_DEVICES[encoder_number])
        rgb = device_toggle_encoder_rgb(
            encoder_number,
            self._device_toggle_state(parameter) if self._parameter_is_enabled(parameter) else None,
        )
        try:
            control_index = control.message_identifier() - 64
        except (AttributeError, RuntimeError):
            return
        manual_sent = self._set_manual_led_rgb(control, rgb, force=force)
        if not manual_sent:
            self._led_sender.send_rgb(control, rgb, control_index=control_index, force=force)

    def _update_submode_switch_encoder_led(self, force=False):
        if not self._active:
            return
        control = self._controls.get("encoder_1")
        if control is None:
            return
        rgb = loopcloud_metric_submode_rgb(self._loopcloud_metric_submode == METRIC_AB_SUBMODE)
        try:
            control_index = control.message_identifier() - 64
        except (AttributeError, RuntimeError):
            return
        manual_sent = self._set_manual_led_rgb(control, rgb, force=force)
        if not manual_sent:
            self._led_sender.send_rgb(control, rgb, control_index=control_index, force=force)

    def _device_toggle_state(self, parameter):
        try:
            midpoint = parameter.min + ((parameter.max - parameter.min) / 2.0)
            return parameter.value > midpoint
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    def device_on_parameter(self, device_number):
        track = selected_track(self.song)
        parameters = self._cached_raw_device_parameters(track, device_number)
        for parameter in parameters:
            try:
                if liveobj_valid(parameter) and parameter.name == DEVICE_ON_PARAMETER_NAME:
                    return parameter
            except RuntimeError:
                continue
        return None

    def _device(self, track, device_number):
        if not liveobj_valid(track) or device_number < 1:
            return None
        try:
            devices = tuple(track.devices)
        except (AttributeError, RuntimeError):
            return None
        index = device_number - 1
        return devices[index] if index < len(devices) and liveobj_valid(devices[index]) else None

    def _device_parameter(self, track, device_number, parameter_number):
        if parameter_number < 1:
            return None
        parameters = self._cached_ordered_device_parameters(track, device_number)
        index = parameter_number - 1
        return parameters[index] if index < len(parameters) else None

    def _metric_ab_parameter(self, parameter_number):
        if parameter_number < 1:
            return None
        device = self._metric_ab_device()
        if not liveobj_valid(device):
            return None
        parameters = self._ordered_device_parameters(device)
        index = parameter_number - 1
        return parameters[index] if index < len(parameters) else None

    def _metric_ab_device(self):
        try:
            devices = tuple(self.song.master_track.devices)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        for device in devices:
            if not liveobj_valid(device):
                continue
            try:
                if device.name == METRIC_AB_DEVICE_NAME:
                    return device
            except (AttributeError, RuntimeError):
                continue
        return None

    def _cached_raw_device_parameters(self, track, device_number):
        entry = self._device_parameter_cache_entry(track, device_number)
        return entry[0] if entry is not None else ()

    def _cached_ordered_device_parameters(self, track, device_number):
        entry = self._device_parameter_cache_entry(track, device_number)
        return entry[1] if entry is not None else ()

    def _device_parameter_cache_entry(self, track, device_number):
        device = self._device(track, device_number)
        if not liveobj_valid(device) or device_number < 1:
            return None
        key = self._device_parameter_cache_key(track, device_number)
        signature = self._device_parameter_cache_signature(track, device_number, device)
        if key is None or signature is None:
            raw_parameters = self._raw_device_parameters(device)
            return raw_parameters, self._ordered_device_parameters_from_raw(device, raw_parameters)
        cached = self._device_parameter_cache.get(key)
        if cached is not None and cached[0] == signature:
            return cached[1], cached[2]
        raw_parameters = self._raw_device_parameters(device)
        ordered_parameters = self._ordered_device_parameters_from_raw(device, raw_parameters)
        self._device_parameter_cache[key] = (signature, raw_parameters, ordered_parameters)
        return raw_parameters, ordered_parameters

    def _clear_device_parameter_cache(self):
        self._device_parameter_cache = {}

    def _device_parameter_cache_key(self, track, device_number):
        if not liveobj_valid(track) or device_number < 1:
            return None
        return (self._track_index(track), self._object_name(track), device_number)

    def _device_parameter_cache_signature(self, track, device_number, device):
        if not liveobj_valid(track) or not liveobj_valid(device):
            return None
        device_count = None
        try:
            device_count = len(tuple(track.devices))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        return (
            self._track_index(track),
            self._object_name(track),
            device_number,
            device_count,
            self._object_name(device),
            self._object_attr(device, "class_name"),
            self._object_attr(device, "class_display_name"),
        )

    def _ordered_device_parameters(self, device):
        return self._ordered_device_parameters_from_raw(device, self._raw_device_parameters(device))

    def _raw_device_parameters(self, device):
        try:
            return tuple(device.parameters)
        except (AttributeError, RuntimeError):
            return ()

    def _ordered_device_parameters_from_raw(self, device, raw_parameters):
        parameters = tuple(parameter for parameter in raw_parameters if self._is_assignable_device_parameter(parameter))
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
                    "LCXL3 mixing custom order missing names: device=%s names=%s",
                    self._object_name(device),
                    ", ".join(str(name) for name in missing_requested_names),
                )
        except Exception:
            pass
        return ordered

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

    def _parameter_name(self, parameter):
        return getattr(parameter, "name", "") or ""

    def _is_assignable_device_parameter(self, parameter):
        if not liveobj_valid(parameter):
            return False
        return self._parameter_name(parameter) not in ("", DEVICE_ON_PARAMETER_NAME)

    def _send_parameter(self, track, send_number):
        if not liveobj_valid(track) or send_number < 1:
            return None
        try:
            sends = tuple(track.mixer_device.sends)
        except (AttributeError, RuntimeError):
            return None
        index = send_number - 1
        return sends[index] if index < len(sends) else None

    def _mixer_parameter(self, track, attribute):
        if not liveobj_valid(track):
            return None
        try:
            return getattr(track.mixer_device, attribute)
        except (AttributeError, RuntimeError):
            return None

    def _cue_parameter(self):
        try:
            return self.song.master_track.mixer_device.cue_volume
        except (AttributeError, RuntimeError):
            return None

    def _parameter_is_enabled(self, parameter):
        if not liveobj_valid(parameter):
            return False
        try:
            return bool(getattr(parameter, "is_enabled", True))
        except RuntimeError:
            return False

    def disconnect(self):
        for slot in tuple(self._on_off_slots.values()):
            slot.disconnect()
        self._on_off_slots = {}
        if self._submode_switch_slot is not None:
            self._submode_switch_slot.disconnect()
            self._submode_switch_slot = None
        for slot in tuple(self._parameter_encoder_slots.values()):
            slot.disconnect()
        self._parameter_encoder_slots = {}
        self._release_all_parameter_controls()
        self._clear_device_parameter_cache()
        try:
            super().disconnect()
        except AttributeError:
            pass
