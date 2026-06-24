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

    def set_target_components(self, fixed_assignments=None, instrument_assignments=None, track_buttons=None):
        self._fixed_assignments = fixed_assignments
        self._instrument_assignments = instrument_assignments
        self._track_buttons = track_buttons
        self._forward_all()

    def _set_parameter_control(self, name, control):
        previous = self._parameter_controls.get(name)
        if previous is control:
            return
        self._parameter_controls[name] = control
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


def _make_parameter_control_setter(name):
    def _setter(self, control):
        self._set_parameter_control(name, control)

    return _setter


def _make_display_setter(name):
    def _setter(self, command):
        self._set_display_command(name, command)

    return _setter


def _make_track_button_setter(index):
    def _setter(self, button):
        self._set_track_button(index, button)

    return _setter


for _number in range(1, ENCODER_COUNT + 1):
    _name = "encoder_{}".format(_number)
    setattr(ControlRouterComponent, "set_{}".format(_name), _make_parameter_control_setter(_name))
    setattr(ControlRouterComponent, "set_{}_display".format(_name), _make_display_setter(_name))

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
