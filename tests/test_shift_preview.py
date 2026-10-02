"""Shift previews must also suppress Live's native parameter mapping path."""

import unittest

import test_mixing as fixtures


class NativeMappedControl(fixtures.FakeManualLedControl):
    """Apply a native mapping before delivering the script's value callback.

    This deliberately does not model Live's takeover algorithm; it detects a
    leaked mapping while Shift is held, which an ordinary listener fake misses.
    """

    def __init__(self, relative=True, identifier=88):
        super().__init__(identifier)
        self.relative = relative
        self.mapped_parameter = None
        self.native_updates = []

    def connect_to(self, parameter):
        super().connect_to(parameter)
        self.mapped_parameter = parameter

    def release_parameter(self):
        super().release_parameter()
        self.mapped_parameter = None

    def receive(self, value):
        parameter = self.mapped_parameter
        if parameter is not None and parameter.is_enabled:
            if self.relative:
                amount = (value - 64) * (parameter.max - parameter.min) / 127.0
                target = parameter.value + amount
            else:
                target = parameter.min + value * (parameter.max - parameter.min) / 127.0
            parameter.value = max(parameter.min, min(parameter.max, target))
            self.native_updates.append((parameter, parameter.value))
        super().receive(value)


def display_lines(display):
    return tuple("".join(chr(value) for value in field) for field in display.sent[-1][1])


class ParameterPreviewChecks:
    """The same native-mapping contract applies to both assignment components."""

    def bind(self, name):
        control = NativeMappedControl(relative=name.startswith("encoder_"))
        display = fixtures.FakeDisplayCommand()
        getattr(self.component, "set_{}_display".format(name))(display)
        getattr(self.component, "set_{}".format(name))(control)
        self.component.set_active(True)
        return control, display

    def test_encoder_and_fader_preview_disconnect_native_mapping_and_keep_display(self):
        for name in (self.encoder_name, self.fader_name):
            with self.subTest(control=name):
                control, display = self.bind(name)
                parameter = control.mapped_parameter
                parameter.value = 0.5
                self.component.set_shift_pressed(True)

                self.assertIsNone(control.mapped_parameter)
                self.assertIs(self.component._connected_parameters[name], parameter)
                if control.relative:
                    self.assertIs(control.manual_led_parameter, parameter)
                for value in (127, 0, 65):
                    control.receive(value)
                    self.assertTrue(display.sent[-1][3])
                    self.component._update_assignments()
                    self.assertIsNone(control.mapped_parameter)
                    self.assertEqual(parameter.value, 0.5)
                self.assertEqual(control.native_updates, [])
                self.assertEqual(display_lines(display), self.expected_lines(name, parameter))
                self.assertEqual(display.sent[-1][0], 98)
                self.assertFalse(display.sent[-1][2])

                self.component.set_shift_pressed(False)
                self.assertIs(control.mapped_parameter, parameter)
                self.assertIsNone(control.manual_led_parameter)
                self.assertEqual(parameter.value, 0.5)
                control.receive(65 if control.relative else 127)
                self.assertGreater(parameter.value, 0.5)
                self.assertEqual(len(control.native_updates), 1)

    def test_shift_before_control_assignment_never_connects_until_release(self):
        self.component.set_shift_pressed(True)
        control, display = self.bind(self.encoder_name)
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(control.connected, [])
        control.receive(65)
        parameter = self.component._connected_parameters[self.encoder_name]
        self.assertEqual(display_lines(display), self.expected_lines(self.encoder_name, parameter))

        self.component.set_shift_pressed(False)
        self.assertIs(control.mapped_parameter, parameter)

    def test_periodic_and_forced_refresh_keep_new_target_unmapped_until_release(self):
        control, display = self.bind(self.encoder_name)
        original = control.mapped_parameter
        original.value = 0.25
        self.component.set_shift_pressed(True)
        replacement = self.replace_selected_track()
        replacement.value = 0.75

        self.component._update_assignments()
        self.component._update_assignments(force=True)
        self.component.set_active(True)
        control.receive(65)

        self.assertIsNone(control.mapped_parameter)
        self.assertIs(self.component._connected_parameters[self.encoder_name], replacement)
        self.assertEqual((original.value, replacement.value), (0.25, 0.75))
        self.assertEqual(display_lines(display)[1:], (replacement.name, "0.75"))
        self.component.set_shift_pressed(False)
        self.assertIs(control.mapped_parameter, replacement)
        self.assertEqual(replacement.value, 0.75)
        control.receive(65)
        self.assertGreater(replacement.value, 0.75)
        self.assertEqual(original.value, 0.25)

    def test_unassigned_target_displays_control_name_and_stays_unmapped(self):
        for name in (self.encoder_name, self.fader_name):
            with self.subTest(control=name):
                control, display = self.bind(name)
                self.component.set_shift_pressed(True)
                self.song.view.selected_track = fixtures.FakeTrack("Empty")
                self.component._update_assignments()
                control.receive(65 if control.relative else 127)

                self.assertIsNone(control.mapped_parameter)
                self.assertEqual(
                    display_lines(display),
                    (name.replace("_", " ").title(), "Unassigned", ""),
                )
                self.component.set_shift_pressed(False)
                self.assertIsNone(control.mapped_parameter)

    def test_preview_refreshes_track_change_before_the_next_poll(self):
        control, display = self.bind(self.encoder_name)
        original = control.mapped_parameter
        original.value = 0.25
        self.component.set_shift_pressed(True)
        replacement = self.replace_selected_track()
        replacement.value = 0.75

        control.receive(65)

        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(display_lines(display)[1:], (replacement.name, "0.75"))
        self.assertEqual((original.value, replacement.value), (0.25, 0.75))

    def test_disabled_assignment_becomes_unassigned_and_can_recover_during_preview(self):
        control, display = self.bind(self.encoder_name)
        parameter = control.mapped_parameter
        self.component.set_shift_pressed(True)
        parameter.is_enabled = False
        control.receive(65)
        self.assertEqual(display_lines(display)[1], "Unassigned")
        self.assertIsNone(control.mapped_parameter)
        self.assertIsNone(control.manual_led_parameter)

        parameter.is_enabled = True
        control.receive(65)
        self.assertEqual(display_lines(display), self.expected_lines(self.encoder_name, parameter))
        self.assertIsNone(control.mapped_parameter)
        self.component.set_shift_pressed(False)
        self.assertIs(control.mapped_parameter, parameter)

    def test_repeated_shift_and_fader_repositioning_do_not_change_parameter_on_release(self):
        control, _ = self.bind(self.fader_name)
        parameter = control.mapped_parameter
        parameter.value = 0.37
        for start in (0, 127, 0):
            self.component.set_shift_pressed(True)
            self.component.set_shift_pressed(True)
            control.receive(start)
            control.receive(64)
            self.component.set_shift_pressed(False)
            self.component.set_shift_pressed(False)
            self.assertIs(control.mapped_parameter, parameter)
            self.assertEqual(parameter.value, 0.37)
        self.assertEqual(control.native_updates, [])
        control.receive(65)
        self.assertNotEqual(parameter.value, 0.37)

    def test_inactive_shift_changes_do_not_release_another_modes_mapping(self):
        control, _ = self.bind(self.encoder_name)
        self.component.set_active(False)
        other_parameter = fixtures.FakeParameter("Other mode", value=0.4)
        control.connect_to(other_parameter)
        release_count = control.release_count

        self.component.set_shift_pressed(True)
        self.component._update_assignments()
        self.component.set_shift_pressed(False)

        self.assertEqual(control.release_count, release_count)
        self.assertIs(control.mapped_parameter, other_parameter)


class FixedShiftPreviewTest(ParameterPreviewChecks, unittest.TestCase):
    setUp = fixtures.FixedAssignmentsTest.setUp
    encoder_name = "encoder_11"
    fader_name = "fader_3"

    def test_empty_fixed_slots_display_unassigned(self):
        self.component.set_shift_pressed(True)
        for name in ("encoder_10", "encoder_18", "fader_2"):
            with self.subTest(control=name):
                control, display = self.bind(name)
                control.receive(65)
                self.assertIsNone(control.mapped_parameter)
                self.assertEqual(display_lines(display), (name.replace("_", " ").title(), "Unassigned", ""))

    def expected_lines(self, name, parameter):
        return ("Device 4", parameter.name, str(parameter))

    def replace_selected_track(self):
        replacement = fixtures.FakeTrack(
            "Replacement", devices=tuple(fixtures.FakeDevice(index) for index in range(1, 10))
        )
        self.song.view.selected_track = replacement
        return replacement.devices[3].parameters[3]

    def test_track_volume_preview_displays_track_name_and_current_value(self):
        control, display = self.bind("fader_8")
        parameter = control.mapped_parameter
        parameter.value = 0.45
        self.component.set_shift_pressed(True)
        control.receive(127)
        self.assertEqual(display_lines(display), ("Selected", "Selected Volume", "0.45"))
        self.assertEqual(parameter.value, 0.45)

    def test_device_on_encoder_previews_state_without_toggling(self):
        control, display = self.bind("encoder_2")
        device_on = self.selected.devices[0].parameters[0]
        self.component.set_shift_pressed(True)
        control.receive(63)
        self.assertEqual(device_on.value, 1.0)
        self.assertEqual(display_lines(display), ("Device 1", "Device On", "1.0"))
        self.assertEqual(control.manual_led_rgb, ("device-toggle", 2, True))
        self.component.set_shift_pressed(False)
        control.receive(63)
        self.assertEqual(device_on.value, 0.0)

    def test_submode_encoder_previews_without_mode_solo_or_ab_changes(self):
        control, display = self.bind("encoder_1")
        metric_ab = fixtures.FakeInstrumentDevice("ADPTR MetricAB", parameter_count=4)
        for parameter, name in zip(metric_ab.parameters[1:], ("Selected Track", "Selected Cue", "AB Switch")):
            parameter.name = name
            parameter.value = 0.5
        self.song.master_track.devices = (metric_ab,)
        initial_values = tuple(parameter.value for parameter in metric_ab.parameters)
        self.component.set_shift_pressed(True)
        for submode, solo, expected in (
            (fixtures.FIXED_ASSIGNMENTS.LOOPCLOUD_SUBMODE, False, "Loopcloud"),
            (fixtures.FIXED_ASSIGNMENTS.LOOPCLOUD_SUBMODE, True, "Loopcloud"),
            (fixtures.FIXED_ASSIGNMENTS.METRIC_AB_SUBMODE, False, "MetricAB"),
        ):
            with self.subTest(submode=submode, solo=solo):
                self.component._loopcloud_metric_submode = submode
                self.loopcloud.solo = solo
                for value in (63, 65):
                    control.receive(value)
                    self.assertEqual(self.component._loopcloud_metric_submode, submode)
                    self.assertEqual(self.loopcloud.solo, solo)
                    self.assertEqual(display_lines(display), ("Mode", expected, ""))
                    self.assertEqual(tuple(p.value for p in metric_ab.parameters), initial_values)

    def test_special_parameter_steps_are_not_accumulated_during_preview(self):
        device = self.selected.devices[3]
        parameter = fixtures.FakeParameter(
            "Selected Cue", value=2.0, minimum=1.0, maximum=4.0,
            parent=device, is_quantized=True,
        )
        device.parameters = device.parameters[:3] + (parameter,) + device.parameters[4:]
        control, display = self.bind("encoder_11")
        control.receive(65)
        self.assertEqual(parameter.value, 2.0)
        self.component.set_shift_pressed(True)
        for _ in range(7):
            control.receive(65)
        self.assertEqual(parameter.value, 2.0)
        self.assertEqual(display_lines(display), ("Device 4", "Selected Cue", "2.0"))
        self.assertFalse(any(self.component._special_parameter_input_accumulators.values()))

        self.component.set_shift_pressed(False)
        control.receive(65)
        self.assertEqual(parameter.value, 2.0)
        control.receive(65)
        self.assertEqual(parameter.value, 3.0)

    def test_special_ab_switch_preview_does_not_change_value(self):
        device = self.selected.devices[3]
        device.name = device.class_display_name = "ADPTR MetricAB"
        parameter = fixtures.FakeParameter("AB Switch", value=0.0, parent=device)
        device.parameters = device.parameters[:3] + (parameter,) + device.parameters[4:]
        control, display = self.bind("encoder_11")
        self.component.set_shift_pressed(True)
        control.receive(65)
        self.assertEqual(parameter.value, 0.0)
        self.assertEqual(display_lines(display), ("ADPTR MetricAB", "AB Switch", "0.0"))
        self.component.set_shift_pressed(False)
        control.receive(65)
        self.assertEqual(parameter.value, 1.0)


class InstrumentShiftPreviewTest(ParameterPreviewChecks, unittest.TestCase):
    setUp = fixtures.InstrumentAssignmentsTest.setUp
    encoder_name = "encoder_1"
    fader_name = "fader_1"

    def expected_lines(self, name, parameter):
        return ("Instrument", parameter.name, str(parameter))

    def replace_selected_track(self):
        device = fixtures.FakeInstrumentDevice("Replacement Instrument")
        self.song.view.selected_track = fixtures.FakeTrack(
            "Replacement", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        )
        return device.parameters[1]

    def test_parameter_buttons_keep_working_while_shift_is_held(self):
        self.component.set_active(True)
        self.component.set_shift_pressed(True)
        button = fixtures.FakeButton()
        self.component.set_button_1(button)
        parameter = self.target_device.parameters[33]
        button.receive(127)
        self.assertEqual(parameter.value, parameter.max)
        button.receive(0)
        self.assertEqual(parameter.value, parameter.max)
        button.receive(127)
        self.assertEqual(parameter.value, parameter.min)


class ShiftRouterTest(unittest.TestCase):
    class Receiver:
        def __init__(self):
            self.events = []

        def set_shift_pressed(self, pressed):
            self.events.append(("shift", pressed))

        def set_encoder_1(self, control):
            self.events.append(("control", control))

    def test_mapping_gives_shift_button_to_router_only(self):
        mappings = fixtures.MAPPINGS.create_mappings(None)
        owners = [name for name, mapping in mappings.items() if mapping.get("shift_button") == "shift_button"]
        self.assertEqual(owners, ["Control_Router"])

    def test_element_special_handlers_follow_shift_and_detach_cleanly(self):
        class PreviewControl(NativeMappedControl):
            def set_shift_pressed(self, pressed):
                self.shift_pressed = pressed

        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        shift = fixtures.FakeButton()
        first, replacement = PreviewControl(), PreviewControl()
        router.set_shift_button(shift)
        router.set_encoder_1(first)
        self.assertFalse(first.shift_pressed)
        shift.receive(127)
        self.assertTrue(first.shift_pressed)
        router.set_encoder_1(replacement)
        self.assertFalse(first.shift_pressed)
        self.assertTrue(replacement.shift_pressed)
        shift.receive(0)
        self.assertFalse(replacement.shift_pressed)
        shift.receive(127)
        router.disconnect()
        self.assertEqual(shift.listeners, [])
        self.assertFalse(replacement.shift_pressed)

    def test_shift_routes_to_assignment_components_and_replaces_listener(self):
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        fixed, instrument, track_buttons = self.Receiver(), self.Receiver(), self.Receiver()
        first, replacement = fixtures.FakeButton(), fixtures.FakeButton()
        router.set_target_components(fixed, instrument, track_buttons)
        router.set_shift_button(first)
        first.receive(127)
        for receiver in (fixed, instrument):
            self.assertEqual(receiver.events[-1], ("shift", True))
        self.assertEqual(track_buttons.events, [])

        router.set_shift_button(replacement)
        self.assertEqual(first.listeners, [])
        replacement.receive(127)
        replacement.receive(0)
        for receiver in (fixed, instrument):
            self.assertEqual(receiver.events[-1], ("shift", False))
        self.assertEqual(len(replacement.listeners), 1)
        router.set_shift_button(replacement)
        self.assertEqual(len(replacement.listeners), 1)

    def test_shift_state_reaches_late_targets_before_controls_are_connected(self):
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        shift, control = fixtures.FakeButton(), NativeMappedControl()
        router.set_shift_button(shift)
        router.set_encoder_1(control)
        shift.receive(127)
        fixed, instrument = self.Receiver(), self.Receiver()
        router.set_target_components(fixed, instrument)
        for receiver in (fixed, instrument):
            self.assertEqual(receiver.events[:2], [("shift", True), ("control", control)])


class SharedModeShiftPreviewTest(unittest.TestCase):
    def test_mode_switch_while_held_only_reconnects_active_mode_after_release(self):
        track = fixtures.FakeTrack(
            "Selected", devices=tuple(fixtures.FakeInstrumentDevice("Device {}".format(i)) for i in range(9))
        )
        song = fixtures.FakeSong((track,))
        fixed = fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent()
        instrument = fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        fixed.song = instrument.song = song
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        control, shift = NativeMappedControl(), fixtures.FakeButton()
        display = fixtures.FakeDisplayCommand()
        router.set_target_components(fixed, instrument)
        router.set_encoder_11(control)
        router.set_encoder_11_display(display)
        router.set_shift_button(shift)
        fixed_target = control.mapped_parameter
        fixed_target.value = 0.3
        instrument_target = track.devices[2].parameters[11]
        instrument_target.value = 0.6

        for to_instrument in (True, False, True):
            shift.receive(127)
            if to_instrument:
                fixed.set_active(False)
                instrument.set_active(True)
                target = instrument_target
            else:
                instrument.set_active(False)
                fixed.set_active(True)
                target = fixed_target
            fixed._update_assignments()
            instrument._update_assignments()
            self.assertIsNone(control.mapped_parameter)
            control.receive(65)
            self.assertEqual((fixed_target.value, instrument_target.value), (0.3, 0.6))
            self.assertEqual(display_lines(display)[1:], (target.name, str(target)))
            shift.receive(0)
            self.assertIs(control.mapped_parameter, target)
            self.assertEqual((fixed_target.value, instrument_target.value), (0.3, 0.6))


if __name__ == "__main__":
    unittest.main()
