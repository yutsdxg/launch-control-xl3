from Live.Device import Device
from Live.MixerDevice import MixerDevice
from ableton.v2.control_surface import LiveObjectDecorator
from ableton.v3.control_surface.elements import EncoderElement

from . import midi
from .colors import Theme, encoder_pan_rgb, encoder_rgb_for_parameter
from .special_parameters import _handle_saturn_band_1_style_input, _saturn_allowed_style_indexes


class ColoredEncoderElement(EncoderElement):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._led_control_index = self.message_identifier() - 64
        self._is_assigned_to_pan = False
        self._manual_led_parameter = None
        self._manual_led_rgb = None

    def reset(self):
        if self._manual_led_parameter is not None:
            self._send_led_for_parameter(self._manual_led_parameter)
        elif self._manual_led_rgb is not None:
            self._send_led_rgb(self._manual_led_rgb)
        else:
            self._send_led_rgb(Theme.OFF)

    def set_manual_led_parameter(self, parameter):
        self._manual_led_parameter = parameter
        self._manual_led_rgb = None
        self._is_assigned_to_pan = False
        self._send_led_for_parameter(parameter)

    def clear_manual_led_parameter(self, parameter=None):
        if parameter is None or parameter is self._manual_led_parameter:
            self._manual_led_parameter = None

    def set_manual_led_rgb(self, rgb, force=False):
        self._manual_led_rgb = rgb
        self._manual_led_parameter = None
        self._is_assigned_to_pan = False
        if force:
            self._last_sent_message = None
        self._send_led_rgb(rgb)

    def clear_manual_led_rgb(self):
        self._manual_led_rgb = None

    def _update_parameter_listeners(self):
        self._is_assigned_to_pan = False
        if self._manual_led_parameter is not None and not self.is_mapped_to_parameter():
            self._send_led_for_parameter(self._manual_led_parameter)
        elif self._manual_led_rgb is not None and not self.is_mapped_to_parameter():
            self._send_led_rgb(self._manual_led_rgb)
        elif self.is_mapped_to_parameter():
            try:
                self._is_assigned_to_pan = self.mapped_object.name == "Track Panning"
            except (AttributeError, RuntimeError):
                self._is_assigned_to_pan = False
            self._send_led_for_parameter()
        else:
            self._send_led_rgb(Theme.OFF)
        super()._update_parameter_listeners()

    def _parameter_value_changed(self):
        if self.is_mapped_to_parameter():
            self._send_led_for_parameter()
        elif self._manual_led_parameter is not None:
            self._send_led_for_parameter(self._manual_led_parameter)
        elif self._manual_led_rgb is not None:
            self._send_led_rgb(self._manual_led_rgb)

    def _send_led_for_parameter(self, parameter=None):
        parameter = parameter or self.mapped_object
        if self._is_assigned_to_pan:
            self._send_led_rgb(encoder_pan_rgb(self.parameter_value))
            return
        parent = getattr(parameter, "canonical_parent", None)
        is_device_parameter = isinstance(parent, (Device, LiveObjectDecorator))
        if isinstance(parent, MixerDevice):
            is_device_parameter = False
        self._send_led_rgb(encoder_rgb_for_parameter(parameter, is_device_parameter=is_device_parameter))

    def _send_led_rgb(self, rgb):
        message = midi.make_rgb_led_message(self._led_control_index, rgb)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _handle_special_parameter_input(self, value):
        if not self.is_mapped_to_parameter():
            return False
        if _handle_saturn_band_1_style_input(self.mapped_object, value):
            self._parameter_value_changed()
            return True
        return False

    def receive_value(self, value):
        if self._handle_special_parameter_input(value):
            return
        super().receive_value(value)

    def notify_value(self, value):
        if self._handle_special_parameter_input(value):
            return
        super().notify_value(value)
