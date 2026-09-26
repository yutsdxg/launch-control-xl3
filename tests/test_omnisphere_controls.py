"""Only Omnisphere Tune Octave uses two-event steps; transpose stays continuous."""

import unittest

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS
PITCH_CONTROLS = (
    (1, "1 A Transpose Semitones"),
    (3, "1 B Transpose Semitones"),
    (5, "1 C Transpose Semitones"),
    (7, "1 D Transpose Semitones"),
    (23, "1 A Tune Octave"),
)


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

    def assert_step(self, control, parameter, value, expected):
        previous = parameter.value
        control.receive(value)
        self.assertAlmostEqual(parameter.value, previous)
        control.receive(value)
        self.assertAlmostEqual(parameter.value, expected)

    def test_pitch_controls_have_reversed_manual_mapping(self):
        for number, name in PITCH_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                self.assertIs(self.component._connected_parameters["encoder_{}".format(number)], parameter)
                self.assertEqual(control.native_updates, [])

    def test_transpose_controls_keep_continuous_input_and_acceleration(self):
        for number, name in PITCH_CONTROLS[:4]:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                parameter.value = 0.6
                control, _ = self.bind_encoder(number)
                expected = parameter.value
                for value in (65, 65, 63, 68, 60, 64):
                    expected += (64 - value) / 127.0
                    control.receive(value)
                    self.assertAlmostEqual(parameter.value, expected)
                self.assertEqual(control.native_updates, [])

    def test_transpose_controls_clamp_at_raw_endpoints(self):
        for number, name in PITCH_CONTROLS[:4]:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                parameter.value = 0.01
                control.receive(127)
                self.assertEqual(parameter.value, 0.0)
                parameter.value = 0.99
                control.receive(0)
                self.assertEqual(parameter.value, 1.0)

    def test_tune_octave_moves_one_of_five_stages_after_two_inputs(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        for expected in (0.25, 0.0, 0.0):
            self.assert_step(control, parameter, 65, expected)
        for expected in (0.25, 0.5, 0.75, 1.0, 1.0):
            self.assert_step(control, parameter, 63, expected)
        self.assertEqual(control.native_updates, [])

    def test_tune_octave_accelerated_input_still_moves_one_stage(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        self.assert_step(control, parameter, 127, 0.25)
        self.assert_step(control, parameter, 0, 0.5)
        # Each event counts once, even when its MIDI magnitude differs.
        control.receive(65)
        self.assertEqual(parameter.value, 0.5)
        control.receive(127)
        self.assertEqual(parameter.value, 0.25)

    def test_neutral_input_does_not_change_tune_or_pending_direction(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        control.receive(64)
        self.assertEqual(parameter.value, 0.5)
        control.receive(65)
        control.receive(64)
        self.assertEqual(parameter.value, 0.5)
        control.receive(65)
        self.assertEqual(parameter.value, 0.25)

    def test_tune_direction_change_restarts_the_two_event_threshold(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        for value in (65, 63, 65):
            control.receive(value)
            self.assertEqual(parameter.value, 0.5)
        control.receive(65)
        self.assertEqual(parameter.value, 0.25)

    def test_tune_step_uses_the_latest_external_value(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        control.receive(65)
        parameter.value = 0.75
        self.component._update_assignments()
        control.receive(65)
        self.assertEqual(parameter.value, 0.5)

    def test_tune_step_uses_nearest_stage_from_arbitrary_raw_value(self):
        parameter = self.parameters["1 A Tune Octave"]
        control, _ = self.bind_encoder(23)
        for current, value, expected in (
            (0.55, 65, 0.25),
            (0.55, 63, 0.75),
            (0.70, 65, 0.5),
            (0.30, 63, 0.5),
        ):
            with self.subTest(current=current, value=value):
                parameter.value = current
                self.assert_step(control, parameter, value, expected)

    def test_tune_stages_support_non_normalized_raw_bounds(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.min = -2.0
        parameter.max = 2.0
        parameter.value = 0.0
        parameter.is_quantized = True
        control, _ = self.bind_encoder(23)
        self.assert_step(control, parameter, 65, -1.0)
        self.assert_step(control, parameter, 63, 0.0)

    def test_tune_does_not_probe_value_items_or_arbitrary_display_values(self):
        class ProbeCountingParameter(fixtures.FakeParameter):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.value_items_reads = 0
                self.formatter_calls = 0

            def __getattribute__(self, name):
                if name == "value_items":
                    self.value_items_reads += 1
                    raise RuntimeError("Only quantized parameters have value items")
                return super().__getattribute__(name)

            def str_for_value(self, value):
                self.formatter_calls += 1
                raise AssertionError("Tune must not probe arbitrary display values")

        original = self.parameters["1 A Tune Octave"]
        parameter = ProbeCountingParameter(original.name, value=0.5, parent=self.device)
        self.device.parameters = tuple(
            parameter if item is original else item for item in self.device.parameters
        )
        control, _ = self.bind_encoder(23)
        for _ in range(5):
            self.component._update_assignments(force=True)
        self.assert_step(control, parameter, 65, 0.25)
        self.assert_step(control, parameter, 63, 0.5)
        self.assertEqual(parameter.value_items_reads, 0)
        self.assertEqual(parameter.formatter_calls, 0)

    def test_tune_fixed_stages_take_precedence_over_quantized_items(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.is_quantized = True
        parameter.value_items = tuple(str(value) for value in range(49))
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        self.assert_step(control, parameter, 65, 0.25)
        self.assert_step(control, parameter, 63, 0.5)

    def test_shift_tune_preview_keeps_values_and_resets_pending_input(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, display = self.bind_encoder(23)
        control.receive(65)
        self.component.set_shift_pressed(True)
        for value in (65, 63, 127):
            control.receive(value)
            self.component._update_assignments(force=True)
            self.assertEqual(parameter.value, 0.5)
            self.assertIsNone(control.mapped_parameter)
        self.assertEqual(display_lines(display)[1:], (parameter.name[:16], "0.5"))

        self.component.set_shift_pressed(False)
        self.assertIsNone(control.mapped_parameter)
        self.assert_step(control, parameter, 65, 0.25)
        self.assertEqual(control.native_updates, [])

    def test_inactive_tune_control_resets_pending_input(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        control.receive(65)
        self.component.set_active(False)
        control.receive(65)
        self.assertEqual(parameter.value, 0.5)
        self.component.set_active(True)
        self.assert_step(control, parameter, 65, 0.25)

    def test_retargeting_tune_control_resets_pending_input(self):
        parameter = self.parameters["1 A Tune Octave"]
        parameter.value = 0.5
        control, _ = self.bind_encoder(23)
        control.receive(65)

        replacement = omnisphere_device()
        replacement_pitch = next(
            item for item in replacement.parameters if item.name == parameter.name
        )
        replacement_pitch.value = 0.5
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()

        self.assertIsNone(control.mapped_parameter)
        self.assertIs(control.manual_led_parameter, replacement_pitch)
        self.assert_step(control, replacement_pitch, 65, 0.25)
        self.assertEqual(parameter.value, 0.5)

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
