"""Diva OSC model changes retarget only the two waveform controls."""

import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_diva_controls import diva_device
from test_shift_preview import NativeMappedControl, display_lines


INSTRUMENT_ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS
WAVE_CONTROLS = ((2, "Shape1", "EcoWave1"), (5, "Shape2", "EcoWave2"))


def override_rules(*assignments):
    rules = tuple(
        {
            "when": {"parameter": "Model", "occurrence": 1, "normalized_value": 0.75},
            "assignments": entries,
        }
        for entries in assignments
    )
    return patch.object(INSTRUMENT_ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules})


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
    parameters = [parameter for parameter in device.parameters if parameter.name not in missing]
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
    return device, {parameter.name: parameter for parameter in parameters}, model


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

    def assert_wave_targets(self, eco, parameters=None):
        parameters = self.parameters if parameters is None else parameters
        for number, normal, alternate in WAVE_CONTROLS:
            expected = parameters.get(alternate if eco else normal)
            self.assertIs(self.controls[number].mapped_parameter, expected)
            self.assertIsNone(self.controls[number].manual_led_parameter)
            if expected is not None:
                self.assertEqual(display_lines(self.displays[number])[1], expected.name)

    def test_initial_eco_model_uses_eco_waves_without_changing_values(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 5)
        self.assert_wave_targets(True)
        for parameter in self.parameters.values():
            if isinstance(parameter, WaveParameter):
                self.assertEqual(parameter.writes, [])

    def test_all_other_models_switch_to_eco_and_back_without_writing_parameters(self):
        self.bind(2, 5)
        for normalized in (0.0, 0.25, 0.5, 1.0):
            with self.subTest(model=normalized):
                self.model.value = normalized
                self.component._update_assignments()
                self.assert_wave_targets(False)
                self.model.value = 0.75
                self.component._update_assignments()
                self.assert_wave_targets(True)
                self.model.value = normalized
                self.component._update_assignments()
                self.assert_wave_targets(False)
        for parameter in self.parameters.values():
            if isinstance(parameter, WaveParameter):
                self.assertEqual(parameter.writes, [])

    def test_encoder_input_writes_only_the_current_native_target_once(self):
        self.bind(2, 5)
        for eco in (False, True, False):
            self.model.value = 0.75 if eco else 0.0
            self.component._update_assignments()
            for number, normal, alternate in WAVE_CONTROLS:
                target = self.parameters[alternate if eco else normal]
                previous = target.value
                writes = {name: len(self.parameters[name].writes) for name in (normal, alternate)}
                control = self.controls[number]
                native_count = len(control.native_updates)
                control.receive(65)
                self.assertAlmostEqual(target.value, previous + 1.0 / 127.0)
                self.assertEqual(len(control.native_updates), native_count + 1)
                for name in (normal, alternate):
                    self.assertEqual(len(self.parameters[name].writes), writes[name] + (name == target.name))

    def test_shift_model_changes_update_preview_and_led_source_without_native_writes(self):
        self.bind(2, 5)
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
        self.bind(2, 5)
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

    def test_missing_model_keeps_base_assignment(self):
        self.install_device(*model_device(include_model=False))
        self.bind(2, 5)
        self.component._update_assignments()
        self.assert_wave_targets(False)

    def test_retarget_to_device_without_model_does_not_keep_previous_override(self):
        self.install_device(*model_device(value=0.75))
        self.bind(2, 5)
        self.assert_wave_targets(True)
        replacement, parameters, _ = model_device(include_model=False)
        self.selected.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), replacement)
        self.component._update_assignments()
        self.assert_wave_targets(False, parameters)

    def test_selector_occurrence_uses_first_model_when_names_repeat(self):
        second = ModelParameter("Model", value=0.75, parent=self.device)
        parameters = tuple(self.device.parameters) + (second,)
        self.device.parameters = fixtures.CountingParameterSequence(self.device, parameters)
        self.bind(2, 5)
        self.assert_wave_targets(False)
        self.model.value = 0.75
        second.value = 0.0
        self.component._update_assignments()
        self.assert_wave_targets(True)
        self.assertEqual(second.value_reads, 0)

    def test_missing_override_target_leaves_only_that_control_unassigned(self):
        self.install_device(*model_device(value=0.75, missing=("EcoWave1",)))
        self.bind(2, 5)
        self.assert_wave_targets(True)
        self.assertIsNone(self.component._connected_parameters.get("encoder_2"))
        self.controls[2].receive(65)
        self.assertEqual(self.controls[2].native_updates, [])
        self.model.value = 0.0
        self.component._update_assignments()
        self.assert_wave_targets(False)

    def test_model_change_preserves_pending_tune_inputs(self):
        self.bind(1, 2, 4, 5)
        for number in (1, 4):
            self.controls[number].receive(65)
        self.model.value = 0.75
        self.component._update_assignments()
        self.assert_wave_targets(True)
        for number, name in ((1, "Tune1"), (4, "Tune2")):
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
        self.bind(2, 5)
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
                self.bind(2, 5)
                self.assert_wave_targets(True)
                self.model.value = other_value
                self.component._update_assignments()
                self.assert_wave_targets(False)

    def test_invalid_model_range_keeps_base_assignment(self):
        self.install_device(*model_device(value=0.75, minimum=1.0, maximum=1.0))
        self.bind(2, 5)
        self.component._update_assignments()
        self.assert_wave_targets(False)


if __name__ == "__main__":
    unittest.main()
