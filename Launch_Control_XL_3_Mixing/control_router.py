from ableton.v3.control_surface import Component

ENCODER_COUNT = 24
FADER_COUNT = 8
TRACK_BUTTON_COUNT = 16


class ControlRouterComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._fixed_assignments = None
        self._instrument_assignments = None
        self._track_buttons = None
        self._parameter_controls = {}
        self._display_commands = {}
        self._track_button_controls = {}
        self._shift_button = None
        self._shift_slot = None
        self._shift_pressed = False
        self._encoder_touch_controls = {}
        self._encoder_touch_slots = {}
        self._locked = False
        self._on_activity = None
        self._activity_slots = {}

    def set_on_activity(self, callback):
        self._on_activity = callback

    def set_locked(self, locked):
        self._locked = bool(locked)
        for control in self._parameter_controls.values():
            self._call_target(control, "set_locked", self._locked, "control", "lock")
        self._forward_lock_state()

    def _forward_lock_state(self):
        for component in (self._fixed_assignments, self._instrument_assignments, self._track_buttons):
            self._call_target(component, "set_locked", self._locked, "component", "lock")

    def _record_activity(self, name, value):
        if self._locked or type(value) is not int or not 0 <= value <= 127:
            return
        if name.startswith("encoder_") and value == 64:
            return
        if name.startswith("button_") and value == 0:
            return
        if self._on_activity is not None:
            self._on_activity()

    def _set_activity_control(self, name, control):
        slot = self._activity_slots.pop(name, None)
        if slot is not None:
            slot.disconnect()
        if control is not None:
            self._activity_slots[name] = self.register_slot(
                control, lambda value, *a: self._record_activity(name, value), "value")

    def set_target_components(self, fixed_assignments=None, instrument_assignments=None, track_buttons=None):
        self._fixed_assignments = fixed_assignments
        self._instrument_assignments = instrument_assignments
        self._track_buttons = track_buttons
        self._forward_shift_state()
        self._forward_lock_state()
        self._forward_all()

    def set_shift_button(self, button):
        if button is self._shift_button:
            return
        if self._shift_slot is not None:
            self._shift_slot.disconnect()
        self._shift_button = button
        self._shift_slot = self.register_slot(button, self._on_shift_value, "value") if button is not None else None
        self._on_shift_value(0)

    def _on_shift_value(self, value):
        pressed = value > 0
        if self._shift_pressed == pressed:
            return
        self._shift_pressed = pressed
        # Guard element-level special handlers before changing parameter connections.
        for control in self._parameter_controls.values():
            self._set_control_shift_state(control, pressed)
        self._forward_shift_state()

    def _set_control_shift_state(self, control, pressed):
        self._call_target(control, "set_shift_pressed", pressed, "control", "shift")

    def _forward_shift_state(self):
        self._call_target(self._fixed_assignments, "set_shift_pressed", self._shift_pressed, "fixed", "shift")
        self._call_target(self._instrument_assignments, "set_shift_pressed", self._shift_pressed, "instrument", "shift")

    def _set_encoder_touch(self, name, button):
        if self._encoder_touch_controls.get(name) is button:
            return
        slot = self._encoder_touch_slots.pop(name, None)
        if slot is not None:
            slot.disconnect()
        self._encoder_touch_controls[name] = button
        if button is not None:
            self._encoder_touch_slots[name] = self.register_slot(
                button,
                lambda value, *a, _name=name: self._on_encoder_touch(_name, value),
                "value",
            )

    def _on_encoder_touch(self, name, value):
        if not self._shift_pressed or value <= 0:
            return
        self._record_activity(name, 65)
        # Shift+turn arrives on the hardware touch channel, without a value CC.
        self._call_target(self._fixed_assignments, "preview_encoder", name, "fixed", name)
        self._call_target(self._instrument_assignments, "preview_encoder", name, "instrument", name)

    def _set_parameter_control(self, name, control):
        previous = self._parameter_controls.get(name)
        if previous is control:
            return
        self._set_control_shift_state(previous, False)
        self._call_target(previous, "set_locked", False, "control", "lock")
        self._call_target(previous, "set_on_activity", None, "control", "activity")
        self._set_control_shift_state(control, self._shift_pressed)
        self._call_target(control, "set_locked", self._locked, "control", "lock")
        self._call_target(control, "set_on_activity", lambda value: self._record_activity(name, value),
                          "control", "activity")
        self._parameter_controls[name] = control
        self._set_activity_control(name, control)
        self._forward_parameter_control(name)

    def _set_display_command(self, name, command):
        previous = self._display_commands.get(name)
        if previous is command:
            return
        self._display_commands[name] = command
        self._forward_display_command(name)

    def _set_track_button(self, index, button):
        previous = self._track_button_controls.get(index)
        if previous is button:
            return
        self._track_button_controls[index] = button
        self._set_activity_control("button_{}".format(index), button)
        self._forward_track_button(index)

    def _forward_all(self):
        for name in tuple(self._parameter_controls):
            self._forward_parameter_control(name)
        for name in tuple(self._display_commands):
            self._forward_display_command(name)
        for index in tuple(self._track_button_controls):
            self._forward_track_button(index)

    def _forward_parameter_control(self, name):
        control = self._parameter_controls.get(name)
        self._call_target(self._fixed_assignments, "set_{}".format(name), control, "fixed", name)
        self._call_target(self._instrument_assignments, "set_{}".format(name), control, "instrument", name)

    def _forward_display_command(self, name):
        command = self._display_commands.get(name)
        method_name = "set_{}_display".format(name)
        self._call_target(self._fixed_assignments, method_name, command, "fixed", "{}_display".format(name))
        self._call_target(
            self._instrument_assignments,
            method_name,
            command,
            "instrument",
            "{}_display".format(name),
        )

    def _forward_track_button(self, index):
        button = self._track_button_controls.get(index)
        self._call_target(
            self._track_buttons,
            "set_track_button_{}".format(index),
            button,
            "track_buttons",
            "track_button_{}".format(index),
        )
        self._call_target(
            self._instrument_assignments,
            "set_button_{}".format(index),
            button,
            "instrument",
            "button_{}".format(index),
        )

    def _call_target(self, target, method_name, value, target_name, label):
        if target is None:
            return
        try:
            method = getattr(target, method_name)
        except AttributeError:
            return
        try:
            method(value)
        except RuntimeError:
            pass

    def disconnect(self):
        for slot in self._activity_slots.values():
            slot.disconnect()
        self._activity_slots.clear()
        if self._shift_slot is not None:
            self._shift_slot.disconnect()
            self._shift_slot = None
        for slot in self._encoder_touch_slots.values():
            slot.disconnect()
        self._encoder_touch_slots.clear()
        self._encoder_touch_controls.clear()
        for control in self._parameter_controls.values():
            self._set_control_shift_state(control, False)
            self._call_target(control, "set_on_activity", None, "control", "activity")
        super().disconnect()


def _make_parameter_control_setter(name):
    def _setter(self, control):
        self._set_parameter_control(name, control)

    return _setter


def _make_display_setter(name):
    def _setter(self, command):
        self._set_display_command(name, command)

    return _setter


def _make_encoder_touch_setter(name):
    def _setter(self, button):
        self._set_encoder_touch(name, button)

    return _setter


def _make_track_button_setter(index):
    def _setter(self, button):
        self._set_track_button(index, button)

    return _setter


for _number in range(1, ENCODER_COUNT + 1):
    _name = "encoder_{}".format(_number)
    setattr(ControlRouterComponent, "set_{}".format(_name), _make_parameter_control_setter(_name))
    setattr(ControlRouterComponent, "set_{}_display".format(_name), _make_display_setter(_name))
    setattr(ControlRouterComponent, "set_{}_touch".format(_name), _make_encoder_touch_setter(_name))

for _number in range(1, FADER_COUNT + 1):
    _name = "fader_{}".format(_number)
    setattr(ControlRouterComponent, "set_{}".format(_name), _make_parameter_control_setter(_name))
    setattr(ControlRouterComponent, "set_{}_display".format(_name), _make_display_setter(_name))

for _number in range(1, TRACK_BUTTON_COUNT + 1):
    setattr(
        ControlRouterComponent,
        "set_track_button_{}".format(_number),
        _make_track_button_setter(_number),
    )
