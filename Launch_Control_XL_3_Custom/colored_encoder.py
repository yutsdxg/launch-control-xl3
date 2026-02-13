from Live.Device import Device
from Live.MixerDevice import MixerDevice
from ableton.v2.control_surface import LiveObjectDecorator
from ableton.v3.control_surface.elements import EncoderElement
from ableton.v3.control_surface.midi import CC_STATUS, SYSEX_END
from .colors import Rgb

RGB_SYSEX_PREFIX = (240, 0, 32, 41, 2, 21, 1, 83)
DEVICE_VALUE_COLOR_BINS = (
    (72, 18, 112),   # low: purple
    (40, 44, 112),   # indigo
    (20, 70, 112),   # blue
    (10, 112, 38),   # green
    (72, 112, 12),   # yellow-green
    (112, 98, 10),   # yellow
    (112, 56, 10),   # orange
    (112, 18, 14),   # high: red
)
DEVICE_VALUE_COLOR_BIN_COUNT = 8


def _normalize_parameter_value(parameter):
    parameter_range = parameter.max - parameter.min
    if parameter_range <= 0:
        return 0.0
    normalized = (parameter.value - parameter.min) / parameter_range
    return min(max(normalized, 0.0), 1.0)


def _is_device_parameter(parameter):
    return isinstance(parameter.canonical_parent, (Device, LiveObjectDecorator))


def get_rgb_for_device_parameter_value(parameter):
    normalized = _normalize_parameter_value(parameter)
    bin_index = min(int(normalized * DEVICE_VALUE_COLOR_BIN_COUNT), DEVICE_VALUE_COLOR_BIN_COUNT - 1)
    return DEVICE_VALUE_COLOR_BINS[bin_index]


def get_color_for_parameter(parameter):
    if _is_device_parameter(parameter):
        return Rgb.WHITE
    parent = parameter.canonical_parent
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
            if _is_device_parameter(self.mapped_object):
                self._send_led_rgb(get_rgb_for_device_parameter_value(self.mapped_object))
            else:
                self._send_led_color(get_color_for_parameter(self.mapped_object))
        else:
            self._send_led_color(Rgb.OFF)
        super()._update_parameter_listeners()

    def _send_led_color(self, color):
        message = (CC_STATUS, self._led_color_cc, color.midi_value)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _send_led_rgb(self, rgb):
        r, g, b = rgb
        message = RGB_SYSEX_PREFIX + (self._led_color_cc, r, g, b, SYSEX_END)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _parameter_value_changed(self):
        if not self.is_mapped_to_parameter():
            return
        if self._is_assigned_to_pan:
            self._send_led_color(get_color_for_pan_value(self.parameter_value))
            return
        if _is_device_parameter(self.mapped_object):
            self._send_led_rgb(get_rgb_for_device_parameter_value(self.mapped_object))
            return
        self._send_led_color(get_color_for_parameter(self.mapped_object))
