import importlib.util
import sys
import types
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = WORKSPACE_ROOT / "Launch_Control_XL_3_Custom"


def _ensure_package():
    package = sys.modules.get("Launch_Control_XL_3_Custom")
    if package is None:
        package = types.ModuleType("Launch_Control_XL_3_Custom")
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules["Launch_Control_XL_3_Custom"] = package


def _load_module(module_name, relative_path):
    _ensure_package()
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

    v3_control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface", types.ModuleType("ableton.v3.control_surface")
    )
    v3_control_surface.__path__ = getattr(v3_control_surface, "__path__", [])

    elements = types.ModuleType("ableton.v3.control_surface.elements")

    class EncoderElement(object):
        pass

    elements.EncoderElement = EncoderElement
    sys.modules["ableton.v3.control_surface.elements"] = elements

    midi = types.ModuleType("ableton.v3.control_surface.midi")
    midi.CC_STATUS = 176
    midi.SYSEX_END = 247
    sys.modules["ableton.v3.control_surface.midi"] = midi

    colors = types.ModuleType("Launch_Control_XL_3_Custom.colors")

    class _Color(object):
        def __init__(self, midi_value):
            self.midi_value = midi_value

    class Rgb(object):
        OFF = _Color(0)
        WHITE = _Color(3)
        WHITE_HALF = _Color(1)
        LIGHT_BLUE = _Color(92)
        TURQUOISE = _Color(39)
        YELLOW = _Color(97)
        ORANGE = _Color(96)
        DARK_BLUE = _Color(47)

    colors.Rgb = Rgb
    sys.modules["Launch_Control_XL_3_Custom.colors"] = colors


_install_colored_encoder_stubs()
UTILS = _load_module("Launch_Control_XL_3_Custom.custom_parameter_utils", "custom_parameter_utils.py")
ORDER = _load_module("Launch_Control_XL_3_Custom.custom_parameter_order", "custom_parameter_order.py")
_load_module("Launch_Control_XL_3_Custom.custom_parameter_value_rules", "custom_parameter_value_rules.py")
COLORED = _load_module("Launch_Control_XL_3_Custom.colored_encoder", "colored_encoder.py")


class FakeDevice(object):
    def __init__(self, name, class_name=None, class_display_name=None):
        self.name = name
        self.class_name = class_name or name
        self.class_display_name = class_display_name or name


class FakeParameter(object):
    def __init__(self, name, value=0.0, min_value=-36.0, max_value=36.0, parent=None):
        self.name = name
        self.value = value
        self.min = min_value
        self.max = max_value
        self.canonical_parent = parent or FakeDevice("Pigments")


class ColoredEncoderValueRulesTest(unittest.TestCase):
    def test_pigments_coarse_rules_are_global_and_do_not_add_custom_bank_order(self):
        o1_key = UTILS.normalize_name("Analog 1 O1 Coarse")
        o2_key = UTILS.normalize_name("Analog 1 O2 Coarse")

        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o1_key]["step_size"], 12)
        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o2_key]["step_size"], 12)
        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o1_key]["display_min"], -36)
        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o2_key]["display_max"], 36)
        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o1_key]["input_mode"], "cc_bins")
        self.assertEqual(COLORED.GLOBAL_VALUE_RULES[o2_key]["input_resolution"], 128)
        self.assertNotIn("Pigments", ORDER.CUSTOM_DEVICE_PARAMETER_ORDER)

    def test_step_size_rule_moves_by_octaves_from_grid_values(self):
        parameter = FakeParameter("Analog 1 O1 Coarse", value=0.0)
        rule = COLORED._resolve_parameter_value_rule(parameter)

        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertEqual(parameter.value, 12.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, 0.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, -12.0)

    def test_step_size_rule_snaps_intermediate_values_directionally(self):
        rule = {"step_size": 12, "center": 0}

        parameter = FakeParameter("Analog 1 O1 Coarse", value=5.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertEqual(parameter.value, 12.0)

        parameter.value = 5.0
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, 0.0)

        parameter.value = -5.0
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertEqual(parameter.value, 0.0)

        parameter.value = -5.0
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, -12.0)

    def test_step_size_rule_handles_normalized_parameter_values_with_display_range(self):
        rule = {"step_size": 12, "center": 0, "display_min": -36, "display_max": 36}
        parameter = FakeParameter("Analog 1 O1 Coarse", value=0.5, min_value=0.0, max_value=1.0)

        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertAlmostEqual(parameter.value, 1.0 / 3.0)

        parameter.value = 0.5
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertAlmostEqual(parameter.value, 2.0 / 3.0)

    def test_step_size_rule_overrides_one_semitone_normalized_drift(self):
        rule = {"step_size": 12, "center": 0, "display_min": -36, "display_max": 36}
        one_semitone_above_center = 37.0 / 72.0
        one_semitone_below_center = 35.0 / 72.0

        parameter = FakeParameter(
            "Analog 1 O1 Coarse",
            value=one_semitone_above_center,
            min_value=0.0,
            max_value=1.0,
        )
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertAlmostEqual(parameter.value, 2.0 / 3.0)

        parameter.value = one_semitone_below_center
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertAlmostEqual(parameter.value, 1.0 / 3.0)

    def test_value_rule_input_threshold_holds_until_enough_ticks(self):
        rule = {
            "step_size": 12,
            "center": 0,
            "display_min": -36,
            "display_max": 36,
            "input_threshold": 4,
        }
        parameter = FakeParameter("Analog 1 O1 Coarse", value=0.5, min_value=0.0, max_value=1.0)
        accumulators = {}

        for _ in range(3):
            handled, direction = COLORED._handle_parameter_value_rule_input(
                parameter,
                65,
                rule,
                accumulators,
                "encoder-1",
            )
            self.assertTrue(handled)
            self.assertEqual(direction, 0)
            self.assertAlmostEqual(parameter.value, 0.5)

        handled, direction = COLORED._handle_parameter_value_rule_input(
            parameter,
            65,
            rule,
            accumulators,
            "encoder-1",
        )
        self.assertTrue(handled)
        self.assertEqual(direction, 1)
        self.assertAlmostEqual(parameter.value, 2.0 / 3.0)

    def test_value_rule_input_threshold_snaps_drift_while_waiting(self):
        rule = {
            "step_size": 12,
            "center": 0,
            "display_min": -36,
            "display_max": 36,
            "input_threshold": 4,
        }
        one_semitone_above_center = 37.0 / 72.0
        parameter = FakeParameter(
            "Analog 1 O1 Coarse",
            value=one_semitone_above_center,
            min_value=0.0,
            max_value=1.0,
        )

        handled, direction = COLORED._handle_parameter_value_rule_input(
            parameter,
            65,
            rule,
            {},
            "encoder-1",
        )

        self.assertTrue(handled)
        self.assertEqual(direction, 0)
        self.assertAlmostEqual(parameter.value, 0.5)

    def test_value_rule_cc_bins_divide_midi_cc_range_into_octave_zones(self):
        rule = {
            "step_size": 12,
            "center": 0,
            "display_min": -36,
            "display_max": 36,
            "input_mode": "cc_bins",
            "input_resolution": 128,
        }
        parameter = FakeParameter("Analog 1 O1 Coarse", value=0.5, min_value=0.0, max_value=1.0)
        accumulators = {}

        for _ in range(9):
            handled, direction = COLORED._handle_parameter_value_rule_input(
                parameter,
                65,
                rule,
                accumulators,
                "encoder-1",
            )
            self.assertTrue(handled)
            self.assertEqual(direction, 0)
            self.assertAlmostEqual(parameter.value, 0.5)

        handled, direction = COLORED._handle_parameter_value_rule_input(
            parameter,
            65,
            rule,
            accumulators,
            "encoder-1",
        )
        self.assertTrue(handled)
        self.assertEqual(direction, 1)
        self.assertAlmostEqual(parameter.value, 2.0 / 3.0)

    def test_value_rule_cc_bins_hold_current_zone_after_normal_mapping_drift(self):
        rule = {
            "step_size": 12,
            "center": 0,
            "display_min": -36,
            "display_max": 36,
            "input_mode": "cc_bins",
            "input_resolution": 128,
        }
        one_semitone_above_center = 37.0 / 72.0
        parameter = FakeParameter(
            "Analog 1 O1 Coarse",
            value=one_semitone_above_center,
            min_value=0.0,
            max_value=1.0,
        )

        handled, direction = COLORED._handle_parameter_value_rule_input(
            parameter,
            65,
            rule,
            {},
            "encoder-1",
        )

        self.assertTrue(handled)
        self.assertEqual(direction, 0)
        self.assertAlmostEqual(parameter.value, 0.5)

    def test_step_size_rule_respects_min_max_bounds(self):
        rule = {"step_size": 12, "center": 0}
        parameter = FakeParameter("Analog 1 O1 Coarse", value=36.0)

        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertEqual(parameter.value, 36.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, 24.0)

        parameter = FakeParameter("Analog 1 O1 Coarse", value=30.0, min_value=-30.0, max_value=30.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, 1, rule))
        self.assertEqual(parameter.value, 30.0)
        self.assertTrue(COLORED._step_parameter_by_value_rule(parameter, -1, rule))
        self.assertEqual(parameter.value, 24.0)

    def test_device_specific_value_rule_takes_priority_over_global_rule(self):
        old_device_rules = COLORED.VALUE_RULES_INDEX
        old_global_rules = COLORED.GLOBAL_VALUE_RULES
        try:
            COLORED.VALUE_RULES_INDEX = UTILS.build_device_value_rule_index(
                {"Pigments": {"Coarse": {"step_size": 12, "center": 0}}}
            )
            COLORED.GLOBAL_VALUE_RULES = UTILS.build_global_value_rule_index(
                {"Coarse": {"step_size": 1, "center": 0}}
            )

            parameter = FakeParameter("Coarse", parent=FakeDevice("Pigments"))
            self.assertEqual(COLORED._resolve_parameter_value_rule(parameter)["step_size"], 12)
        finally:
            COLORED.VALUE_RULES_INDEX = old_device_rules
            COLORED.GLOBAL_VALUE_RULES = old_global_rules

    def test_mode_count_stepping_still_works(self):
        parameter = FakeParameter("L Division", value=0.0, min_value=0.0, max_value=6.0)

        self.assertTrue(COLORED._step_parameter_by_mode_count(parameter, 1, 7))
        self.assertEqual(parameter.value, 1.0)


if __name__ == "__main__":
    unittest.main()
