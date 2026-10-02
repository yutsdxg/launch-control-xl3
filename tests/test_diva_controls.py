"""Diva Tune controls use normalized values without native MIDI writes."""

import struct
import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS
TUNE_CONTROLS = ((1, "Tune1"), (5, "Tune2"))
TRIPLE_TUNE_CONTROLS = TUNE_CONTROLS + ((9, "Tune3"),)
# Independently observed through Diva 1.4.8's VST3 controller, parameter IDs
# 86/87: these normalized values display -24, -12, 0, +12, +24 semitones.
# Keep these expectations separate from the configuration under test.
OCTAVE_VALUES = (0.1, 0.3, 0.5, 0.7, 0.9)


class DivaTuneParameter(fixtures.FakeParameter):
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        # The real controller reads assigned values back at float32 precision.
        self._value = struct.unpack("f", struct.pack("f", value))[0]

    def __str__(self):
        return "{:.2f}".format(self.value * 60.0 - 30.0)


def diva_device(parameter_type=DivaTuneParameter):
    device = fixtures.FakeInstrumentDevice("Diva")
    parameters = [fixtures.FakeParameter("Device On", parent=device)]
    # Parameter inventory is independent of physical control assignments. In
    # particular, Model and inactive models' parameters remain exposed in Live.
    names = (
        "Model", "Tune1", "Tune2", "Tune3", "Volume1", "Volume2", "Volume3",
        "Feedback1", "NoiseVol", "Shape1", "Shape2", "Shape3", "EcoWave1", "EcoWave2",
        "PulseWidth", "FM", "Sync2", "Sine2On", "OscMix", "Triangle1On", "Saw1On", "Pwm1On",
        "Noise1On", "Triangle2On", "Saw2On", "Pulse2On", "SawShape", "PulseShape",
        "SuboscShape", "DigitalType1", "DigitalType2", "DigitalShape2", "DigitalShape3",
        "DigitalShape4", "DepthMod Dpt1", "DepthMod Src1", "DepthMod Dpt1", "DepthMod Src1",
        "Frequency", "Resonance", "Freq Mod Depth", "KeyFollow", "Filter FM", "Mode", "Output",
        "Attack", "Decay", "Sustain", "Release", "Attack", "Decay", "Sustain", "Release",
        "OnOff", "Active #FX1", "Active #FX2",
    )
    for name in names:
        if name in ("Tune1", "Tune2", "Tune3"):
            parameters.append(parameter_type(name, value=0.5, minimum=0.0, maximum=1.0, parent=device))
        else:
            parameters.append(fixtures.FakeParameter(name, parent=device))
    device.parameters = tuple(parameters)
    return device


class DivaControlsTest(unittest.TestCase):
    def setUp(self):
        self.device = diva_device()
        self.parameters = {}
        for parameter in self.device.parameters:
            self.parameters.setdefault(parameter.name, parameter)
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
        self.assertAlmostEqual(parameter.value, expected, places=6)

    def retarget(self, device):
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        self.component._update_assignments()

    def test_all_three_tunes_step_through_all_octaves_in_normal_direction_without_native_writes(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
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

    def test_all_three_tunes_leave_zero_pitch_after_two_inputs_in_either_direction(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                self.assertEqual((parameter.min, parameter.max), (0.0, 1.0))
                self.assertEqual(str(parameter), "0.00")
                self.assert_step(control, parameter, 65, 0.7)
                self.assertEqual(str(parameter), "12.00")
                parameter.value = 0.5
                self.assert_step(control, parameter, 63, 0.3)
                self.assertEqual(str(parameter), "-12.00")
                self.assertEqual(control.native_updates, [])

    def test_acceleration_counts_once_and_reversing_restarts_the_threshold(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                self.assert_step(control, parameter, 127, 0.7)
                self.assert_step(control, parameter, 0, 0.5)
                for midi in (65, 63, 65, 64):
                    control.receive(midi)
                    self.assertEqual(parameter.value, 0.5)
                control.receive(127)
                self.assertAlmostEqual(parameter.value, 0.7, places=6)
                self.assertEqual(control.native_updates, [])

    def test_endpoints_clamp_to_octaves_inside_the_parameter_range(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                for current, midi, expected in (
                    (0.1, 63, 0.1), (0.0, 63, 0.1), (0.9, 65, 0.9), (1.0, 65, 0.9)
                ):
                    parameter.value = current
                    self.assert_step(control, parameter, midi, expected)

    def test_latest_external_value_selects_the_nearest_octave_before_stepping(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, _ = self.bind_encoder(number)
                for current, midi, expected in (
                    (0.28, 65, 0.5), (0.72, 63, 0.5), (0.53, 65, 0.7), (0.47, 63, 0.3)
                ):
                    parameter.value = 0.5
                    control.receive(midi)
                    self.assertEqual(parameter.value, 0.5)
                    parameter.value = current
                    self.component._update_assignments()
                    control.receive(midi)
                    self.assertAlmostEqual(parameter.value, expected, places=6)

    def test_shift_is_display_only_and_resets_pending_steps(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = self.parameters[name]
                control, display = self.bind_encoder(number)
                control.receive(65)
                self.component.set_shift_pressed(True)
                for midi in (65, 63, 127):
                    control.receive(midi)
                    self.component._update_assignments(force=True)
                    self.assertEqual(parameter.value, 0.5)
                    self.assertIsNone(control.mapped_parameter)
                self.assertEqual(display_lines(display)[1:], (name, "0.00"))
                self.component.set_shift_pressed(False)
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, parameter)
                self.assert_step(control, parameter, 65, 0.7)
                self.assertEqual(control.native_updates, [])

    def test_retargeting_resets_pending_steps_and_keeps_new_tune_manually_mapped(self):
        for number, name in TRIPLE_TUNE_CONTROLS:
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
                self.assert_step(control, parameter, 65, 0.7)
                self.assertEqual(original.value, 0.5)
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
            self.assert_step(control, parameter, 65, 0.75)
            self.assert_step(control, parameter, 63, 0.5)
            self.assertEqual(control.native_updates, [])

    def test_fixed_octaves_never_probe_value_items_or_display_formatter(self):
        class ProbeCountingParameter(DivaTuneParameter):
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
        for number, name in TRIPLE_TUNE_CONTROLS:
            with self.subTest(parameter=name):
                parameter = next(item for item in device.parameters if item.name == name)
                control, _ = self.bind_encoder(number)
                for quantized in (False, True):
                    parameter.is_quantized = quantized
                    self.component._update_assignments(force=True)
                    self.assert_step(control, parameter, 65, 0.7)
                    self.assert_step(control, parameter, 63, 0.5)
                self.assertEqual(parameter.value_items_reads, 0)
                self.assertEqual(parameter.formatter_calls, 0)


if __name__ == "__main__":
    unittest.main()
