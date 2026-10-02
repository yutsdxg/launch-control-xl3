"""Diva OSC models select their upper controls and retain shared assignments."""

import unittest
from contextlib import contextmanager
from unittest.mock import patch

import test_mixing as fixtures
from test_diva_controls import TUNE_CONTROLS, diva_device
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS
WAVE_CONTROLS = ((2, "Shape1", "EcoWave1"), (6, "Shape2", "EcoWave2"))
# Expected production layouts are independent of the configuration under test.
MODEL_ASSIGNMENTS = {
    0.0: {1: "Tune1", 2: "Shape1", 3: "Volume1", 5: "Tune2", 6: "Shape2",
          7: "Volume2", 9: "Tune3", 10: "Shape3", 11: "Volume3", 16: "NoiseVol"},
    0.25: {1: "Tune1", 2: "PulseWidth", 3: "FM", 5: "Tune2", 6: "Sync2", 7: "OscMix",
           9: "Triangle1On", 10: "Saw1On", 11: "Pwm1On", 12: "Noise1On",
           13: "Triangle2On", 14: "Saw2On", 15: "Pulse2On", 16: "Sine2On"},
    0.5: {1: "Tune1", 2: "SawShape", 3: "PulseShape", 4: "SuboscShape",
          9: "PulseWidth", 11: "Volume3", 12: "NoiseVol"},
    0.75: {1: "Tune1", 2: "EcoWave1", 3: "Volume1", 5: "Tune2", 6: "EcoWave2",
           7: "Volume2", 9: "PulseWidth"},
    1.0: {1: "Tune1", 2: "DigitalType1", 3: "FM", 5: "Tune2", 6: "DigitalType2",
          7: "OscMix", 9: "PulseWidth", 10: "DigitalShape2", 13: "DigitalShape3",
          14: "DigitalShape4"},
}
MANUAL_PARAMETER_NAMES = frozenset((
    "Tune1", "Tune2", "Tune3", "EcoWave1", "EcoWave2", "Sync2", "Sine2On", "Triangle1On", "Saw1On",
    "Pwm1On", "Noise1On", "Triangle2On", "Saw2On", "Pulse2On", "SawShape", "PulseShape",
    "SuboscShape", "DigitalType1", "DigitalType2", "DepthMod Dpt1",
))
# Verified through Diva's VST3 controller: normalized endpoints/thirds select
# displayed waveform numbers 1, 2, 3, 4 for both EcoWave parameters.
ECO_WAVE_VALUES = (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0)


@contextmanager
def override_rules(*assignments):
    rules = tuple(
        {
            "when": {"parameter": "Model", "occurrence": 1, "normalized_value": 0.75},
            "assignments": entries,
        }
        for entries in assignments
    )
    # Generic rule behavior uses its own baseline and does not depend on Diva's
    # model-specific production layout.
    base = (None, "Shape1", None, None, "Shape2")
    with patch.object(INSTRUMENT_ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_ORDER_INDEX", {"diva": base}):
        with patch.object(INSTRUMENT_ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
            yield


class ModelParameter(fixtures.FakeParameter):
    def __init__(self, *args, **kwargs):
        self.value_reads = 0
        self.display_calls = 0
        self.value_items_reads = 0
        super().__init__(*args, **kwargs)

    @property
    def value(self):
        self.value_reads += 1
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def __getattribute__(self, name):
        if name == "value_items":
            self.value_items_reads += 1
            raise AssertionError("Model matching must not inspect value_items")
        return super().__getattribute__(name)

    def __str__(self):
        self.display_calls += 1
        raise AssertionError("Model matching must not depend on display text")

    def str_for_value(self, value):
        self.display_calls += 1
        raise AssertionError("Model matching must not probe display values")


class WaveParameter(fixtures.FakeParameter):
    def __init__(self, *args, **kwargs):
        self.writes = []
        super().__init__(*args, **kwargs)
        self.writes.clear()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self.writes.append(value)
        self._value = value


def model_device(value=0.0, minimum=0.0, maximum=1.0, include_model=True, missing=()):
    device = diva_device()
    parameters = [parameter for parameter in device.parameters
                  if parameter.name not in missing and parameter.name not in ("Model", "EcoWave1", "EcoWave2")]
    for index, parameter in enumerate(parameters):
        if parameter.name in ("Shape1", "Shape2"):
            parameters[index] = WaveParameter(parameter.name, value=0.2, parent=device)
    for name in ("EcoWave1", "EcoWave2"):
        if name not in missing:
            parameters.append(WaveParameter(name, value=0.6, parent=device))
    model = None
    if include_model:
        model = ModelParameter("Model", value=value, minimum=minimum, maximum=maximum, parent=device)
        parameters.append(model)
    device.parameter_read_count = 0
    device.parameters = fixtures.CountingParameterSequence(device, parameters)
    by_name = {}
    for parameter in parameters:
        by_name.setdefault(parameter.name, parameter)
    return device, by_name, model


class ConditionalInstrumentAssignmentsTest(unittest.TestCase):
    def setUp(self):
        self.install_device(*model_device())

    def install_device(self, device, parameters, model):
        self.device, self.parameters, self.model = device, parameters, model
        self.selected = fixtures.FakeTrack(
            "Selected", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        )
        self.song = fixtures.FakeSong((self.selected,), selected_track=self.selected)
        self.component = INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.component.song = self.song
        self.controls = {}
        self.displays = {}

    def bind(self, *numbers):
        for number in numbers:
            control, display = NativeMappedControl(), fixtures.FakeDisplayCommand()
            getattr(self.component, "set_encoder_{}_display".format(number))(display)
            getattr(self.component, "set_encoder_{}".format(number))(control)
            self.controls[number], self.displays[number] = control, display
        self.component.set_active(True)

    def assert_wave_targets(self, eco, parameters=None, triple=True):
        parameters = self.parameters if parameters is None else parameters
        for number, normal, alternate in WAVE_CONTROLS:
            expected = parameters.get(alternate if eco else normal) if eco or triple else None
            self.assertIs(self.controls[number].mapped_parameter, None if eco else expected)
            self.assertIs(self.controls[number].manual_led_parameter, expected if eco else None)
            if expected is not None:
                self.assertEqual(display_lines(self.displays[number])[1], expected.name)

    def assert_upper_targets(self, model):
        names = {8: "Feedback1"}
        names.update(MODEL_ASSIGNMENTS.get(model, {}))
        for number in range(1, 17):
            name = names.get(number)
            parameter = self.parameters.get(name)
            manual = name in MANUAL_PARAMETER_NAMES
            self.assertIs(self.controls[number].mapped_parameter, None if manual else parameter)
            self.assertIs(self.controls[number].manual_led_parameter, parameter if manual else None)

    def assert_two_input_step(self, control, parameter, midi, expected):
        previous = parameter.value
        writes = len(parameter.writes)
        control.receive(midi)
        self.assertEqual(parameter.value, previous)
        self.assertEqual(len(parameter.writes), writes)
        control.receive(midi)
        self.assertAlmostEqual(parameter.value, expected)
        self.assertEqual(len(parameter.writes), writes + (abs(previous - expected) > 1e-9))

    def test_initial_eco_model_uses_eco_waves_without_changing_values(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        self.assert_wave_targets(True)
        for parameter in self.parameters.values():
            if isinstance(parameter, WaveParameter):
                self.assertEqual(parameter.writes, [])

    def test_models_select_only_their_upper_assignments_and_preserve_shared_controls(self):
        self.bind(*range(1, 25))
        faders = (NativeMappedControl(relative=False), NativeMappedControl(relative=False))
        self.component.set_fader_1(faders[0])
        self.component.set_fader_5(faders[1])
        attacks = [parameter for parameter in self.device.parameters if parameter.name == "Attack"]
        shared = {
            number: (self.controls[number].mapped_parameter, self.controls[number].manual_led_parameter)
            for number in range(17, 25)
        }
        self.assertIs(shared[22][1], self.parameters["DepthMod Dpt1"])
        for normalized in (0.0, 0.25, 0.5, 1.0):
            with self.subTest(model=normalized):
                self.model.value = normalized
                self.component._update_assignments()
                self.assert_upper_targets(normalized)
                self.model.value = 0.75
                self.component._update_assignments()
                self.assert_upper_targets(0.75)
                self.model.value = normalized
                self.component._update_assignments()
                self.assert_upper_targets(normalized)
                for number, (parameter, led_parameter) in shared.items():
                    self.assertIs(self.controls[number].mapped_parameter, parameter)
                    self.assertIs(self.controls[number].manual_led_parameter, led_parameter)
                self.assertIs(faders[0].mapped_parameter, attacks[0])
                self.assertIs(faders[1].mapped_parameter, attacks[1])
        for parameter in self.parameters.values():
            if isinstance(parameter, WaveParameter):
                self.assertEqual(parameter.writes, [])

    def test_encoder_input_uses_native_shape_and_manual_eco_without_double_writes(self):
        self.bind(2, 6)
        for eco in (False, True, False):
            self.model.value = 0.75 if eco else 0.0
            self.component._update_assignments()
            for number, normal, alternate in WAVE_CONTROLS:
                target = self.parameters[alternate if eco else normal]
                previous = target.value
                writes = {name: len(self.parameters[name].writes) for name in (normal, alternate)}
                control = self.controls[number]
                native_count = len(control.native_updates)
                if eco:
                    self.assert_two_input_step(control, target, 65, 1.0)
                    self.assertEqual(len(control.native_updates), native_count)
                else:
                    control.receive(65)
                    self.assertAlmostEqual(target.value, previous + 1.0 / 127.0)
                    self.assertEqual(len(control.native_updates), native_count + 1)
                for name in (normal, alternate):
                    self.assertEqual(len(self.parameters[name].writes), writes[name] + (name == target.name))

    def test_both_eco_waves_step_through_four_values_with_two_inputs_and_stop_at_endpoints(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        for number, _, name in WAVE_CONTROLS:
            with self.subTest(parameter=name):
                parameter, control = self.parameters[name], self.controls[number]
                parameter.value = ECO_WAVE_VALUES[0]
                parameter.writes.clear()
                for expected in ECO_WAVE_VALUES[1:]:
                    self.assert_two_input_step(control, parameter, 65, expected)
                self.assert_two_input_step(control, parameter, 65, 1.0)
                for expected in reversed(ECO_WAVE_VALUES[:-1]):
                    self.assert_two_input_step(control, parameter, 63, expected)
                self.assert_two_input_step(control, parameter, 63, 0.0)
                self.assertEqual(len(parameter.writes), 6)
                self.assertEqual(control.native_updates, [])

    def test_eco_acceleration_counts_once_and_reversal_restarts_pending_input(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        for number, _, name in WAVE_CONTROLS:
            with self.subTest(parameter=name):
                parameter, control = self.parameters[name], self.controls[number]
                parameter.value = 0.0
                parameter.writes.clear()
                self.assert_two_input_step(control, parameter, 127, 1.0 / 3.0)
                self.assert_two_input_step(control, parameter, 127, 2.0 / 3.0)
                self.assert_two_input_step(control, parameter, 0, 1.0 / 3.0)
                writes = len(parameter.writes)
                for midi in (65, 63, 65, 64):
                    control.receive(midi)
                    self.assertAlmostEqual(parameter.value, 1.0 / 3.0)
                    self.assertEqual(len(parameter.writes), writes)
                control.receive(127)
                self.assertAlmostEqual(parameter.value, 2.0 / 3.0)
                self.assertEqual(len(parameter.writes), writes + 1)
                self.assertEqual(control.native_updates, [])

    def test_model_and_shift_changes_reset_pending_eco_inputs(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        for boundary in ("model", "shift"):
            with self.subTest(boundary=boundary):
                for number, _, name in WAVE_CONTROLS:
                    self.parameters[name].value = 0.0
                    self.parameters[name].writes.clear()
                    self.controls[number].receive(65)
                if boundary == "model":
                    self.model.value = 0.0
                    self.component._update_assignments()
                    self.assert_wave_targets(False)
                    self.model.value = 0.75
                    self.component._update_assignments()
                else:
                    self.component.set_shift_pressed(True)
                    for control in self.controls.values():
                        control.receive(65)
                        control.receive(127)
                    self.component.set_shift_pressed(False)
                self.assert_wave_targets(True)
                for number, normal, alternate in WAVE_CONTROLS:
                    parameter, control = self.parameters[alternate], self.controls[number]
                    self.assertEqual(parameter.writes, [])
                    self.assert_two_input_step(control, parameter, 65, 1.0 / 3.0)
                    self.assertEqual(control.native_updates, [])
                    self.assertEqual(self.parameters[normal].writes, [])

    def test_replacing_device_resets_pending_eco_inputs(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        for control in self.controls.values():
            control.receive(65)
        replacement, parameters, _ = model_device(value=0.75)
        for _, _, name in WAVE_CONTROLS:
            parameters[name].value = 0.0
            parameters[name].writes.clear()
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()
        self.assert_wave_targets(True, parameters)
        for number, _, name in WAVE_CONTROLS:
            self.assert_two_input_step(self.controls[number], parameters[name], 65, 1.0 / 3.0)
            self.assertEqual(self.parameters[name].writes, [])
            self.assertEqual(self.controls[number].native_updates, [])

    def test_shift_model_changes_update_preview_and_led_source_without_native_writes(self):
        self.bind(2, 6)
        self.component.set_shift_pressed(True)
        for eco in (True, False, True):
            self.model.value = 0.75 if eco else 0.0
            self.component._update_assignments()
            for number, normal, alternate in WAVE_CONTROLS:
                target = self.parameters[alternate if eco else normal]
                control = self.controls[number]
                self.assertIsNone(control.mapped_parameter)
                self.assertIs(control.manual_led_parameter, target)
                self.assertEqual(display_lines(self.displays[number])[1], target.name)
                control.receive(65)
                self.assertEqual(control.native_updates, [])
        self.component.set_shift_pressed(False)
        self.assert_wave_targets(True)
        for parameter in self.parameters.values():
            if isinstance(parameter, WaveParameter):
                self.assertEqual(parameter.writes, [])

    def test_selected_track_and_replaced_device_get_independent_model_state(self):
        self.bind(2, 6)
        replacement, parameters, model = model_device(value=0.75)
        track = fixtures.FakeTrack(
            "Replacement", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        )
        self.song.view.selected_track = track
        self.component._update_assignments()
        self.assert_wave_targets(True, parameters)
        self.model.value = 0.25
        self.component._update_assignments()
        self.assert_wave_targets(True, parameters)

        next_device, next_parameters, next_model = model_device(value=0.0)
        track.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), next_device)
        self.component._update_assignments()
        self.assert_wave_targets(False, next_parameters)
        next_model.value = 0.75
        self.component._update_assignments()
        self.assert_wave_targets(True, next_parameters)

    def test_missing_model_retains_the_shared_feedback_control(self):
        self.install_device(*model_device(include_model=False))
        self.bind(*range(1, 17))
        self.component._update_assignments()
        self.assert_upper_targets(None)

    def test_retarget_to_device_without_model_does_not_keep_previous_override(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        self.assert_wave_targets(True)
        replacement, parameters, _ = model_device(include_model=False)
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()
        self.assert_wave_targets(False, parameters, triple=False)

    def test_selector_occurrence_uses_first_model_when_names_repeat(self):
        second = ModelParameter("Model", value=0.75, parent=self.device)
        parameters = tuple(self.device.parameters) + (second,)
        self.device.parameters = fixtures.CountingParameterSequence(self.device, parameters)
        self.bind(2, 6)
        self.assert_wave_targets(False)
        self.model.value = 0.75
        second.value = 0.0
        self.component._update_assignments()
        self.assert_wave_targets(True)
        self.assertEqual(second.value_reads, 0)

    def test_missing_override_target_leaves_only_that_control_unassigned(self):
        self.install_device(*model_device(value=0.75, missing=("EcoWave1",)))
        self.bind(2, 6)
        self.assert_wave_targets(True)
        self.assertIsNone(self.component._connected_parameters.get("encoder_2"))
        self.controls[2].receive(65)
        self.assertEqual(self.controls[2].native_updates, [])
        self.model.value = 0.0
        self.component._update_assignments()
        self.assert_wave_targets(False)

    def test_same_tune_assignments_keep_pending_inputs_across_models(self):
        self.bind(1, 5)
        for normalized in (0.25, 0.75, 1.0):
            with self.subTest(model=normalized):
                self.model.value = 0.0
                self.component._update_assignments()
                for number, name in TUNE_CONTROLS:
                    self.parameters[name].value = 0.5
                    self.controls[number].receive(65)
                    self.assertEqual(self.parameters[name].value, 0.5)
                self.model.value = normalized
                self.component._update_assignments()
                for number, name in TUNE_CONTROLS:
                    self.assertIsNone(self.controls[number].mapped_parameter)
                    self.assertIs(self.controls[number].manual_led_parameter, self.parameters[name])
                    self.controls[number].receive(65)
                    self.assertAlmostEqual(self.parameters[name].value, 0.7, places=6)
                    self.assertEqual(self.controls[number].native_updates, [])

    def test_dco_unassigns_tune2_and_resets_pending_inputs(self):
        self.bind(5)
        control = self.controls[5]
        tune = self.parameters["Tune2"]
        control.receive(65)
        self.model.value = 0.5
        self.component._update_assignments()
        self.assertIsNone(control.mapped_parameter)
        self.assertIsNone(control.manual_led_parameter)
        control.receive(65)
        self.assertEqual(tune.value, 0.5)
        self.model.value = 0.0
        self.component._update_assignments()
        self.assertIs(control.manual_led_parameter, tune)
        control.receive(65)
        self.assertEqual(tune.value, 0.5)
        control.receive(65)
        self.assertAlmostEqual(tune.value, 0.7, places=6)
        self.assertEqual(control.native_updates, [])

    def test_unknown_model_unassigns_tunes_and_resets_pending_inputs(self):
        self.bind(1, 5)
        for number, _ in TUNE_CONTROLS:
            self.controls[number].receive(65)
        self.model.value = 0.625
        self.component._update_assignments()
        for number, name in TUNE_CONTROLS:
            self.assertIsNone(self.controls[number].mapped_parameter)
            self.assertIsNone(self.controls[number].manual_led_parameter)
            self.controls[number].receive(65)
            self.assertEqual(self.parameters[name].value, 0.5)
        self.model.value = 0.0
        self.component._update_assignments()
        for number, name in TUNE_CONTROLS:
            self.controls[number].receive(65)
            self.assertEqual(self.parameters[name].value, 0.5)
            self.controls[number].receive(65)
            self.assertAlmostEqual(self.parameters[name].value, 0.7, places=6)
            self.assertEqual(self.controls[number].native_updates, [])

    def test_override_can_retarget_another_occurrence_with_the_same_name_and_range(self):
        first = self.parameters["Shape1"]
        second = WaveParameter("Shape1", value=0.4, parent=self.device)
        self.device.parameters = fixtures.CountingParameterSequence(
            self.device, tuple(self.device.parameters) + (second,)
        )
        with override_rules({"encoder_2": {"Shape1": {"occurrence": 2}}}):
            self.bind(2)
            control = self.controls[2]
            self.assertIs(control.mapped_parameter, first)
            self.model.value = 0.75
            self.component._update_assignments()
            self.assertIs(control.mapped_parameter, second)
            self.assertEqual((first.writes, second.writes), ([], []))
            control.receive(65)
            self.assertEqual(first.writes, [])
            self.assertEqual(len(second.writes), 1)
            self.assertAlmostEqual(second.value, 0.4 + 1.0 / 127.0)
            self.model.value = 0.0
            self.component._update_assignments()
            self.assertIs(control.mapped_parameter, first)

    def test_override_can_change_same_parameter_between_native_and_manual_mapping(self):
        target = self.parameters["Shape1"]
        target.value = 0.5
        target.writes.clear()
        with override_rules({"encoder_2": {"Shape1": {"invert_direction": True, "discrete_count": 5}}}):
            self.bind(2)
            control = self.controls[2]
            self.assertIs(control.mapped_parameter, target)
            self.model.value = 0.75
            self.component._update_assignments()
            self.assertIsNone(control.mapped_parameter)
            self.assertIs(control.manual_led_parameter, target)
            self.assertEqual(target.writes, [])
            control.receive(65)
            self.assertEqual(target.value, 0.5)
            control.receive(65)
            self.assertEqual(target.value, 0.25)
            self.assertEqual(target.writes, [0.25])
            self.assertEqual(control.native_updates, [])

            # An unfinished manual step must not survive a mapping-mode change.
            control.receive(65)
            self.model.value = 0.0
            self.component._update_assignments()
            self.assertIs(control.mapped_parameter, target)
            self.assertIsNone(control.manual_led_parameter)
            self.model.value = 0.75
            self.component._update_assignments()
            control.receive(65)
            self.assertEqual(target.value, 0.25)
            self.model.value = 0.0
            self.component._update_assignments()
            control.receive(65)
            self.assertAlmostEqual(target.value, 0.25 + 1.0 / 127.0)
            self.assertEqual(len(control.native_updates), 1)

    def test_multiple_matching_rules_read_selector_once_and_last_assignment_wins(self):
        with override_rules({"encoder_2": "EcoWave1"}, {"encoder_2": "EcoWave2"}):
            self.bind(2, 5)
            reads = self.model.value_reads
            self.model.value = 0.75
            self.component._update_assignments()
            self.assertEqual(self.model.value_reads - reads, 1)
            self.assertIs(self.controls[2].mapped_parameter, self.parameters["EcoWave2"])
            self.assertIs(self.controls[5].mapped_parameter, self.parameters["Shape2"])
            reads = self.model.value_reads
            self.component._update_assignments()
            self.assertEqual(self.model.value_reads - reads, 1)

    def test_repeated_updates_read_model_once_without_reenumeration_or_reconnection(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 6)
        parameter_reads = self.device.parameter_read_count
        model_reads = self.model.value_reads
        connections = {number: len(control.connected) for number, control in self.controls.items()}
        releases = {number: control.release_count for number, control in self.controls.items()}
        for _ in range(12):
            self.component._update_assignments()
        self.assertEqual(self.device.parameter_read_count, parameter_reads)
        self.assertEqual(self.model.value_reads - model_reads, 12)
        self.assertEqual(self.model.display_calls, 0)
        self.assertEqual(self.model.value_items_reads, 0)
        for number, control in self.controls.items():
            self.assertEqual(len(control.connected), connections[number])
            self.assertEqual(control.release_count, releases[number])
        self.component.set_active(False)
        model_reads = self.model.value_reads
        self.component._update_assignments()
        self.assertEqual(self.model.value_reads, model_reads)

    def test_model_normalizes_its_actual_minimum_and_maximum(self):
        for minimum, maximum, eco_value, other_value in ((0.0, 4.0, 3.0, 2.0), (-2.0, 2.0, 1.0, 0.0)):
            with self.subTest(bounds=(minimum, maximum)):
                self.install_device(*model_device(value=eco_value, minimum=minimum, maximum=maximum))
                self.bind(*range(1, 17))
                self.assert_upper_targets(0.75)
                self.model.value = other_value
                self.component._update_assignments()
                self.assert_upper_targets(0.5)

    def test_invalid_model_range_retains_the_shared_feedback_control(self):
        self.install_device(*model_device(value=0.75, minimum=1.0, maximum=1.0))
        self.bind(*range(1, 17))
        self.component._update_assignments()
        self.assert_upper_targets(None)


if __name__ == "__main__":
    unittest.main()
