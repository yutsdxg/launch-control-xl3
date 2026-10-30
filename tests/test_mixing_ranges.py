"""Configured minimums must own input without leaking a native mapping.

The compensation curve imported below is synthetic test data. These checks use
real control callbacks and observe parameter writes, including device-off order.
"""

import unittest

import test_mixing as fixtures
from test_configured_mixing import ObservableTrack, ObservableView
from test_saturator_compensation import Device, TEST_CURVE, drive_value, output_db
from test_shift_preview import NativeMappedControl

from Launch_Control_XL_3_Mixing.mixing_assignments import ConfiguredMixingAssignmentsComponent
from Launch_Control_XL_3_Mixing.saturator_compensation import SaturatorCompensationManager


class ConfiguredMixingRangesTest(unittest.TestCase):
    def make_component(self, name="fader_7", *, minimum=0.5, initial=0.5,
                       output=0.0, device_on=1.0, **options):
        self.device = Device(output=output)
        self.device.drive.native_change(initial)
        self.device.named["Device On"].native_change(device_on)
        self.device.drive.is_enabled = self.device.output.is_enabled = device_on > 0.5
        track = ObservableTrack("Selected", devices=(self.device,))
        self.song = fixtures.FakeSong((track,))
        self.song.view = ObservableView(track)
        entry = {"device": 1, "parameter": "Drive"}
        if minimum is not None:
            entry["min"] = minimum
        entry.update(options)
        self.component = ConfiguredMixingAssignmentsComponent(assignments={name: entry})
        self.component.song = self.song
        self.component._saturator_compensation.disconnect()
        self.component._saturator_compensation = SaturatorCompensationManager(curve=TEST_CURVE)
        self.addCleanup(self.component.disconnect)
        self.control = NativeMappedControl(relative=name.startswith("encoder_"))
        getattr(self.component, "set_{}".format(name))(self.control)
        return self.control

    def assert_no_parameter_writes(self):
        for name in ("Drive", "Output", "Device On"):
            self.assertEqual(self.device.named[name].writes, [], name)

    def clear_parameter_writes(self):
        for name in ("Drive", "Output", "Device On"):
            self.device.named[name].writes.clear()

    def disable_parameters_with_device_off(self):
        """Model Live disabling both parameters as soon as Device On goes off."""
        on = self.device.named["Device On"]
        events = []
        for name in ("Drive", "Output", "Device On"):
            parameter = self.device.named[name]
            parameter.notify_on_write = True

            def record(name=name, parameter=parameter):
                events.append((name, parameter.value, on.value, output_db(self.device.output)))

            parameter.add_value_listener(record)

        def enabled_changed():
            self.device.drive.is_enabled = self.device.output.is_enabled = on.value > 0.5

        on.add_value_listener(enabled_changed)
        enabled_changed()
        return events

    def test_positive_minimum_fader_owns_full_travel_without_native_mapping(self):
        control = self.make_component(takeover="none")
        self.assertIsNone(control.mapped_parameter)
        self.assert_no_parameter_writes()
        for value in range(128):
            with self.subTest(cc=value):
                control.receive(value)
                self.assertAlmostEqual(self.device.drive.value, 0.5 + 0.5 * value / 127.0)
        self.assertEqual(control.native_updates, [])

    def test_unset_and_zero_minimum_preserve_native_mapping(self):
        for minimum in (None, 0.0):
            with self.subTest(minimum=minimum):
                control = self.make_component(minimum=minimum)
                self.assertIs(control.mapped_parameter, self.device.drive)
                self.assert_no_parameter_writes()
                control.receive(127)
                self.assertEqual(self.device.drive.value, 1.0)
                self.assertEqual(len(control.native_updates), 1)
                self.assertIs(control.mapped_parameter, self.device.drive)

    def test_encoder_uses_bounded_span_for_steps_and_clamps_at_both_ends(self):
        control = self.make_component("encoder_23", initial=0.75)
        self.assertIsNone(control.mapped_parameter)
        control.receive(65)
        self.assertAlmostEqual(self.device.drive.value, 0.75 + 0.5 / 127.0)
        control.receive(63)
        self.assertAlmostEqual(self.device.drive.value, 0.75)
        control.receive(0)
        self.assertEqual(self.device.drive.value, 0.5)
        control.receive(127)
        self.assertAlmostEqual(self.device.drive.value, 0.5 + 0.5 * 63.0 / 127.0)
        control.receive(127)
        control.receive(65)
        self.assertEqual(self.device.drive.value, 1.0)
        self.assertEqual(control.native_updates, [])

    def test_default_value_scaling_anchors_first_input_then_scales_to_endpoint(self):
        control = self.make_component(initial=0.75)
        control.receive(0)
        self.assertEqual(self.device.drive.value, 0.75)
        self.assert_no_parameter_writes()
        control.receive(64)
        self.assertAlmostEqual(self.device.drive.value, 0.75 + 0.25 * 64.0 / 127.0)
        control.receive(127)
        self.assertEqual(self.device.drive.value, 1.0)
        self.assertEqual(control.native_updates, [])

    def test_pickup_wait_does_not_wake_device_or_change_drive_or_output(self):
        control = self.make_component(initial=0.75, output=-12.0, takeover="pickup",
                                      auto_bypass={"off_at": "min"})
        self.disable_parameters_with_device_off()
        on = self.device.named["Device On"]
        on.external_change(0.0)
        self.component._update_assignments()
        for value in (0, 10, 31):
            control.receive(value)
            self.assert_no_parameter_writes()
            self.assertEqual((self.device.drive.value, output_db(self.device.output), on.value),
                             (0.75, -12.0, 0.0))
        control.receive(96)
        self.assertEqual(on.value, 1.0)
        self.assertAlmostEqual(self.device.drive.value, 0.5 + 0.5 * 96.0 / 127.0)
        self.assertEqual(len(self.device.drive.writes), 1)
        self.assertEqual(len(self.device.output.writes), 1)
        self.assertEqual(control.native_updates, [])

    def test_shift_lock_and_inactive_resume_reset_scaling_without_replaying_cc(self):
        for pause in ("shift", "lock", "inactive"):
            with self.subTest(pause=pause):
                control = self.make_component(initial=0.75)
                control.receive(0)
                control.receive(64)
                before = self.device.drive.value
                self.clear_parameter_writes()
                setter = {"shift": self.component.set_shift_pressed,
                          "lock": self.component.set_locked,
                          "inactive": lambda paused: self.component.set_active(not paused)}[pause]
                setter(True)
                control.receive(127)
                self.assertEqual(self.device.drive.value, before)
                self.assert_no_parameter_writes()
                setter(False)
                self.assert_no_parameter_writes()
                control.receive(127)
                self.assertEqual(self.device.drive.value, before)
                self.assert_no_parameter_writes()
                control.receive(0)
                self.assertEqual(self.device.drive.value, 0.5)
                self.assertEqual(control.native_updates, [])

    def test_target_rebind_anchors_new_fader_position_without_replaying_old_cc(self):
        control = self.make_component(initial=0.75)
        control.receive(0)
        control.receive(64)
        previous = self.device
        before = previous.drive.value
        replacement = Device(output=-12.0)
        replacement.drive.native_change(0.6)
        self.song.view.selected_track = ObservableTrack("Replacement", devices=(replacement,))
        self.component._update_assignments()
        self.device = replacement
        self.assert_no_parameter_writes()
        self.assertIsNone(control.mapped_parameter)
        control.receive(127)
        self.assertEqual(replacement.drive.value, 0.6)
        self.assert_no_parameter_writes()
        control.receive(0)
        self.assertEqual(replacement.drive.value, 0.5)
        self.assertEqual(previous.drive.value, before)
        self.assertEqual(control.native_updates, [])

    def test_control_rebind_resets_value_scaling_anchor(self):
        control = self.make_component(initial=0.75)
        control.receive(0)
        control.receive(64)
        before = self.device.drive.value
        replacement = NativeMappedControl(relative=False)
        self.component.set_fader_7(replacement)
        self.clear_parameter_writes()
        control.receive(0)
        replacement.receive(127)
        self.assertEqual(self.device.drive.value, before)
        self.assert_no_parameter_writes()
        replacement.receive(0)
        self.assertEqual(self.device.drive.value, 0.5)
        self.assertEqual(replacement.native_updates, [])

    def test_outside_existing_value_is_clamped_only_on_physical_input(self):
        control = self.make_component(initial=0.25, output=-12.0)
        self.component._update_assignments()
        self.component.set_active(True)
        self.assertEqual(self.device.drive.value, 0.25)
        self.assert_no_parameter_writes()
        control.receive(64)
        self.assertEqual(self.device.drive.value, 0.5)
        self.assertAlmostEqual(output_db(self.device.output), 0.0)
        self.assertEqual(len(self.device.drive.writes), 1)

    def test_effective_drive_minimum_resets_output_before_off_and_wakes_once(self):
        for name, wake_cc, wake_drive, wake_output in (
                ("fader_7", 127, 1.0, -10.0),
                ("encoder_23", 65, 0.5 + 0.5 / 127.0, -24.0 / 127.0)):
            with self.subTest(control=name):
                options = {"takeover": "none"} if name.startswith("fader_") else {}
                control = self.make_component(name, initial=drive_value(6.0), output=-4.0,
                                              auto_bypass={"off_at": "min"}, **options)
                events = self.disable_parameters_with_device_off()
                on = self.device.named["Device On"]
                self.assert_no_parameter_writes()
                control.receive(0)
                self.assertEqual(self.device.drive.value, 0.5)
                self.assertAlmostEqual(output_db(self.device.output), 0.0)
                self.assertEqual(on.value, 0.0)
                self.assertEqual([event[0] for event in events], ["Drive", "Output", "Device On"])
                self.assertEqual(events[1][2], 1.0)
                self.assertAlmostEqual(events[2][3], 0.0)
                self.clear_parameter_writes()
                events.clear()
                control.receive(wake_cc)
                self.assertEqual(on.value, 1.0)
                self.assertAlmostEqual(self.device.drive.value, wake_drive)
                self.assertAlmostEqual(output_db(self.device.output), wake_output)
                self.assertEqual(len(self.device.drive.writes), 1)
                self.assertEqual(len(self.device.output.writes), 1)
                self.assertEqual(on.writes, [1.0])
                self.assertEqual([event[0] for event in events], ["Device On", "Drive", "Output"])
                self.assertEqual(control.native_updates, [])

    def test_saved_below_minimum_off_device_is_repaired_on_input_and_can_wake_again(self):
        for takeover in (None, "none"):
            with self.subTest(takeover=takeover or "default_value_scaling"):
                options = {} if takeover is None else {"takeover": takeover}
                control = self.make_component(initial=0.0, output=-12.0, device_on=0.0,
                                              auto_bypass={"off_at": "min"}, **options)
                events = self.disable_parameters_with_device_off()
                on = self.device.named["Device On"]
                self.assertIsNone(control.mapped_parameter)
                self.assert_no_parameter_writes()
                control.receive(0)
                self.assertEqual(self.device.drive.value, 0.5)
                self.assertAlmostEqual(output_db(self.device.output), 0.0)
                self.assertEqual(on.value, 0.0)
                self.assertEqual(on.writes, [1.0, 0.0])
                self.assertEqual(self.device.drive.writes, [0.5])
                self.assertEqual(self.device.output.writes, [1.0])
                self.assertEqual([event[0] for event in events],
                                 ["Device On", "Drive", "Output", "Device On"])
                self.assertEqual(events[2][2], 1.0)
                self.assertAlmostEqual(events[3][3], 0.0)
                self.clear_parameter_writes()
                events.clear()
                control.receive(127)
                self.assertEqual(on.value, 1.0)
                self.assertEqual(self.device.drive.writes, [1.0])
                self.assertAlmostEqual(output_db(self.device.output), -10.0)
                self.assertEqual(len(self.device.output.writes), 1)
                self.assertEqual(on.writes, [1.0])
                self.assertEqual([event[0] for event in events], ["Device On", "Drive", "Output"])
                self.assertEqual(control.native_updates, [])


if __name__ == "__main__":
    unittest.main()
