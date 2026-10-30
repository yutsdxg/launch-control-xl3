"""Auto bypass uses the configured range while Device On keeps its native range."""

import types
import unittest
from unittest.mock import patch

import test_mixing  # Install the same minimal Live stubs as the other tests.

from Launch_Control_XL_3_Mixing.auto_bypass import (
    device_is_off, input_target, normalized_value, set_device_enabled, should_bypass,
)


def parameter(value=0.5, minimum=0.0, maximum=1.0, items=()):
    return types.SimpleNamespace(
        value=value, min=minimum, max=maximum, is_enabled=True,
        is_quantized=bool(items), value_items=items)


class AutoBypassRangeTest(unittest.TestCase):
    def test_effective_minimum_is_bypass_endpoint_instead_of_native_minimum(self):
        drive = parameter()
        self.assertEqual(normalized_value(drive), 0.5)
        self.assertFalse(should_bypass(drive, "min"))
        self.assertEqual(normalized_value(drive, bounds=(0.5, 1.0)), 0.0)
        self.assertTrue(should_bypass(drive, "min", bounds=(0.5, 1.0)))
        self.assertFalse(should_bypass(drive, "max", bounds=(0.5, 1.0)))

    def test_values_outside_effective_span_clamp_only_for_endpoint_decisions(self):
        drive = parameter(value=0.25)
        self.assertTrue(should_bypass(drive, "min", bounds=(0.5, 1)))
        self.assertTrue(should_bypass(drive, "max", value=1.2, bounds=(0.5, 1)))
        self.assertEqual(drive.value, 0.25)
        self.assertFalse(should_bypass(drive, "min", value=0.51, bounds=(0.5, 1)))

    def test_endpoint_tolerance_is_relative_to_the_effective_span(self):
        drive = parameter()
        self.assertTrue(should_bypass(drive, "min", value=0.5 + 0.5e-6, bounds=(0.5, 1)))
        self.assertFalse(should_bypass(drive, "min", value=0.5 + 1e-6, bounds=(0.5, 1)))
        self.assertTrue(should_bypass(drive, "max", value=1 - 0.25e-6, bounds=(0.5, 1)))

    def test_absolute_wake_preview_uses_full_fader_travel_within_effective_span(self):
        drive = parameter()
        self.assertEqual(input_target(drive, 0, False, bounds=(0.5, 1)), 0.5)
        self.assertAlmostEqual(input_target(drive, 64, False, bounds=(0.5, 1)), 0.5 + 0.5 * 64 / 127)
        self.assertEqual(input_target(drive, 127, False, bounds=(0.5, 1)), 1)
        self.assertTrue(should_bypass(drive, "min", input_target(drive, 0, False, bounds=(0.5, 1)),
                                      bounds=(0.5, 1)))
        self.assertFalse(should_bypass(drive, "min", input_target(drive, 1, False, bounds=(0.5, 1)),
                                       bounds=(0.5, 1)))

    def test_continuous_relative_wake_scales_to_effective_span_and_clamps(self):
        drive = parameter()
        self.assertEqual(input_target(drive, 63, True, bounds=(0.5, 1)), 0.5)
        self.assertAlmostEqual(input_target(drive, 65, True, bounds=(0.5, 1)), 0.5 + 0.5 / 127)
        drive.value = 1
        self.assertEqual(input_target(drive, 127, True, bounds=(0.5, 1)), 1)

    def test_quantized_relative_wake_keeps_native_enum_step(self):
        mode = parameter(value=4, minimum=0, maximum=7, items=tuple(str(i) for i in range(8)))
        self.assertEqual(input_target(mode, 65, True, bounds=(4, 7)), 5)
        self.assertEqual(input_target(mode, 63, True, bounds=(4, 7)), 4)
        self.assertEqual(input_target(mode, 127, True, bounds=(4, 7)), 7)

    def test_disabled_primary_can_be_previewed_without_writing_it(self):
        drive = parameter()
        drive.is_enabled = False
        self.assertAlmostEqual(input_target(drive, 1, False, bounds=(0.5, 1)), 0.5 + 0.5 / 127)
        self.assertEqual(drive.value, 0.5)

    def test_native_device_on_endpoint_writes_are_not_affected_by_other_bounds(self):
        on = parameter(value=0)
        self.assertTrue(device_is_off(on))
        self.assertTrue(set_device_enabled(on, True))
        self.assertEqual(on.value, 1)
        self.assertFalse(device_is_off(on))
        self.assertTrue(set_device_enabled(on, False))
        self.assertEqual(on.value, 0)

    def test_absent_bounds_preserve_native_continuous_and_quantized_operations(self):
        target = parameter(value=-20, minimum=-60, maximum=0)
        self.assertAlmostEqual(normalized_value(target), 2 / 3)
        self.assertEqual(input_target(target, 0, False), -60)
        self.assertEqual(input_target(target, 127, False), 0)
        self.assertAlmostEqual(input_target(target, 65, True), -20 + 60 / 127)
        mode = parameter(value=3, minimum=0, maximum=7, items=tuple(str(i) for i in range(8)))
        self.assertEqual(input_target(mode, 65, True), 4)

    def test_invalid_bounds_or_values_do_not_produce_actions(self):
        drive = parameter()
        for bounds in ((0.5, 0.5), (1, 0.5), (-0.1, 1), (0.5, 1.1),
                       (float("nan"), 1), (0.5, float("inf")), (False, True),
                       (0.5,), (0.5, 1, 2), "01"):
            with self.subTest(bounds=bounds):
                self.assertIsNone(normalized_value(drive, bounds=bounds))
                self.assertIsNone(should_bypass(drive, "min", bounds=bounds))
                self.assertIsNone(input_target(drive, 65, True, bounds=bounds))
        for value in (None, float("nan"), float("inf")):
            with self.subTest(value=value):
                drive.value = value
                self.assertIsNone(normalized_value(drive, bounds=(0.5, 1)))
                self.assertIsNone(input_target(drive, 65, True, bounds=(0.5, 1)))

    def test_invalid_live_reference_is_rejected_even_when_cached_properties_remain(self):
        drive = parameter()
        with patch("Launch_Control_XL_3_Mixing.auto_bypass.liveobj_valid", return_value=False):
            self.assertIsNone(normalized_value(drive))
            self.assertIsNone(normalized_value(drive, bounds=(0.5, 1)))
            self.assertIsNone(should_bypass(drive, "min", bounds=(0.5, 1)))
            self.assertIsNone(input_target(drive, 65, True, bounds=(0.5, 1)))
            self.assertFalse(set_device_enabled(drive, False))
        self.assertEqual(drive.value, 0.5)


if __name__ == "__main__":
    unittest.main()
