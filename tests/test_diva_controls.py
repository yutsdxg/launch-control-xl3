"""Diva Tune controls use fixed semitone values without native MIDI writes."""

import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS
TUNE_CONTROLS = ((1, "Tune1"), (4, "Tune2"))
OCTAVE_VALUES = (-24, -12, 0, 12, 24)


def diva_device(parameter_type=fixtures.FakeParameter):
    device = fixtures.FakeInstrumentDevice("Diva")
    parameters = [fixtures.FakeParameter("Device On", parent=device)]
    for entry in INSTRUMENT_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER["Diva"]:
        name, _ = INSTRUMENT_ASSIGNMENTS.extract_custom_entry_name_and_options(entry)
        if name:
            if name in ("Tune1", "Tune2"):
                parameters.append(parameter_type(name, minimum=-30, maximum=30, parent=device))
            else:
                parameters.append(fixtures.FakeParameter(name, parent=device))
    device.parameters = tuple(parameters)
    return device


class DivaControlsTest(unittest.TestCase):
    def setUp(self):
        self.device = diva_device()
        self.parameters = {parameter.name: parameter for parameter in self.device.parameters}
        self.selected = fixtures.FakeTrack(
            "Selected", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), self.device)
        )
        self.song = fixtures.FakeSong((self.selected,), selected_track=self.selected)
        self.component = INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.component.song = self.song

    def bind_encoder(self, number):
        control = NativeMappedControl()
        display = fixtures.FakeDisplayCommand()
        getattr(self.component, "set_encoder_{}_display".format(number))(display)
        getattr(self.component, "set_encoder_{}".format(number))(control)
        self.component.set_active(True)
        return control, display

    def assert_step(self, control, parameter, midi, expected):
        previous = parameter.value
        control.receive(midi)
        self.assertEqual(parameter.value, previous)
        control.receive(midi)
        self.assertEqual(parameter.value, expected)

    def retarget(self, device):
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        self.component._update_assignments()

    def test_both_tunes_step_through_all_octaves_in_normal_direction_without_native_writes(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                parameter.value = OCTAVE_VALUES[0]
                control, _ = self.bind_encoder(number)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                for expected in OCTAVE_VALUES[1:]:
                    self.assert_step(control, parameter, 65, expected)
                for expected in reversed(OCTAVE_VALUES[:-1]):
                    self.assert_step(control, parameter, 63, expected)
                self.assertEqual(control.native_updates, [])

    def test_acceleration_counts_once_and_reversing_restarts_the_threshold(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                self.assert_step(control, parameter, 127, 12)
                self.assert_step(control, parameter, 0, 0)
                for midi in (65, 63, 65, 64):
                    control.receive(midi)
                    self.assertEqual(parameter.value, 0)
                control.receive(127)
                self.assertEqual(parameter.value, 12)
                self.assertEqual(control.native_updates, [])

    def test_endpoints_clamp_to_octaves_inside_the_parameter_range(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                for current, midi, expected in ((-24, 63, -24), (-30, 63, -24), (24, 65, 24), (30, 65, 24)):
                    parameter.value = current
                    self.assert_step(control, parameter, midi, expected)

    def test_latest_external_value_selects_the_nearest_octave_before_stepping(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                for current, midi, expected in ((-13, 65, 0), (13, 63, 0), (2, 65, 12), (-2, 63, -12)):
                    parameter.value = 0
                    control.receive(midi)
                    self.assertEqual(parameter.value, 0)
                    parameter.value = current
                    self.component._update_assignments()
                    control.receive(midi)
                    self.assertEqual(parameter.value, expected)

    def test_shift_is_display_only_and_resets_pending_steps(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, display = self.bind_encoder(number)
                control.receive(65)
                self.component.set_shift_pressed(True)
                for midi in (65, 63, 127):
                    control.receive(midi)
                    self.component._update_assignments(force=True)
                    self.assertEqual(parameter.value, 0)
                    self.assertIsNone(control.mapped_parameter)
                self.assertEqual(display_lines(display)[1:], (name, str(parameter.value)))
                self.component.set_shift_pressed(False)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                self.assert_step(control, parameter, 65, 12)
                self.assertEqual(control.native_updates, [])

    def test_retargeting_resets_pending_steps_and_keeps_new_tune_manually_mapped(self):
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                self.retarget(self.device)
                original = self.parameters[name]
                control, _ = self.bind_encoder(number)
                control.receive(65)
                replacement = diva_device()
                parameter = next(item for item in replacement.parameters if item.name == name)
                self.retarget(replacement)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                self.assert_step(control, parameter, 65, 12)
                self.assertEqual(original.value, 0)
                self.assertEqual(control.native_updates, [])

    def test_other_diva_encoders_keep_native_continuous_mapping(self):
        parameter = self.parameters["Shape1"]
        control, _ = self.bind_encoder(2)
        self.assertIs(control.mapped_parameter, parameter)
        self.assertIsNone(control.manual_led_parameter)
        control.receive(65)
        self.assertGreater(parameter.value, 0)
        self.assertEqual(len(control.native_updates), 1)

    def test_discrete_count_without_direction_inversion_also_uses_manual_steps(self):
        parameter = self.parameters["Tune1"]
        with patch.object(self.component, "_custom_parameter_options", return_value={"discrete_count": 5}):
            control, _ = self.bind_encoder(1)
            self.assertIsNone(control.mapped_parameter)
            self.assert_step(control, parameter, 65, 15)
            self.assert_step(control, parameter, 63, 0)
            self.assertEqual(control.native_updates, [])

    def test_fixed_octaves_never_probe_value_items_or_display_formatter(self):
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
                raise AssertionError("Diva Tune must not probe arbitrary display values")

        device = diva_device(ProbeCountingParameter)
        self.retarget(device)
        for number, name in TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = next(item for item in device.parameters if item.name == name)
                control, _ = self.bind_encoder(number)
                for quantized in (False, True):
                    parameter.is_quantized = quantized
                    self.component._update_assignments(force=True)
                    self.assert_step(control, parameter, 65, 12)
                    self.assert_step(control, parameter, 63, 0)
                self.assertEqual(parameter.value_items_reads, 0)
                self.assertEqual(parameter.formatter_calls, 0)


if __name__ == "__main__":
    unittest.main()
