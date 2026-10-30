"""Auto bypass follows physical inputs while preserving Live's parameter map."""

import types
import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_configured_mixing import ElementControl, ObservableDevice, ObservableTrack, ObservableView
from test_encoder_companion_actions import TrackedParameter
from test_initial_assignment_display import HardwareDisplay
from test_mixing_colored_encoder import COLORED, FakeDevice as LedDevice, FakeParameter as LedParameter
from test_shift_preview import NativeMappedControl

from Launch_Control_XL_3_Mixing.auto_bypass import normalized_value, should_bypass
from Launch_Control_XL_3_Mixing.mixing_assignments import ConfiguredMixingAssignmentsComponent
from Launch_Control_XL_3_Mixing.mixing_targets import validate_assignments


class Parameter:
    def __init__(self, name="Dry/Wet", value=0.0, minimum=0.0, maximum=1.0, device_on=None):
        self.name = name
        self.min, self.max = minimum, maximum
        self._value = value
        self.device_on = device_on
        self.enabled = True
        self.writes = []
        self.is_quantized = False
        self.value_items = ()

    @property
    def is_enabled(self):
        return self.enabled and (self.device_on is None or self.device_on.value > 0.5)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if not self.is_enabled:
            raise RuntimeError("A disabled parameter cannot be written")
        self._value = value
        self.writes.append(value)

    def __str__(self):
        return str(self.value)


class AutoBypassTest(unittest.TestCase):
    def setUp(self):
        self.on = TrackedParameter("Device On", value=1.0)
        self.parameter = Parameter()
        self.device = ObservableDevice()
        self.device.replace_parameters((self.on, self.parameter))
        self.track = ObservableTrack("Selected", devices=(self.device,))
        self.song = fixtures.FakeSong((self.track,))
        self.song.view = ObservableView(self.track)

    def install(self, off_at="min", name="encoder_1", assignments=None, control=None):
        self.name = name
        self.component = ConfiguredMixingAssignmentsComponent(assignments=assignments or {
            name: {"device": 1, "parameter": self.parameter.name, "auto_bypass": {"off_at": off_at}}})
        self.component.song = self.song
        self.addCleanup(self.component.disconnect)
        self.display = HardwareDisplay()
        self.control = control or NativeMappedControl(relative=name.startswith("encoder_"))
        getattr(self.component, "set_{}_display".format(name))(self.display)
        getattr(self.component, "set_{}".format(name))(self.control)
        return self.control

    def test_min_bypasses_and_next_encoder_turn_restores_device(self):
        self.install()
        self.assertEqual(self.on.writes, [])
        self.control.receive(63)
        self.assertEqual(self.on.writes, [0.0])
        self.control.receive(65)
        self.assertGreater(self.parameter.value, 0.0)
        self.assertEqual(self.on.writes, [0.0, 1.0])
        self.assertIs(self.control.mapped_parameter, self.parameter)
        self.assertEqual(self.display.local_shift_turn()[1], "Dry/Wet")

    def test_max_threshold_bypasses_and_fader_movement_restores_device(self):
        self.parameter.name = "Threshold"
        self.parameter.min, self.parameter.max, self.parameter._value = -60.0, 0.0, -20.0
        self.install(off_at="max", name="fader_5")
        self.control.receive(127)
        self.assertEqual(self.parameter.value, 0.0)
        self.assertEqual(self.on.value, 0.0)
        self.control.receive(126)
        self.assertLess(self.parameter.value, 0.0)
        self.assertEqual(self.on.value, 1.0)
        self.assertEqual(len(self.control.native_updates), 2)

    def test_repeated_endpoint_inputs_do_not_repeat_device_on_writes(self):
        self.install()
        for value in (63, 0, 63):
            self.control.receive(value)
        self.assertEqual(self.on.writes, [0.0])
        for value in (65, 65, 65):
            self.control.receive(value)
        self.assertEqual(self.on.writes, [0.0, 1.0])

    def test_external_changes_refreshes_and_selection_never_write_device_on(self):
        self.install()
        for value in (0.4, 0.0, 1.0, 0.0):
            self.parameter.value = value
            self.component._update_assignments()
            self.component._update_assignments(force=True)
            self.component.refresh_display_feedback()
        self.song.view.selected_track = ObservableTrack("Empty")
        self.song.view.selected_track = self.track
        self.component.set_active(False)
        self.component.set_active(True)
        self.assertEqual(self.on.writes, [])

    def test_shift_touch_lock_and_inactive_inputs_do_not_write_or_replay_actions(self):
        self.install()
        for setter in (self.component.set_shift_pressed, self.component.set_locked):
            setter(True)
            for value in (0, 63, 65, 127):
                self.control.receive(value)
                self.component.preview_encoder(self.name)
                self.component._update_assignments(force=True)
            setter(False)
        self.component.set_active(False)
        self.control.receive(63)
        self.component.set_active(True)
        self.assertEqual(self.on.writes, [])
        self.assertEqual(self.parameter.writes, [])
        self.control.receive(63)
        self.assertEqual(self.on.writes, [0.0])

    def test_neutral_and_invalid_inputs_do_not_run_companion_action(self):
        self.install()
        for value in (64, -1, 128, 1.5, True, None):
            self.component._on_parameter_control_value(self.name, value)
        self.assertEqual(self.on.writes, [])
        self.assertEqual(self.parameter.writes, [])

    def test_encoder_wakes_a_bypassed_disabled_parameter_and_applies_one_relative_input(self):
        self.on.value = 0.0
        self.on.writes.clear()
        self.parameter.device_on = self.on
        self.install()
        self.assertIsNone(self.control.mapped_parameter)
        self.assertIs(self.control.manual_led_parameter, self.parameter)
        self.assertEqual(self.display.local_shift_turn()[1], "Dry/Wet")
        self.control.receive(63)
        self.assertEqual(self.on.writes, [])
        self.control.receive(65)
        self.assertEqual(self.on.writes, [1.0])
        self.assertAlmostEqual(self.parameter.value, 1.0 / 127)
        self.assertEqual(len(self.parameter.writes), 1)
        self.assertEqual(self.control.native_updates, [])
        self.assertIs(self.control.mapped_parameter, self.parameter)
        self.control.receive(65)
        self.assertAlmostEqual(self.parameter.value, 2.0 / 127)
        self.assertEqual(len(self.control.native_updates), 1)

    def test_fader_wake_preserves_native_takeover_and_never_replays_the_wake_cc(self):
        self.on.value = 0.0
        self.on.writes.clear()
        self.parameter.device_on = self.on
        self.install(name="fader_6")
        self.assertIsNone(self.control.mapped_parameter)
        self.control.receive(0)
        self.assertEqual(self.on.writes, [])
        self.control.receive(20)
        self.assertEqual(self.on.writes, [1.0])
        self.assertEqual(self.parameter.writes, [])
        self.assertIs(self.control.mapped_parameter, self.parameter)
        self.component._update_assignments(force=True)
        self.assertEqual(self.parameter.writes, [])
        self.control.receive(21)
        self.assertAlmostEqual(self.parameter.value, 21 / 127)
        self.assertEqual(len(self.control.native_updates), 1)

    def test_threshold_disabled_at_max_wakes_only_when_input_leaves_max(self):
        self.on.value = 0.0
        self.on.writes.clear()
        self.parameter.device_on = self.on
        self.parameter.min, self.parameter.max, self.parameter._value = -60.0, 0.0, 0.0
        self.install(off_at="max")
        self.control.receive(65)
        self.assertEqual(self.on.writes, [])
        self.control.receive(63)
        self.assertEqual(self.on.value, 1.0)
        self.assertLess(self.parameter.value, 0.0)

    def test_shift_and_lock_do_not_wake_a_bypassed_disabled_parameter(self):
        self.on.value = 0.0
        self.on.writes.clear()
        self.parameter.device_on = self.on
        self.install()
        for setter in (self.component.set_shift_pressed, self.component.set_locked):
            setter(True)
            self.control.receive(65)
            self.component.preview_encoder(self.name)
            self.component._update_assignments(force=True)
            setter(False)
            self.assertIsNone(self.control.mapped_parameter)
        self.assertEqual(self.on.writes, [])
        self.assertEqual(self.parameter.writes, [])
        self.control.receive(65)
        self.assertEqual(self.on.writes, [1.0])

    def test_delayed_parameter_enable_does_not_queue_a_write(self):
        self.on.value = 0.0
        self.on.writes.clear()
        self.parameter.device_on = self.on
        self.install()
        self.parameter.enabled = False
        self.control.receive(65)
        self.assertEqual(self.on.value, 1.0)
        self.assertEqual(self.parameter.writes, [])
        self.parameter.enabled = True
        self.component._update_assignments()
        self.assertEqual(self.parameter.writes, [])
        self.control.receive(65)
        self.assertAlmostEqual(self.parameter.value, 1 / 127)

    def test_other_disabled_parameters_are_not_treated_as_bypass_recovery(self):
        self.parameter.enabled = False
        self.install()
        self.control.receive(65)
        self.assertEqual(self.on.writes, [])
        self.assertEqual(self.parameter.writes, [])
        self.assertIsNone(self.control.mapped_parameter)

    def test_multiple_conditions_for_same_device_use_any_off_condition(self):
        threshold = Parameter("Threshold", value=0.3)
        self.device.replace_parameters((self.on, self.parameter, threshold))
        assignments = {
            "encoder_1": {"device": 1, "parameter": "Dry/Wet", "auto_bypass": {"off_at": "min"}},
            "fader_5": {"device": 1, "parameter": "Threshold", "auto_bypass": {"off_at": "max"}},
        }
        self.install(assignments=assignments)
        other = NativeMappedControl(relative=False)
        self.component.set_fader_5(other)
        other.receive(100)
        self.assertEqual(self.on.value, 0.0)  # Dry/Wet is still neutral.
        self.control.receive(65)
        self.assertEqual(self.on.value, 1.0)
        other.receive(127)
        self.assertEqual(self.on.value, 0.0)
        self.control.receive(65)
        self.assertEqual(self.on.value, 0.0)  # Threshold is still neutral.

    def test_missing_or_unwritable_device_on_keeps_primary_control_working(self):
        self.install()
        self.device.replace_parameters((self.parameter,))
        self.control.receive(65)
        self.assertGreater(self.parameter.value, 0.0)
        self.assertEqual(self.on.writes, [])
        self.device.replace_parameters((self.on, self.parameter))
        self.on.is_enabled = False
        self.control.receive(0)
        self.assertEqual(self.on.writes, [])
        self.assertEqual(self.parameter.value, 0.0)

    def test_missing_primary_or_device_does_not_write_an_unrelated_target(self):
        self.install()
        self.device.replace_parameters((self.on,))
        self.control.receive(63)
        self.assertIsNone(self.control.mapped_parameter)
        self.assertEqual(self.on.writes, [])
        self.track.devices = ()
        self.control.receive(65)
        self.assertEqual(self.on.writes, [])

    def test_other_device_conditions_do_not_keep_this_device_bypassed(self):
        other_on = TrackedParameter("Device On", value=1.0)
        other_parameter = Parameter()
        other_device = ObservableDevice()
        other_device.replace_parameters((other_on, other_parameter))
        self.track.devices = (self.device, other_device)
        self.install(assignments={
            "encoder_1": {"device": 1, "parameter": "Dry/Wet", "auto_bypass": {"off_at": "min"}},
            "fader_6": {"device": 2, "parameter": "Dry/Wet", "auto_bypass": {"off_at": "min"}},
        })
        self.on.value = 0.0
        self.on.writes.clear()
        self.control.receive(65)
        self.assertEqual(self.on.value, 1.0)
        self.assertEqual(other_on.writes, [])

    def test_selection_change_actions_only_affect_the_new_device(self):
        self.install()
        other_on = TrackedParameter("Device On", value=1.0)
        other_parameter = Parameter()
        other_device = ObservableDevice()
        other_device.replace_parameters((other_on, other_parameter))
        self.song.view.selected_track = ObservableTrack("Other", devices=(other_device,))
        self.assertEqual(other_on.writes, [])
        self.control.receive(63)
        self.assertEqual(other_on.writes, [0.0])
        self.assertEqual(self.on.writes, [])

    def test_parameter_list_is_cached_for_primary_and_device_on(self):
        self.install()
        self.device.parameter_read_count = 0
        for value in (63, 65, 65, 63):
            self.control.receive(value)
        self.assertEqual(self.device.parameter_read_count, 0)

    def test_unmodified_native_fader_does_not_bypass_pickup(self):
        class PickupControl(NativeMappedControl):
            def receive(self, value):
                if value < 90:
                    fixtures.FakeButton.receive(self, value)
                else:
                    super().receive(value)

        self.parameter._value = 0.7
        self.install(name="fader_6", control=PickupControl(relative=False))
        connections = len(self.control.connected)
        for value in (10, 20, 30):
            self.control.receive(value)
        self.assertEqual(self.parameter.writes, [])
        self.assertEqual(self.parameter.value, 0.7)
        self.assertEqual(len(self.control.connected), connections)
        self.control.receive(100)
        self.assertAlmostEqual(self.parameter.value, 100 / 127)

    def test_shared_saturn_handler_runs_bypass_once_without_applying_the_turn_twice(self):
        self.on.value = 0.0
        self.on.writes.clear()
        device = LedDevice()
        parameter = LedParameter(value=2.0, parent=device)
        device.parameters = (self.on, parameter)
        self.track.devices = (device,)
        self.parameter = parameter
        self.install(name="encoder_22")
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        self.addCleanup(router.disconnect)
        router.set_target_components(fixed_assignments=self.component)
        encoder = ElementControl()
        with patch.object(COLORED, "encoder_rgb_for_parameter", return_value=(25, 5, 0)), \
                patch.object(COLORED, "Theme", types.SimpleNamespace(OFF=(0, 0, 0))):
            router.set_encoder_22(encoder)
            encoder.receive_value(65)
        self.assertEqual(parameter.value, 6.0)
        self.assertEqual(self.on.writes, [1.0])


class AutoBypassConfigurationTest(unittest.TestCase):
    def test_valid_options_for_encoder_and_fader(self):
        for name in ("encoder_19", "fader_6"):
            for endpoint in ("min", "max"):
                entry = {"device": 1, "parameter": "Dry/Wet", "auto_bypass": {"off_at": endpoint}}
                self.assertEqual(validate_assignments({name: entry})[name], entry)

    def test_invalid_options_disable_only_their_slot(self):
        invalid = (None, True, "min", {}, {"off_at": "middle"}, {"off_at": "min", "extra": 1})
        for option in invalid:
            with self.subTest(option=option), self.assertLogs(level="WARNING"):
                result = validate_assignments({
                    "encoder_1": {"device": 1, "parameter": "Dry/Wet", "auto_bypass": option},
                    "fader_8": {"mixer": "volume"}})
                self.assertIsNone(result["encoder_1"])
                self.assertEqual(result["fader_8"], {"mixer": "volume"})
        for entry in (
            {"mixer": "volume", "auto_bypass": {"off_at": "min"}},
            {"device": 1, "parameter": "Device On", "auto_bypass": {"off_at": "min"}},
            {"device": 1, "parameter": "Dry/Wet", "directional_on_off": True,
             "auto_bypass": {"off_at": "min"}},
        ):
            with self.subTest(entry=entry), self.assertLogs(level="WARNING"):
                self.assertIsNone(validate_assignments({"encoder_1": entry})["encoder_1"])

    def test_endpoint_tolerance_uses_raw_range_and_does_not_parse_display_units(self):
        parameter = Parameter("Threshold", value=-60.0, minimum=-60.0, maximum=0.0)
        self.assertTrue(should_bypass(parameter, "min"))
        self.assertTrue(should_bypass(parameter, "min", -60.0 + 60.0 * 1e-7))
        self.assertFalse(should_bypass(parameter, "min", -60.0 + 60.0 * 1e-4))
        self.assertTrue(should_bypass(parameter, "max", -60.0 * 1e-7))
        self.assertFalse(should_bypass(parameter, "max", -60.0 * 1e-4))
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assertIsNone(normalized_value(parameter, value))
        parameter.max = parameter.min
        self.assertIsNone(should_bypass(parameter, "min"))


if __name__ == "__main__":
    unittest.main()
