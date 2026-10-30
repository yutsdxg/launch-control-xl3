"""Physical Drive compensation uses actual native values and preserves manual trim.

The injected curve below is synthetic test data, not a measured calibration.
Live 12.4.15 updates the native value before the control callback and delivers
the Drive notification afterwards; the fakes deliberately retain that order.
"""

import unittest

import test_mixing  # Install the same minimal Live stubs as the other components.
from test_configured_mixing import ObservableTrack, ObservableView
from test_shift_preview import NativeMappedControl

from Launch_Control_XL_3_Mixing.mixing_assignments import ConfiguredMixingAssignmentsComponent
from Launch_Control_XL_3_Mixing.saturator_compensation import SaturatorCompensationManager


TEST_CURVE = ((0.0, 0.0), (6.0, -4.0), (12.0, -7.0), (24.0, -10.0))


def drive_value(db):
    return (db + 36.0) / 72.0


def output_value(db):
    return (db + 36.0) / 36.0


def output_db(parameter):
    return parameter.value * 36.0 - 36.0


class ObservableParameter:
    def __init__(self, name, value=0.0, *, maximum=1.0, items=()):
        self.name = self.original_name = name
        self.min, self.max = 0.0, maximum
        self._value = value
        self.is_enabled = True
        self.is_quantized = bool(items)
        self.automation_state = self.state = 0
        self.value_items = tuple(items)
        self.listeners = []
        self.writes = []
        self.notify_on_write = False
        self.fail_write = False

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if not self.is_enabled or self.fail_write:
            raise RuntimeError("Live refused the parameter write")
        self._value = value
        self.writes.append(value)
        if self.notify_on_write:
            self.notify()

    def native_change(self, value):
        """Native parameter mapping changes the value before Python input."""
        self._value = value

    def external_change(self, value):
        """A mouse edit notifies without a physical control callback."""
        self._value = value
        self.notify()

    def notify(self):
        for callback in tuple(self.listeners):
            callback()

    def add_value_listener(self, callback):
        if callback in self.listeners:
            raise AssertionError("A value observer was installed twice")
        self.listeners.append(callback)

    def remove_value_listener(self, callback):
        self.listeners.remove(callback)


class Device:
    def __init__(self, output=-6.0):
        # Names/classes deliberately differ: initial routing is parameter-based.
        self.name, self.class_name = "User renamed effect", "OtherDeviceClass"
        self.named = {
            "Device On": ObservableParameter("Device On", 1.0, items=("Off", "On")),
            "Drive": ObservableParameter("Drive", drive_value(0.0)),
            "Output": ObservableParameter("Output", output_value(output)),
            "Type": ObservableParameter("Type", 0.0, maximum=7.0, items=(
                "Analog Clip", "Soft Sine", "Bass Shaper", "Medium Curve",
                "Hard Curve", "Sinoid Fold", "Digital Clip", "Waveshaper")),
            "Color On": ObservableParameter("Color On", 0.0, items=("Off", "On")),
            "Post Clip Mode": ObservableParameter("Post Clip Mode", 0.0, maximum=2.0,
                                                   items=("No Clip", "Soft Clip", "Hard Clip")),
            "Dry/Wet": ObservableParameter("Dry/Wet", 1.0),
        }
        for parameter in self.named.values():
            parameter.canonical_parent = self

    @property
    def parameters(self):
        return tuple(self.named.values())

    @property
    def drive(self):
        return self.named["Drive"]

    @property
    def output(self):
        return self.named["Output"]


class Resolver:
    def __init__(self, devices):
        self.devices = devices
        self.track = object()

    def device(self, number):
        return self.devices.get(number)

    def owner(self, entry):
        return self.device(entry.get("device"))

    def resolve(self, entry):
        if not entry:
            return None
        device = self.owner(entry)
        return device.named.get(entry.get("parameter")) if device is not None else None


class NativeControl:
    def __init__(self, parameter):
        self.mapped_parameter = parameter

    def connect_to(self, parameter):
        raise AssertionError("Compensation must preserve the existing native mapping")

    def release_parameter(self):
        raise AssertionError("Compensation must preserve the existing native mapping")


class SaturatorCompensationTest(unittest.TestCase):
    def setUp(self):
        self.device = Device()
        self.resolver = Resolver({1: self.device})
        self.assignments = {"fader_7": {"device": 1, "parameter": "Drive"}}
        self.controls = {"fader_7": NativeControl(self.device.drive)}
        self.enabled = True
        self.manager = SaturatorCompensationManager(curve=TEST_CURVE)
        self.addCleanup(self.manager.disconnect)
        self.refresh()

    def refresh(self, enabled=None):
        if enabled is not None:
            self.enabled = enabled
        self.manager.refresh(self.resolver, self.assignments, self.controls, enabled=self.enabled)

    def physical(self, db, control="fader_7", device=None, *, notify=True, refresh=True):
        target = device or self.device
        target.drive.native_change(drive_value(db))
        if refresh:
            self.refresh()
        self.manager.begin_input(control)
        self.manager.end_input(control)
        if notify:
            target.drive.notify()

    def assertOutput(self, expected, device=None):
        self.assertAlmostEqual(output_db((device or self.device).output), expected, places=5)

    def test_binding_refresh_and_pickup_wait_never_write_output(self):
        for unused in range(4):
            self.refresh()
            self.manager.begin_input("fader_7")
            self.manager.end_input("fader_7")
        self.assertEqual(self.device.output.writes, [])
        self.assertIs(self.controls["fader_7"].mapped_parameter, self.device.drive)

    def test_native_actual_drive_value_controls_correction_and_refresh_keeps_anchor(self):
        self.physical(6.0)
        self.assertOutput(-10.0)
        self.physical(9.0)
        self.assertOutput(-11.5)
        self.physical(12.0)
        self.assertOutput(-13.0)
        self.assertEqual(self.device.drive.writes, [])

    def test_arbitrary_encoder_and_duplicate_assignment_share_one_target_state(self):
        self.assignments["encoder_23"] = dict(self.assignments["fader_7"])
        self.controls["encoder_23"] = NativeControl(self.device.drive)
        self.refresh()
        self.physical(6.0, "encoder_23")
        self.assertOutput(-10.0)
        self.manager.begin_input("fader_7")
        self.manager.end_input("fader_7")
        self.assertEqual(len(self.device.output.writes), 1)
        self.physical(12.0, "fader_7")
        self.assertOutput(-13.0)
        self.assertIs(self.controls["encoder_23"].mapped_parameter, self.device.drive)

    def test_two_devices_use_separate_curves_and_manual_offsets(self):
        other = Device(output=-20.0)
        self.resolver.devices[2] = other
        self.assignments["encoder_4"] = {"device": 2, "parameter": "Drive"}
        self.controls["encoder_4"] = NativeControl(other.drive)
        self.refresh()
        self.physical(6.0)
        self.physical(12.0, "encoder_4", other)
        self.assertOutput(-10.0)
        self.assertOutput(-27.0, other)

    def test_mouse_drive_change_reanchors_without_correction_or_next_pickup_jump(self):
        self.device.drive.external_change(drive_value(12.0))
        self.refresh()
        self.assertEqual(self.device.output.writes, [])
        self.manager.begin_input("fader_7")
        self.manager.end_input("fader_7")
        self.assertEqual(self.device.output.writes, [])
        self.physical(18.0)
        self.assertOutput(-7.5)

    def test_manual_output_trim_survives_following_drive_changes(self):
        self.physical(6.0)
        self.device.output.notify()
        self.device.output.external_change(output_value(-9.0))
        self.physical(12.0)
        self.assertOutput(-12.0)
        self.physical(0.0)
        self.assertOutput(-5.0)

    def test_delayed_and_duplicate_own_output_notifications_do_not_change_trim(self):
        self.physical(6.0, notify=False)
        self.physical(12.0, notify=False)
        self.device.drive.notify()
        self.device.output.notify()
        self.device.output.notify()
        self.physical(0.0)
        self.assertOutput(-6.0)

    def test_output_manual_change_wins_over_an_undelivered_own_notification(self):
        self.physical(6.0)
        self.device.output.external_change(output_value(-7.0))
        self.device.output.notify()
        self.physical(12.0)
        self.assertOutput(-10.0)

    def test_lower_output_clamp_preserves_unclipped_trim_for_return(self):
        self.device.output.external_change(output_value(-35.0))
        self.physical(12.0)
        self.assertOutput(-36.0)
        self.device.output.notify()
        self.device.output.notify()
        self.physical(6.0)
        self.assertOutput(-36.0)
        self.physical(0.0)
        self.assertOutput(-35.0)

    def test_upper_output_clamp_preserves_unclipped_trim_for_return(self):
        self.device.drive.external_change(drive_value(12.0))
        self.device.output.external_change(output_value(-1.0))
        self.physical(0.0)
        self.assertOutput(0.0)
        self.device.output.notify()
        self.physical(12.0)
        self.assertOutput(-1.0)

    def test_outside_calibrated_range_uses_constant_endpoint_corrections(self):
        self.physical(-24.0)
        self.assertEqual(self.device.output.writes, [])
        self.physical(24.0)
        self.assertOutput(-16.0)
        count = len(self.device.output.writes)
        self.physical(36.0)
        self.assertOutput(-16.0)
        self.assertEqual(len(self.device.output.writes), count)

    def test_synchronous_drive_write_during_encoder_wakeup_is_still_physical(self):
        self.manager.begin_input("fader_7")
        self.device.drive.external_change(drive_value(6.0))
        self.manager.end_input("fader_7")
        self.assertOutput(-10.0)
        self.device.drive.notify()
        self.physical(12.0)
        self.assertOutput(-13.0)

    def test_shift_lock_or_inactive_period_reanchors_without_replaying_old_inputs(self):
        self.refresh(enabled=False)
        self.physical(6.0)
        self.assertEqual(self.device.output.writes, [])
        self.refresh(enabled=True)
        self.assertEqual(self.device.output.writes, [])
        self.physical(12.0)
        self.assertOutput(-9.0)

    def test_unsupported_settings_pause_then_reanchor_on_resume(self):
        for parameter, invalid in (("Type", 1.0), ("Color On", 1.0),
                                   ("Dry/Wet", 0.5), ("Post Clip Mode", 1.0)):
            with self.subTest(parameter=parameter):
                self.device.drive.external_change(drive_value(0.0))
                self.device.output.external_change(output_value(-6.0))
                selector = self.device.named[parameter]
                original = selector.value
                selector.external_change(invalid)
                self.refresh()
                self.device.output.writes.clear()
                self.physical(6.0)
                self.assertEqual(self.device.output.writes, [])
                selector.external_change(original)
                self.refresh()
                self.assertEqual(self.device.output.writes, [])
                self.physical(12.0)
                self.assertOutput(-9.0)

    def test_drive_and_output_automation_or_disabled_targets_do_not_write(self):
        for name in ("Drive", "Output"):
            for state in (1, 2):
                with self.subTest(name=name, state=state):
                    self.device.drive.external_change(drive_value(0.0))
                    self.device.output.external_change(output_value(-6.0))
                    parameter = self.device.named[name]
                    parameter.automation_state = state
                    self.refresh()
                    self.device.output.writes.clear()
                    self.physical(6.0)
                    self.assertEqual(self.device.output.writes, [])
                    parameter.automation_state = 0
                    self.refresh()
            parameter = self.device.named[name]
            parameter.is_enabled = False
            self.refresh()
            self.device.output.writes.clear()
            self.physical(12.0)
            self.assertEqual(self.device.output.writes, [])
            parameter.is_enabled = True
            self.refresh()

    def test_replacement_device_detaches_old_listeners_and_uses_new_output(self):
        old = self.device
        other = Device(output=-20.0)
        self.resolver.devices[1] = other
        self.controls["fader_7"] = NativeControl(other.drive)
        self.refresh()
        old.drive.external_change(drive_value(18.0))
        old.output.external_change(output_value(-2.0))
        self.assertEqual(old.drive.listeners, [])
        self.assertEqual(old.output.listeners, [])
        self.assertEqual(old.output.writes, [])
        self.assertEqual(other.output.writes, [])
        self.physical(6.0, device=other)
        self.assertOutput(-24.0, other)

    def test_missing_companion_and_non_exact_drive_names_are_inert(self):
        output = self.device.output
        for missing in ("Output", "Type", "Color On", "Post Clip Mode", "Dry/Wet"):
            with self.subTest(missing=missing):
                self.device.drive.external_change(drive_value(0.0))
                output.external_change(output_value(-6.0))
                output.writes.clear()
                saved = self.device.named.pop(missing)
                self.refresh()
                self.device.drive.native_change(drive_value(6.0))
                self.manager.begin_input("fader_7")
                self.manager.end_input("fader_7")
                self.device.drive.notify()
                self.assertEqual(output.writes, [])
                self.device.named[missing] = saved
                self.refresh()
        for parameter in ("drive", "Drive Amount", "WS Drive"):
            with self.subTest(parameter=parameter):
                self.assignments["fader_7"]["parameter"] = parameter
                self.refresh()
                self.physical(12.0)
                self.assertEqual(self.device.output.writes, [])

    def test_explicit_empty_curve_and_missing_device_do_not_write(self):
        self.manager.disconnect()
        self.manager = SaturatorCompensationManager(curve=())
        self.addCleanup(self.manager.disconnect)
        self.refresh()
        self.physical(6.0)
        self.assertEqual(self.device.output.writes, [])
        self.resolver.devices.clear()
        self.refresh()
        self.manager.begin_input("fader_7")
        self.manager.end_input("fader_7")
        self.assertEqual(self.device.output.writes, [])

    def test_disconnection_removes_observers_and_late_input_cannot_write(self):
        self.manager.disconnect()
        self.assertEqual(self.device.drive.listeners, [])
        self.assertEqual(self.device.output.listeners, [])
        self.device.drive.external_change(drive_value(12.0))
        self.manager.begin_input("fader_7")
        self.manager.end_input("fader_7")
        self.assertEqual(self.device.output.writes, [])

    def test_failed_output_write_does_not_retry_old_operation_after_recovery(self):
        self.device.output.fail_write = True
        self.physical(6.0)
        self.assertEqual(self.device.output.writes, [])
        self.device.output.fail_write = False
        self.refresh()
        self.assertEqual(self.device.output.writes, [])
        self.physical(12.0)
        self.assertOutput(-9.0)

    def test_synchronous_own_output_notification_preserves_trim_across_clamping(self):
        self.device.output.notify_on_write = True
        self.device.output.external_change(output_value(-35.0))
        self.physical(12.0)
        self.assertOutput(-36.0)
        self.physical(0.0)
        self.assertOutput(-35.0)

    def test_target_removed_during_physical_input_never_writes_the_old_output(self):
        self.device.drive.native_change(drive_value(6.0))
        self.manager.begin_input("fader_7")
        self.assignments.clear()
        self.refresh()
        self.manager.end_input("fader_7")
        self.device.drive.notify()
        self.assertEqual(self.device.output.writes, [])
        self.assertEqual(self.device.drive.listeners, [])

    def test_non_normalized_drive_or_output_ranges_are_not_interpreted_as_db(self):
        for name in ("Drive", "Output"):
            with self.subTest(name=name):
                parameter = self.device.named[name]
                parameter.min, parameter.max = -36.0, 36.0
                self.refresh()
                self.physical(6.0)
                self.assertEqual(self.device.output.writes, [])
                parameter.min, parameter.max = 0.0, 1.0
                self.device.drive.external_change(drive_value(0.0))
                self.refresh()


class ConfiguredSaturatorCompensationTest(unittest.TestCase):
    def setUp(self):
        self.device = Device()
        track = ObservableTrack("Selected", devices=(self.device,))
        song = test_mixing.FakeSong((track,))
        song.view = ObservableView(track)
        self.component = ConfiguredMixingAssignmentsComponent(assignments={
            "fader_7": {"device": 1, "parameter": "Drive"},
            "encoder_23": {"device": 1, "parameter": "Drive"},
        })
        self.component.song = song
        self.component._saturator_compensation.disconnect()
        self.component._saturator_compensation = SaturatorCompensationManager(curve=TEST_CURVE)
        self.addCleanup(self.component.disconnect)
        self.controls = {}
        for name in ("fader_7", "encoder_23"):
            control = NativeMappedControl(relative=name.startswith("encoder_"))
            self.controls[name] = control
            getattr(self.component, "set_{}".format(name))(control)

    def physical(self, name, db=None, midi=65):
        # Do not use NativeMappedControl.receive: that fixture counts its native
        # setter as a Python write. Reproduce the measured Live ordering here.
        if db is not None and self.controls[name].mapped_parameter is not None:
            self.device.drive.native_change(drive_value(db))
        self.component._on_parameter_control_value(name, midi)
        self.device.drive.notify()

    def test_arbitrary_fader_and_encoder_share_compensation_without_native_remapping(self):
        self.physical("fader_7", 6.0, midi=40)
        self.assertAlmostEqual(output_db(self.device.output), -10.0)
        self.physical("encoder_23", 12.0)
        self.assertAlmostEqual(output_db(self.device.output), -13.0)
        self.assertEqual(self.device.drive.writes, [])
        for control in self.controls.values():
            self.assertIs(control.mapped_parameter, self.device.drive)
        before = len(self.device.output.writes)
        self.physical("encoder_23", midi=64)
        self.physical("fader_7", midi=40)
        self.assertEqual(len(self.device.output.writes), before)

    def test_shift_lock_and_inactive_mode_suppress_compensation_and_reanchor_on_resume(self):
        for setter in (self.component.set_shift_pressed, self.component.set_locked):
            self.device.drive.external_change(drive_value(0.0))
            self.device.output.external_change(output_value(-6.0))
            self.device.output.writes.clear()
            setter(True)
            self.assertTrue(all(control.mapped_parameter is None for control in self.controls.values()))
            self.physical("fader_7", 6.0, midi=40)
            self.assertEqual(self.device.output.writes, [])
            self.device.drive.external_change(drive_value(6.0))
            self.physical("encoder_23")
            setter(False)
            self.assertEqual(self.device.output.writes, [])
            self.physical("fader_7", midi=40)
            self.assertEqual(self.device.output.writes, [])
            self.physical("encoder_23", 12.0)
            self.assertAlmostEqual(output_db(self.device.output), -9.0)
        self.device.output.writes.clear()
        self.component.set_active(False)
        self.assertEqual(self.device.drive.listeners, [])
        self.assertEqual(self.device.output.listeners, [])
        self.device.drive.external_change(drive_value(18.0))
        self.physical("fader_7", midi=80)
        self.component.set_active(True)
        self.assertEqual(self.device.output.writes, [])
        self.physical("fader_7", 24.0, midi=100)
        self.assertAlmostEqual(output_db(self.device.output), -10.5)
        self.assertEqual(self.device.drive.writes, [])

    def test_auto_bypass_encoder_wakeup_keeps_single_drive_update_and_future_compensation(self):
        self.device.drive.external_change(drive_value(6.0))
        on = self.device.named["Device On"]
        on.notify_on_write = self.device.drive.notify_on_write = True

        def device_enabled_changed():
            self.device.drive.is_enabled = self.device.output.is_enabled = on.value > 0.5

        on.add_value_listener(device_enabled_changed)
        self.component._assignments["encoder_23"]["auto_bypass"] = {"off_at": "min"}
        on.external_change(0.0)
        self.component._update_assignments()
        self.assertIsNone(self.controls["encoder_23"].mapped_parameter)
        self.physical("encoder_23")
        self.assertEqual(on.value, 1.0)
        self.assertEqual(len(self.device.drive.writes), 1)
        self.assertAlmostEqual(self.device.drive.value, drive_value(6.0) + 1.0 / 127.0)
        self.assertEqual(self.device.output.writes, [])
        self.assertIs(self.controls["encoder_23"].mapped_parameter, self.device.drive)
        self.physical("encoder_23", 6.0 + 144.0 / 127.0)
        self.assertAlmostEqual(output_db(self.device.output), -6.0 - 36.0 / 127.0)
        self.assertEqual(len(self.device.drive.writes), 1)


if __name__ == "__main__":
    unittest.main()
