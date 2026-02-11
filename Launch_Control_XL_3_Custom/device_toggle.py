from ableton.v3.control_surface import Component
from ableton.v3.control_surface.controls import ButtonControl
from ableton.v3.live import liveobj_valid

TOGGLE_PARAMETER_START_INDEX = 22


class DeviceToggleComponent(Component):
    toggle_button_1 = ButtonControl()
    toggle_button_2 = ButtonControl()
    toggle_button_3 = ButtonControl()
    toggle_button_4 = ButtonControl()
    toggle_button_5 = ButtonControl()
    toggle_button_6 = ButtonControl()
    toggle_button_7 = ButtonControl()
    toggle_button_8 = ButtonControl()

    def set_toggle_button_1(self, button):
        self.toggle_button_1.set_control_element(button)

    def set_toggle_button_2(self, button):
        self.toggle_button_2.set_control_element(button)

    def set_toggle_button_3(self, button):
        self.toggle_button_3.set_control_element(button)

    def set_toggle_button_4(self, button):
        self.toggle_button_4.set_control_element(button)

    def set_toggle_button_5(self, button):
        self.toggle_button_5.set_control_element(button)

    def set_toggle_button_6(self, button):
        self.toggle_button_6.set_control_element(button)

    def set_toggle_button_7(self, button):
        self.toggle_button_7.set_control_element(button)

    def set_toggle_button_8(self, button):
        self.toggle_button_8.set_control_element(button)

    @toggle_button_1.pressed
    def toggle_button_1(self, _):
        self._toggle_parameter(0)

    @toggle_button_2.pressed
    def toggle_button_2(self, _):
        self._toggle_parameter(1)

    @toggle_button_3.pressed
    def toggle_button_3(self, _):
        self._toggle_parameter(2)

    @toggle_button_4.pressed
    def toggle_button_4(self, _):
        self._toggle_parameter(3)

    @toggle_button_5.pressed
    def toggle_button_5(self, _):
        self._toggle_parameter(4)

    @toggle_button_6.pressed
    def toggle_button_6(self, _):
        self._toggle_parameter(5)

    @toggle_button_7.pressed
    def toggle_button_7(self, _):
        self._toggle_parameter(6)

    @toggle_button_8.pressed
    def toggle_button_8(self, _):
        self._toggle_parameter(7)

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
        try:
            parameter.value = min_value if current > midpoint else max_value
        except RuntimeError:
            return

    def _parameter_for_offset(self, offset):
        selected_track = self.song.view.selected_track
        if not liveobj_valid(selected_track):
            return None
        selected_device = self._resolve_device_for_track(selected_track)
        if not liveobj_valid(selected_device):
            return None
        parameter_index = TOGGLE_PARAMETER_START_INDEX + offset
        try:
            parameters = tuple(selected_device.parameters)
        except RuntimeError:
            return None
        if parameter_index < len(parameters):
            return parameters[parameter_index]
        # Fallback: some interpretations number parameters excluding "Device On" (index 0).
        fallback_index = TOGGLE_PARAMETER_START_INDEX - 1 + offset
        if 0 <= fallback_index < len(parameters):
            return parameters[fallback_index]
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
