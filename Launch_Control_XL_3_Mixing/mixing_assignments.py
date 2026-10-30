"""Configuration-driven Mixing, independent of the legacy fixed assignments."""

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid

from .auto_bypass import device_is_off, input_target, set_device_enabled, should_bypass
from .display import send_display, send_locked_display, send_unassigned_display
from .mixing_config import MIXING_ASSIGNMENTS
from .mixing_targets import CONTROL_NAMES, MixingTargetResolver, validate_assignments
from .parameter_actions import apply_directional_on_off
from .saturator_compensation import SaturatorCompensationManager

ASSIGNMENT_UPDATE_INTERVAL = 0.1


class ConfiguredMixingAssignmentsComponent(Component):
    def __init__(self, *a, assignments=None, **k):
        super().__init__(*a, **k)
        self._active = True
        self._shift_pressed = False
        self._locked = False
        self._updating = False
        self._assignments = validate_assignments(MIXING_ASSIGNMENTS if assignments is None else assignments)
        self._resolver = MixingTargetResolver(self._update_assignments)
        self._saturator_compensation = SaturatorCompensationManager()
        self._controls = {}
        self._control_slots = {}
        self._display_commands = {}
        self._connected_parameters = {}
        self._connected_parameter_signatures = {}
        self._tasks.add(task.loop(task.sequence(
            task.run(self._update_assignments), task.delay(ASSIGNMENT_UPDATE_INTERVAL))))

    def set_midi_sender(self, _sender):
        # Encoder elements already own the value-based RGB output.
        self.refresh_led_feedback()

    def set_active(self, active):
        active = bool(active)
        if self._active == active:
            if active:
                self._update_assignments()
            return
        self._active = active
        if active:
            self._update_assignments()
        else:
            self._saturator_compensation.disconnect()
            self._release_all_parameter_controls()
            self._resolver.disconnect()

    def set_shift_pressed(self, pressed):
        pressed = bool(pressed)
        if self._shift_pressed != pressed:
            self._shift_pressed = pressed
            self._update_assignments(force=True)

    def set_locked(self, locked):
        locked = bool(locked)
        if self._locked != locked:
            self._locked = locked
            self._update_assignments(force=True)

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
                control, lambda value, *a: self._on_parameter_control_value(name, value), "value")
        self._update_assignments()

    def _set_display_command(self, name, command):
        self._display_commands[name] = command
        self._update_assignments()

    def _update_assignments(self, force=False, prepare_displays=True):
        if not self._active or self._updating:
            return
        self._updating = True
        try:
            self._resolver.refresh(self.song, self._assignments)
            for name in self._controls:
                self._update_parameter_assignment(name, force=force)
            self._saturator_compensation.refresh(
                self._resolver, self._assignments, self._controls,
                enabled=not self._shift_pressed and not self._locked)
            if prepare_displays:
                for name in self._display_commands:
                    self._prepare_control_display(name)
        finally:
            self._updating = False

    def _parameter_is_enabled(self, parameter):
        if not liveobj_valid(parameter):
            return False
        try:
            return bool(getattr(parameter, "is_enabled", True))
        except RuntimeError:
            return False

    def _manual_mapping(self, name):
        entry = self._assignments[name]
        return (self._shift_pressed or self._locked or bool(entry and entry.get("directional_on_off"))
                or self._bypassed_parameter(name, self._resolver.resolve(entry)))

    def _bypassed_parameter(self, name, parameter):
        entry = self._assignments[name]
        return bool(
            entry and entry.get("auto_bypass") and liveobj_valid(parameter)
            and not self._parameter_is_enabled(parameter)
            and self._parameter_is_enabled(self._resolver.device_on(entry))
            and device_is_off(self._resolver.device_on(entry))
        )

    def _parameter_is_available(self, name, parameter):
        return self._parameter_is_enabled(parameter) or self._bypassed_parameter(name, parameter)

    def _update_parameter_assignment(self, name, force=False):
        control = self._controls.get(name)
        entry = self._assignments[name]
        parameter = self._resolver.resolve(entry)
        if control is None or not self._parameter_is_available(name, parameter):
            self._release_parameter_control(name, control)
            return
        manual = self._manual_mapping(name)
        try:
            signature = (self._resolver.owner(entry), parameter, parameter.name, parameter.min, parameter.max, manual)
        except (AttributeError, RuntimeError):
            self._release_parameter_control(name, control)
            return
        if not force and signature == self._connected_parameter_signatures.get(name):
            if manual and name.startswith("encoder_"):
                self._refresh_encoder_led(control)
            return
        if manual:
            # Install the logical LED source before removing Live's mapping.
            try:
                if name.startswith("encoder_"):
                    control.set_manual_led_parameter(parameter)
                control.release_parameter()
            except (AttributeError, RuntimeError):
                return
        else:
            self._release_parameter_control(name, control)
            try:
                control.connect_to(parameter)
            except RuntimeError:
                return
        self._connected_parameters[name] = parameter
        self._connected_parameter_signatures[name] = signature

    def _release_parameter_control(self, name, control):
        # Inactive components must never release the other mode's native map.
        if name not in self._connected_parameters:
            return
        parameter = self._connected_parameters.pop(name)
        self._connected_parameter_signatures.pop(name, None)
        if control is not None:
            try:
                control.clear_manual_led_parameter(parameter)
            except (AttributeError, RuntimeError):
                pass
            try:
                control.release_parameter()
            except (AttributeError, RuntimeError):
                pass

    def _release_all_parameter_controls(self):
        for name, control in self._controls.items():
            self._release_parameter_control(name, control)

    def _refresh_encoder_led(self, control):
        try:
            control.refresh_manual_led_feedback()
        except (AttributeError, RuntimeError):
            pass

    def refresh_led_feedback(self):
        if self._active:
            for name, control in self._controls.items():
                if name.startswith("encoder_"):
                    self._refresh_encoder_led(control)

    def refresh_display_feedback(self):
        if self._active:
            for command in self._display_commands.values():
                try:
                    command.clear_send_cache()
                except (AttributeError, RuntimeError):
                    pass
            self._update_assignments()

    def _prepare_control_display(self, name, trigger=False):
        command = self._display_commands.get(name)
        if self._locked:
            send_locked_display(command, trigger=trigger)
            return
        parameter = self._resolver.resolve(self._assignments[name])
        if not self._parameter_is_available(name, parameter):
            send_unassigned_display(command, name, trigger=trigger)
            return
        entry = self._assignments[name]
        owner = self._resolver.owner(entry)
        try:
            lines = (owner.name, parameter.name, str(parameter))
        except (AttributeError, RuntimeError):
            send_unassigned_display(command, name, trigger=trigger)
            return
        send_display(command, lines, trigger=trigger)

    def preview_encoder(self, name):
        if self._active and name.startswith("encoder_") and name in self._controls:
            if self._locked or self._shift_pressed:
                self._update_assignments(prepare_displays=False)
                self._prepare_control_display(name, trigger=True)

    def _on_parameter_control_value(self, name, value):
        if not self._active or type(value) is not int or not 0 <= value <= 127:
            return
        if name.startswith("encoder_") and value == 64:
            return
        self._update_assignments(prepare_displays=False)
        if not self._locked and not self._shift_pressed:
            self._saturator_compensation.begin_input(name)
            try:
                entry = self._assignments[name]
                if entry and entry.get("directional_on_off"):
                    apply_directional_on_off(self._connected_parameters.get(name), value)
                    self._refresh_encoder_led(self._controls.get(name))
                elif entry and entry.get("auto_bypass"):
                    self._handle_auto_bypass_input(name, value)
            finally:
                self._saturator_compensation.end_input(name)
        self._prepare_control_display(name, trigger=True)

    def on_consumed_encoder_input(self, event):
        # Shared element handlers (e.g. Saturn) can apply a value before consuming
        # the MIDI event. Run the companion action without applying that value twice.
        name, value = event
        entry = self._assignments.get(name)
        if entry and entry.get("auto_bypass"):
            self._on_parameter_control_value(name, value)

    def _handle_auto_bypass_input(self, name, value):
        entry = self._assignments[name]
        parameter = self._connected_parameters.get(name)
        if not self._parameter_is_available(name, parameter):
            return
        if self._bypassed_parameter(name, parameter):
            relative = name.startswith("encoder_")
            target = input_target(parameter, value, relative)
            if target is None or should_bypass(parameter, entry["auto_bypass"]["off_at"], target):
                return
            if not set_device_enabled(self._resolver.device_on(entry), True):
                return
            if relative and self._parameter_is_enabled(parameter):
                try:
                    parameter.value = target
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
            # A disabled fader wakes the device without bypassing Live's takeover.
            # Its next input is handled by the native parameter map. No queued CC.
            self._update_assignments(prepare_displays=False)
            if not relative or not self._parameter_is_enabled(parameter):
                return
        self._apply_auto_bypass(entry)
        self._update_assignments(prepare_displays=False)

    def _apply_auto_bypass(self, entry):
        conditions = []
        for name, candidate in self._assignments.items():
            if candidate and candidate.get("auto_bypass") and candidate["device"] == entry["device"]:
                parameter = self._resolver.resolve(candidate)
                if not self._parameter_is_available(name, parameter):
                    continue
                condition = should_bypass(parameter, candidate["auto_bypass"]["off_at"])
                if condition is not None:
                    conditions.append(condition)
        if conditions:
            set_device_enabled(self._resolver.device_on(entry), not any(conditions))

    def disconnect(self):
        self._active = False
        self._saturator_compensation.disconnect()
        self._release_all_parameter_controls()
        self._resolver.disconnect()
        for slot in self._control_slots.values():
            slot.disconnect()
        self._control_slots.clear()
        super().disconnect()


def _control_setter(name):
    return lambda self, control: self._set_parameter_control(name, control)


def _display_setter(name):
    return lambda self, command: self._set_display_command(name, command)


for _name in CONTROL_NAMES:
    setattr(ConfiguredMixingAssignmentsComponent, "set_{}".format(_name), _control_setter(_name))
    setattr(ConfiguredMixingAssignmentsComponent, "set_{}_display".format(_name), _display_setter(_name))
