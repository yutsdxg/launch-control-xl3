"""Omnisphere's reversed controls keep native values and clear feedback."""

import unittest

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS


def omnisphere_device():
    device = fixtures.FakeInstrumentDevice("Omnisphere")
    names = (
        INSTRUMENT_ASSIGNMENTS.extract_custom_entry_name_and_options(entry)[0]
        for entry in INSTRUMENT_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER["Omnisphere"]
    )
    device.parameters = (fixtures.FakeParameter("Device On", parent=device),) + tuple(
        fixtures.FakeParameter(name, parent=device) for name in names if name
    )
    return device


class OmnisphereControlsTest(unittest.TestCase):
    def setUp(self):
        self.device = omnisphere_device()
        self.parameters = {parameter.name: parameter for parameter in self.device.parameters}
        self.selected = fixtures.FakeTrack(
            "Selected", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), self.device)
        )
        self.song = fixtures.FakeSong((self.selected,), selected_track=self.selected)
        self.component = INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.component.song = self.song

    def bind_button(self, number):
        button = fixtures.FakeButton(36 + number)
        getattr(self.component, "set_button_{}".format(number))(button)
        self.component.set_active(True)
        return button

    def led(self, button):
        return self.component._led_sender.last[button]

    def bind_encoder(self, number):
        control = NativeMappedControl()
        display = fixtures.FakeDisplayCommand()
        getattr(self.component, "set_encoder_{}_display".format(number))(display)
        getattr(self.component, "set_encoder_{}".format(number))(control)
        self.component.set_active(True)
        return control, display

    def test_five_pitch_controls_reverse_direction_without_a_native_mapping(self):
        for number, name in (
            (1, "1 A Transpose Semitones"),
            (3, "1 B Transpose Semitones"),
            (5, "1 C Transpose Semitones"),
            (7, "1 D Transpose Semitones"),
            (23, "1 A Tune Octave"),
        ):
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                parameter.value = 0.5
                control, _ = self.bind_encoder(number)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                self.assertIs(self.component._connected_parameters["encoder_{}".format(number)], parameter)

                control.receive(64)
                self.assertEqual(parameter.value, 0.5)
                control.receive(65)
                self.assertAlmostEqual(parameter.value, 0.5 - 1.0 / 127.0)
                control.receive(63)
                self.assertAlmostEqual(parameter.value, 0.5)
                self.assertEqual(control.native_updates, [])

    def test_pitch_updates_use_the_external_value_and_clamp_to_bounds(self):
        parameter = self.parameters["1 A Transpose Semitones"]
        control, _ = self.bind_encoder(1)
        parameter.value = 0.25
        control.receive(65)
        self.assertAlmostEqual(parameter.value, 0.25 - 1.0 / 127.0)

        parameter.value = parameter.min
        control.receive(127)
        self.assertEqual(parameter.value, parameter.min)
        parameter.value = parameter.max
        control.receive(0)
        self.assertEqual(parameter.value, parameter.max)

    def test_quantized_pitch_uses_one_item_or_integer_step(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.is_quantized = True
        for minimum, maximum, items, initial, expected in (
            (0.0, 1.0, ("Low", "Middle", "High"), 0.5, 0.0),
            (-2.0, 2.0, (), 0.0, -1.0),
        ):
            with self.subTest(value_items=items):
                parameter.min = minimum
                parameter.max = maximum
                parameter.value_items = items
                parameter.value = initial
                control, _ = self.bind_encoder(23)
                control.receive(65)
                self.assertEqual(parameter.value, expected)
                control.receive(63)
                self.assertEqual(parameter.value, initial)

    def test_shift_pitch_preview_keeps_values_and_restores_manual_direction(self):
        parameter = self.parameters["1 A Transpose Semitones"]
        parameter.value = 0.5
        control, display = self.bind_encoder(1)
        self.component.set_shift_pressed(True)
        for value in (65, 63, 127):
            control.receive(value)
            self.component._update_assignments(force=True)
            self.assertEqual(parameter.value, 0.5)
            self.assertIsNone(control.mapped_parameter)
        self.assertEqual(display_lines(display)[1:], (parameter.name[:16], "0.5"))

        self.component.set_shift_pressed(False)
        self.assertIsNone(control.mapped_parameter)
        control.receive(65)
        self.assertLess(parameter.value, 0.5)
        self.assertEqual(control.native_updates, [])

    def test_level_and_replacement_instrument_keep_native_clockwise_direction(self):
        level = self.parameters["1 A Level"]
        level.value = 0.5
        level_control, _ = self.bind_encoder(2)
        self.assertIs(level_control.mapped_parameter, level)
        level_control.receive(65)
        self.assertGreater(level.value, 0.5)

        pitch_control, _ = self.bind_encoder(1)
        pitch = self.parameters["1 A Transpose Semitones"]
        replacement = fixtures.FakeInstrumentDevice("Replacement")
        parameter = replacement.parameters[1]
        parameter.value = 0.5
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()
        self.assertIs(pitch_control.mapped_parameter, parameter)
        self.assertIsNone(pitch_control.manual_led_parameter)
        pitch_control.receive(65)
        self.assertGreater(parameter.value, 0.5)
        self.assertEqual(len(pitch_control.native_updates), 1)
        self.assertEqual(pitch.value, pitch.min)

    def test_inactive_pitch_handler_does_not_change_another_modes_mapping(self):
        parameter = self.parameters["1 A Transpose Semitones"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(1)
        self.component.set_active(False)
        other = fixtures.FakeParameter("Other mode", value=0.5)
        control.connect_to(other)
        self.component.set_shift_pressed(True)
        self.component._update_assignments()
        self.component.set_shift_pressed(False)
        control.receive(65)
        self.assertIs(control.mapped_parameter, other)
        self.assertIsNone(control.manual_led_parameter)
        self.assertGreater(other.value, 0.5)
        self.assertEqual(parameter.value, 0.5)

    def test_bypass_is_dim_and_effects_enabled_are_lit_after_toggles(self):
        bypass = self.parameters["1 Bypass All Effects"]
        button = self.bind_button(5)
        self.assertEqual(self.led(button), ("instrument-button", True))

        button.receive(127)
        self.assertEqual(bypass.value, bypass.max)
        self.assertEqual(self.led(button), ("instrument-button", False))
        button.receive(0)
        self.assertEqual(bypass.value, bypass.max)
        self.assertEqual(self.led(button), ("instrument-button", False))

        button.receive(127)
        self.assertEqual(bypass.value, bypass.min)
        self.assertEqual(self.led(button), ("instrument-button", True))

    def test_external_bypass_changes_refresh_the_inverted_led(self):
        bypass = self.parameters["1 Bypass All Effects"]
        button = self.bind_button(5)
        bypass.value = bypass.max
        self.component._update_assignments()
        self.assertEqual(self.led(button), ("instrument-button", False))

        bypass.value = bypass.min
        self.component.refresh_led_feedback()
        self.assertEqual(self.led(button), ("instrument-button", True))

    def test_other_omnisphere_buttons_keep_their_original_led_polarity(self):
        for number, name in ((1, "1 A Layer On"), (6, "1 Arp On")):
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                button = self.bind_button(number)
                self.assertEqual(self.led(button), ("instrument-button", False))
                button.receive(127)
                self.assertEqual(parameter.value, parameter.max)
                self.assertEqual(self.led(button), ("instrument-button", True))

    def test_retargeting_to_another_instrument_removes_bypass_led_inversion(self):
        button = self.bind_button(5)
        replacement = fixtures.FakeInstrumentDevice("Replacement")
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()
        parameter = replacement.parameters[37]
        self.assertEqual(self.led(button), ("instrument-button", False))

        button.receive(127)
        self.assertEqual(parameter.value, parameter.max)
        self.assertEqual(self.led(button), ("instrument-button", True))

    def test_unavailable_bypass_stays_dark_without_toggling(self):
        bypass = self.parameters["1 Bypass All Effects"]
        button = self.bind_button(5)
        bypass.is_enabled = False
        self.component._update_assignments()
        self.assertEqual(self.led(button), ("instrument-button", None))
        button.receive(127)
        self.assertEqual(bypass.value, bypass.min)

        bypass.is_enabled = True
        self.component._update_assignments()
        self.assertEqual(self.led(button), ("instrument-button", True))
        self.song.view.selected_track = fixtures.FakeTrack("Empty")
        self.component._update_assignments()
        self.assertEqual(self.led(button), ("instrument-button", None))


if __name__ == "__main__":
    unittest.main()
