"""Bounded ranges retain fader travel and acknowledge actual parameter values."""

import importlib.util
from pathlib import Path
import struct
import unittest


PATH = Path(__file__).resolve().parents[1] / "Launch_Control_XL_3_Mixing/parameter_ranges.py"
SPEC = importlib.util.spec_from_file_location("parameter_ranges_under_test", PATH)
RANGES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RANGES)
effective_bounds = RANGES.effective_bounds
is_bounded = RANGES.is_bounded
ParameterRangeControl = RANGES.ParameterRangeControl


class Parameter:
    def __init__(self, value=0.75, minimum=0.0, maximum=1.0, items=()):
        self._value = value
        self.min, self.max = minimum, maximum
        self.is_quantized = bool(items)
        self.value_items = tuple(items)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, unused):
        raise AssertionError("Range calculations must not write parameters")

    def apply(self, value):
        self._value = value


def move(control, parameter, cc):
    target = control.input_target(cc)
    if target is not None:
        parameter.apply(target)
        control.applied(parameter.value)
    return target


class EffectiveBoundsTest(unittest.TestCase):
    def test_normalized_floor_maps_native_units_without_changing_parameter(self):
        parameter = Parameter(value=0.25)
        self.assertEqual(effective_bounds(parameter, {"min": 0.5}), (0.5, 1.0))
        self.assertEqual(parameter.value, 0.25)
        db = Parameter(value=0.0, minimum=-36.0, maximum=36.0)
        self.assertEqual(effective_bounds(db, {"min": 0.5}), (0.0, 36.0))

    def test_omitted_or_zero_floor_keeps_native_bounds(self):
        parameter = Parameter(minimum=-2.0, maximum=8.0)
        self.assertEqual(effective_bounds(parameter), (-2.0, 8.0))
        self.assertEqual(effective_bounds(parameter, {"min": 0}), (-2.0, 8.0))
        self.assertFalse(is_bounded(None))
        self.assertFalse(is_bounded({}))
        self.assertFalse(is_bounded({"min": 0}))
        self.assertTrue(is_bounded({"min": 0.5}))

    def test_quantized_floor_rounds_up_to_native_item_step(self):
        parameter = Parameter(value=0, maximum=7, items=tuple(range(8)))
        self.assertEqual(effective_bounds(parameter, {"min": 0.5}), (4.0, 7.0))
        fraction = Parameter(value=0, items=tuple(range(5)))
        self.assertEqual(effective_bounds(fraction, {"min": 0.3}), (0.5, 1.0))
        self.assertEqual(effective_bounds(fraction, {"min": 0.5}), (0.5, 1.0))

    def test_invalid_or_zero_width_ranges_are_unassigned(self):
        parameter = Parameter()
        for minimum in (-0.1, 1.0, 1.1, True, "0.5", None, float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(minimum=minimum):
                self.assertIsNone(effective_bounds(parameter, {"min": minimum}))
        self.assertIsNone(effective_bounds(parameter, "invalid"))
        self.assertIsNone(effective_bounds(None))
        for lower, upper in ((0, 0), (1, 0), (0, float("inf")), (float("nan"), 1), (-1e308, 1e308)):
            self.assertIsNone(effective_bounds(Parameter(minimum=lower, maximum=upper)))
        boolean = Parameter(value=0, items=("Off", "On"))
        self.assertIsNone(effective_bounds(boolean, {"min": 0.5}))


class ParameterRangeControlTest(unittest.TestCase):
    def setUp(self):
        self.parameter = Parameter()

    def control(self, *, relative=False, minimum=0.5, takeover="value_scaling"):
        return ParameterRangeControl(self.parameter, relative, minimum, takeover)

    def test_none_mode_maps_entire_fader_to_configured_range(self):
        control = self.control(takeover="none")
        self.assertEqual(move(control, self.parameter, 0), 0.5)
        self.assertAlmostEqual(move(control, self.parameter, 64), 0.5 + 0.5 * 64.0 / 127.0)
        self.assertEqual(move(control, self.parameter, 127), 1.0)

    def test_scaling_initial_input_anchors_and_up_down_follow_fractional_distance(self):
        control = self.control()
        self.assertIsNone(move(control, self.parameter, 20))
        self.assertEqual(self.parameter.value, 0.75)
        expected = 0.5 + 0.5 * (0.5 + (40 - 20) / 127.0 * 0.5 / (1 - 20 / 127.0))
        self.assertAlmostEqual(move(control, self.parameter, 40), expected)
        logical = (expected - 0.5) / 0.5
        expected = 0.5 + 0.5 * (logical + (30 - 40) / 127.0 * logical / (40 / 127.0))
        self.assertAlmostEqual(move(control, self.parameter, 30), expected)

    def test_scaling_reaches_both_endpoints_after_arbitrary_start(self):
        control = self.control()
        self.assertIsNone(move(control, self.parameter, 70))
        self.assertEqual(move(control, self.parameter, 127), 1.0)
        self.assertEqual(move(control, self.parameter, 0), 0.5)

    def test_scaling_anchors_again_after_external_parameter_change(self):
        control = self.control()
        move(control, self.parameter, 10)
        move(control, self.parameter, 20)
        self.parameter.apply(0.9)
        self.assertIsNone(move(control, self.parameter, 90))
        self.assertEqual(self.parameter.value, 0.9)
        self.assertGreater(move(control, self.parameter, 100), 0.9)

    def test_parameter_below_floor_clamps_only_on_input_then_scales(self):
        self.parameter.apply(0.2)
        control = self.control()
        self.assertEqual(self.parameter.value, 0.2)
        self.assertEqual(move(control, self.parameter, 30), 0.5)
        self.assertGreater(move(control, self.parameter, 40), 0.5)

    def test_pickup_waits_until_crossing_and_external_changes_rearm(self):
        control = self.control(takeover="pickup")
        self.assertIsNone(move(control, self.parameter, 10))
        self.assertIsNone(move(control, self.parameter, 50))
        self.assertAlmostEqual(move(control, self.parameter, 80), 0.5 + 0.5 * 80 / 127)
        self.assertAlmostEqual(move(control, self.parameter, 90), 0.5 + 0.5 * 90 / 127)
        self.parameter.apply(0.55)
        self.assertIsNone(move(control, self.parameter, 95))
        self.assertAlmostEqual(move(control, self.parameter, 0), 0.5)

    def test_pickup_can_capture_on_first_input_with_one_cc_tolerance(self):
        control = self.control(takeover="pickup")
        self.assertIsNotNone(move(control, self.parameter, 63))

    def test_relative_continuous_step_uses_effective_span_and_respects_floor(self):
        control = self.control(relative=True)
        self.assertAlmostEqual(move(control, self.parameter, 65), 0.75 + 0.5 / 127)
        self.parameter.apply(0.5)
        self.assertEqual(move(control, self.parameter, 63), 0.5)
        self.assertGreaterEqual(move(control, self.parameter, 0), 0.5)
        self.parameter.apply(0.2)
        self.assertGreaterEqual(move(control, self.parameter, 65), 0.5)

    def test_quantized_relative_uses_native_steps_and_snaps_floor_upward(self):
        self.parameter = Parameter(value=4.0, maximum=7.0, items=tuple(range(8)))
        control = self.control(relative=True)
        self.assertEqual(move(control, self.parameter, 63), 4.0)
        self.assertEqual(move(control, self.parameter, 65), 5.0)
        self.assertEqual(move(control, self.parameter, 127), 7.0)
        self.assertEqual(move(control, self.parameter, 0), 4.0)

    def test_quantized_scaling_keeps_substep_progress_after_noop_applications(self):
        self.parameter = Parameter(value=4.0, maximum=7.0, items=tuple(range(8)))
        control = self.control()
        self.assertIsNone(move(control, self.parameter, 0))
        values = [move(control, self.parameter, cc) for cc in range(1, 128)]
        self.assertEqual(values[0], 4.0)
        self.assertIn(5.0, values)
        self.assertIn(6.0, values)
        self.assertEqual(values[-1], 7.0)

    def test_quantized_none_mapping_never_emits_nonitem_values(self):
        self.parameter = Parameter(value=0.5, items=tuple(range(5)))
        control = self.control(minimum=0.3, takeover="none")
        values = [move(control, self.parameter, cc) for cc in range(128)]
        self.assertEqual(set(values), {0.5, 0.75, 1.0})

    def test_unexpected_applied_value_rearms_without_replaying_previous_motion(self):
        control = self.control()
        move(control, self.parameter, 10)
        self.assertIsNotNone(control.input_target(20))
        self.parameter.apply(0.6)
        control.applied(0.6)
        self.assertIsNone(move(control, self.parameter, 100))
        self.assertEqual(self.parameter.value, 0.6)

    def test_rejected_change_acknowledged_as_unchanged_does_not_queue_motion(self):
        control = self.control()
        move(control, self.parameter, 10)
        self.assertGreater(control.input_target(20), self.parameter.value)
        control.applied(self.parameter.value)
        self.assertIsNone(move(control, self.parameter, 30))
        self.assertEqual(self.parameter.value, 0.75)

    def test_float_readback_rounding_keeps_own_scaling_progress(self):
        control = self.control()
        move(control, self.parameter, 10)
        target = control.input_target(20)
        self.parameter.apply(target + 1e-8)
        control.applied(self.parameter.value)
        self.assertIsNotNone(move(control, self.parameter, 30))

    def test_narrow_range_float32_readback_does_not_rearm_after_each_move(self):
        float32 = lambda value: struct.unpack("<f", struct.pack("<f", value))[0]
        self.parameter.apply(float32(0.9995))
        control = self.control(minimum=0.999)
        self.assertIsNone(control.input_target(0))
        for value in range(1, 128):
            target = control.input_target(value)
            self.assertIsNotNone(target, value)
            self.parameter.apply(float32(target))
            control.applied(self.parameter.value)
        self.assertEqual(self.parameter.value, 1.0)

    def test_float32_floor_rounding_does_not_trap_scaling_below_lower_bound(self):
        float32 = lambda value: struct.unpack("<f", struct.pack("<f", value))[0]
        minimum = 0.99999
        self.parameter.apply(float32(minimum))
        self.assertLess(self.parameter.value, minimum)
        control = self.control(minimum=minimum)
        self.assertIsNone(control.input_target(0))
        for value in range(1, 128):
            target = control.input_target(value)
            self.assertIsNotNone(target, value)
            self.parameter.apply(float32(target))
            control.applied(self.parameter.value)
        self.assertEqual(self.parameter.value, 1.0)

    def test_float32_precision_at_large_native_offset_keeps_virtual_motion(self):
        float32 = lambda value: struct.unpack("<f", struct.pack("<f", value))[0]
        self.parameter = Parameter(value=float32(1000009.5), minimum=1000000.0, maximum=1000010.0)
        control = self.control(minimum=0.9)
        self.assertIsNone(control.input_target(0))
        for value in range(1, 128):
            target = control.input_target(value)
            self.assertIsNotNone(target, value)
            self.parameter.apply(float32(target))
            control.applied(self.parameter.value)
        self.assertEqual(self.parameter.value, 1000010.0)

    def test_unacknowledged_failed_proposal_is_discarded(self):
        control = self.control()
        move(control, self.parameter, 10)
        self.assertIsNotNone(control.input_target(20))
        self.assertIsNone(move(control, self.parameter, 30))
        self.assertEqual(self.parameter.value, 0.75)

    def test_reset_and_native_range_changes_reanchor(self):
        control = self.control()
        move(control, self.parameter, 10)
        move(control, self.parameter, 20)
        control.reset()
        self.assertIsNone(move(control, self.parameter, 30))
        self.parameter.max = 2.0
        self.parameter.apply(1.5)
        self.assertIsNone(move(control, self.parameter, 40))

    def test_invalid_cc_and_neutral_relative_input_are_inert(self):
        for relative in (True, False):
            control = self.control(relative=relative)
            for value in (-1, 128, True, 1.0, None, "65"):
                self.assertIsNone(control.input_target(value))
            if relative:
                self.assertIsNone(control.input_target(64))
        self.assertEqual(self.parameter.value, 0.75)

    def test_invalid_parameter_values_minima_or_modes_produce_no_target(self):
        for minimum in (-1, 1, float("nan"), True, "0.5"):
            self.assertIsNone(self.control(minimum=minimum).input_target(50))
        self.assertIsNone(self.control(takeover="unknown").input_target(50))
        self.parameter.apply(float("nan"))
        self.assertIsNone(self.control().input_target(50))
        self.parameter.apply(float("inf"))
        self.assertIsNone(self.control().input_target(50))


if __name__ == "__main__":
    unittest.main()
