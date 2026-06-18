import importlib.util
import sys
import types
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = WORKSPACE_ROOT / "Launch_Control_XL_3_Mixing"

SATURN_STYLE_ITEMS = (
    "Subtle Tube",
    "Clean Tube",
    "Warm Tube",
    "Broken Tube",
    "Subtle Tape",
    "Clean Tape",
    "Warm Tape",
    "Old Tape",
    "American Tweed Amp",
    "American Plexi Amp",
    "British Rock Amp",
    "British Pop Amp",
    "Smooth",
    "Crunchy",
    "Lead",
    "Screaming",
    "Power",
    "Subtle Saturation",
    "Gentle Saturation",
    "Heavy Saturation",
    "Subtle Transformer",
    "Gentle Transformer",
    "Warm Transformer",
    "Smudge",
    "Breakdown",
    "Foldback",
    "Rectify",
    "Destroy",
)


def _ensure_package():
    package = sys.modules.get("Launch_Control_XL_3_Mixing")
    if package is None:
        package = types.ModuleType("Launch_Control_XL_3_Mixing")
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules["Launch_Control_XL_3_Mixing"] = package


def _load_module(module_name, relative_path):
    _ensure_package()
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, PACKAGE_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _install_colored_encoder_stubs():
    live_root = types.ModuleType("Live")
    live_root.__path__ = []
    sys.modules["Live"] = live_root

    live_device = types.ModuleType("Live.Device")

    class Device(object):
        pass

    live_device.Device = Device
    sys.modules["Live.Device"] = live_device

    live_mixer = types.ModuleType("Live.MixerDevice")

    class MixerDevice(object):
        pass

    live_mixer.MixerDevice = MixerDevice
    sys.modules["Live.MixerDevice"] = live_mixer

    ableton = sys.modules.setdefault("ableton", types.ModuleType("ableton"))
    ableton.__path__ = getattr(ableton, "__path__", [])

    ableton_v2 = sys.modules.setdefault("ableton.v2", types.ModuleType("ableton.v2"))
    ableton_v2.__path__ = getattr(ableton_v2, "__path__", [])

    v2_control_surface = types.ModuleType("ableton.v2.control_surface")

    class LiveObjectDecorator(object):
        pass

    v2_control_surface.LiveObjectDecorator = LiveObjectDecorator
    sys.modules["ableton.v2.control_surface"] = v2_control_surface

    ableton_v3 = sys.modules.setdefault("ableton.v3", types.ModuleType("ableton.v3"))
    ableton_v3.__path__ = getattr(ableton_v3, "__path__", [])

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface",
        types.ModuleType("ableton.v3.control_surface"),
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    elements = types.ModuleType("ableton.v3.control_surface.elements")

    class EncoderElement(object):
        def __init__(self, *a, **k):
            self._mapped_object = None
            self._last_sent_message = None
            self.received_values = []
            self.notified_values = []
            self.sent_midi = []

        def message_identifier(self):
            return 78

        def is_mapped_to_parameter(self):
            return self._mapped_object is not None

        @property
        def mapped_object(self):
            return self._mapped_object

        @mapped_object.setter
        def mapped_object(self, value):
            self._mapped_object = value

        @property
        def parameter_value(self):
            return str(getattr(self._mapped_object, "value", ""))

        def receive_value(self, value):
            self.received_values.append(value)

        def notify_value(self, value):
            self.notified_values.append(value)

        def _update_parameter_listeners(self):
            pass

        def send_midi(self, message):
            self.sent_midi.append(message)

    elements.EncoderElement = EncoderElement
    sys.modules["ableton.v3.control_surface.elements"] = elements

    colors = types.ModuleType("Launch_Control_XL_3_Mixing.colors")

    class Theme(object):
        OFF = "off"
        DEVICE_ON = "device-on"
        DEVICE_OFF = "device-off"
        SOLO_ON = "solo-on"
        SOLO_MODIFIER_IDLE = "solo-idle"
        MUTE_MODIFIER_ON = "mute-on"
        MUTE_MODIFIER_IDLE = "mute-idle"

    colors.Theme = Theme
    colors.dim_track_rgb = lambda rgb: ("dim", rgb)
    colors.track_rgb = lambda track: track.rgb
    colors.encoder_pan_rgb = lambda value: ("pan", value)
    colors.encoder_rgb_for_parameter = lambda parameter, is_device_parameter=False: (
        "parameter",
        parameter.value,
        is_device_parameter,
    )
    sys.modules["Launch_Control_XL_3_Mixing.colors"] = colors

    midi = types.ModuleType("Launch_Control_XL_3_Mixing.midi")
    midi.make_rgb_led_message = lambda control_index, rgb: ("rgb", control_index, rgb)
    sys.modules["Launch_Control_XL_3_Mixing.midi"] = midi

    return Device


DEVICE_CLASS = _install_colored_encoder_stubs()
COLORED = _load_module("Launch_Control_XL_3_Mixing.colored_encoder", "colored_encoder.py")


class FakeDevice(DEVICE_CLASS):
    def __init__(self, name="Saturn 2", class_name=None, class_display_name=None):
        self.name = name
        self.class_name = class_name or name
        self.class_display_name = class_display_name or name
        self.parameters = ()


class FakeParameter(object):
    def __init__(
        self,
        name="Band 1 Style",
        value=2.0,
        minimum=0.0,
        maximum=None,
        parent=None,
        value_items=SATURN_STYLE_ITEMS,
    ):
        self.name = name
        self.value = value
        self.min = minimum
        self.max = float(len(SATURN_STYLE_ITEMS) - 1) if maximum is None else maximum
        self.canonical_parent = parent or FakeDevice()
        self.value_items = value_items


class MixingSaturnStyleEncoderTest(unittest.TestCase):
    def setUp(self):
        self.encoder = COLORED.ColoredEncoderElement()

    def _map_parameter(self, parameter):
        self.encoder.mapped_object = parameter

    def test_allowed_saturn_styles_are_resolved_from_value_items(self):
        parameter = FakeParameter()

        self.assertEqual(COLORED._saturn_allowed_style_indexes(parameter), (2, 6, 22))

    def test_saturn_band_1_style_steps_only_through_allowed_values(self):
        parameter = FakeParameter(value=2.0)
        self._map_parameter(parameter)

        self.encoder.receive_value(65)
        self.assertEqual(parameter.value, 6.0)
        self.encoder.receive_value(65)
        self.assertEqual(parameter.value, 22.0)
        self.encoder.receive_value(65)
        self.assertEqual(parameter.value, 22.0)
        self.encoder.receive_value(63)
        self.assertEqual(parameter.value, 6.0)
        self.encoder.receive_value(63)
        self.assertEqual(parameter.value, 2.0)
        self.encoder.receive_value(63)
        self.assertEqual(parameter.value, 2.0)
        self.assertEqual(self.encoder.received_values, [])

    def test_saturn_band_1_style_snaps_from_disallowed_value_by_direction(self):
        parameter = FakeParameter(value=5.0)
        self._map_parameter(parameter)

        self.encoder.receive_value(65)
        self.assertEqual(parameter.value, 6.0)
        parameter.value = 5.0
        self.encoder.receive_value(63)
        self.assertEqual(parameter.value, 2.0)
        parameter.value = 21.0
        self.encoder.notify_value(65)
        self.assertEqual(parameter.value, 22.0)
        parameter.value = 21.0
        self.encoder.notify_value(63)
        self.assertEqual(parameter.value, 6.0)
        self.assertEqual(self.encoder.received_values, [])
        self.assertEqual(self.encoder.notified_values, [])

    def test_saturn_band_1_style_uses_parameter_range_not_midi_cc_values(self):
        maximum = 1.0
        parameter = FakeParameter(
            value=2.0 / 27.0,
            minimum=0.0,
            maximum=maximum,
        )
        self._map_parameter(parameter)

        self.encoder.receive_value(65)

        self.assertAlmostEqual(parameter.value, 6.0 / 27.0)

    def test_saturn_band_1_style_uses_fallback_indexes_when_value_items_are_empty(self):
        parameter = FakeParameter(
            value=2.0 / 27.0,
            minimum=0.0,
            maximum=1.0,
            value_items=(),
        )
        self._map_parameter(parameter)

        self.encoder.receive_value(65)
        self.assertAlmostEqual(parameter.value, 6.0 / 27.0)
        self.encoder.receive_value(65)
        self.assertAlmostEqual(parameter.value, 22.0 / 27.0)

    def test_non_matching_target_falls_back_to_normal_encoder_mapping(self):
        parameter = FakeParameter(parent=FakeDevice("Operator"))
        self._map_parameter(parameter)

        self.encoder.receive_value(65)

        self.assertEqual(self.encoder.received_values, [65])
        self.assertEqual(parameter.value, 2.0)

    def test_missing_value_items_falls_back_to_normal_encoder_mapping(self):
        value_items = tuple(item for item in SATURN_STYLE_ITEMS if item != "Warm Transformer")
        parameter = FakeParameter(value_items=value_items)
        self._map_parameter(parameter)

        self.encoder.receive_value(65)

        self.assertEqual(self.encoder.received_values, [65])
        self.assertEqual(parameter.value, 2.0)

    def test_manual_led_parameter_prevents_unmapped_update_from_turning_led_off(self):
        parameter = FakeParameter(value=2.0)
        self.encoder.set_manual_led_parameter(parameter)
        parameter.value = 6.0
        self.encoder.sent_midi[:] = []

        self.encoder._update_parameter_listeners()

        self.assertEqual(
            self.encoder.sent_midi,
            [("rgb", 14, ("parameter", 6.0, True))],
        )

    def test_manual_led_rgb_prevents_unmapped_update_from_turning_led_off(self):
        self.encoder.set_manual_led_rgb(("device-toggle", 2, True))

        self.encoder._update_parameter_listeners()
        self.encoder.reset()
        self.encoder._parameter_value_changed()

        self.assertEqual(
            self.encoder.sent_midi,
            [("rgb", 14, ("device-toggle", 2, True))],
        )

    def test_clearing_manual_led_rgb_restores_unmapped_off_led(self):
        self.encoder.set_manual_led_rgb(("device-toggle", 2, True))
        self.encoder.clear_manual_led_rgb()

        self.encoder._update_parameter_listeners()

        self.assertEqual(
            self.encoder.sent_midi,
            [
                ("rgb", 14, ("device-toggle", 2, True)),
                ("rgb", 14, "off"),
            ],
        )

    def test_forced_manual_led_rgb_resends_current_value(self):
        self.encoder.set_manual_led_rgb(("device-toggle", 2, True))
        self.encoder.sent_midi[:] = []

        self.encoder.set_manual_led_rgb(("device-toggle", 2, True), force=True)

        self.assertEqual(
            self.encoder.sent_midi,
            [("rgb", 14, ("device-toggle", 2, True))],
        )

    def test_clearing_manual_led_parameter_restores_unmapped_off_led(self):
        parameter = FakeParameter(value=2.0)
        self.encoder.set_manual_led_parameter(parameter)
        self.encoder.clear_manual_led_parameter(parameter)
        self.encoder.sent_midi[:] = []

        self.encoder._update_parameter_listeners()

        self.assertEqual(self.encoder.sent_midi, [("rgb", 14, "off")])


if __name__ == "__main__":
    unittest.main()
