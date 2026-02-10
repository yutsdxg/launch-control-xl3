from Live.Device import Device
from Live.MixerDevice import MixerDevice
from ableton.v2.control_surface import LiveObjectDecorator
from ableton.v3.control_surface.elements import EncoderElement
from ableton.v3.control_surface.midi import CC_STATUS
from .colors import Rgb

def get_color_for_parameter(parameter):
    parent = parameter.canonical_parent
    if isinstance(parent, (Device, LiveObjectDecorator)):
        return Rgb.PURPLE
    if isinstance(parent, MixerDevice):
        return Rgb.LIGHT_BLUE if parameter.name == 'Track Volume' else Rgb.TURQUOISE
    if "Loop" in parameter.name:
        return Rgb.YELLOW
    if "Vertical" in parameter.name:
        return Rgb.TURQUOISE
    if "Tempo" in parameter.name:
        return Rgb.ORANGE
    return Rgb.WHITE


def get_color_for_pan_value(value):
    if 'R' in value:
        return Rgb.ORANGE
    if "L" in value:
        return Rgb.DARK_BLUE
    return Rgb.WHITE_HALF


class ColoredEncoderElement(EncoderElement):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._led_color_cc = self.message_identifier() - 64
        self._is_assigned_to_pan = False

    def reset(self):
        self._send_led_color(Rgb.OFF)

    def _update_parameter_listeners(self):
        self._is_assigned_to_pan = False
        if self.is_mapped_to_parameter():
            self._is_assigned_to_pan = self.mapped_object.name == "Track Panning"
            if not self._is_assigned_to_pan:
                self._send_led_color(get_color_for_parameter(self.mapped_object))
        else:
            self._send_led_color(Rgb.OFF)
        super()._update_parameter_listeners()

    def _send_led_color(self, color):
        message = (CC_STATUS, self._led_color_cc, color.midi_value)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _parameter_value_changed(self):
        if self._is_assigned_to_pan:
            self._send_led_color(get_color_for_pan_value(self.parameter_value))
