"""Encoder turns update only the configured primary and companion parameters."""

import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines


ASSIGNMENTS = fixtures.INSTRUMENT_ASSIGNMENTS


class TrackedParameter(fixtures.FakeParameter):
    def __init__(self, *args, **kwargs):
        self.writes = []
        super().__init__(*args, **kwargs)
        self.writes.clear()

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.writes.append(value)

    def str_for_value(self, value):
        raise AssertionError("Companion actions must never probe display values")


def depth_device():
    device = fixtures.FakeInstrumentDevice("Diva")
    model = fixtures.FakeParameter("Model", parent=device)
    depths = tuple(TrackedParameter("DepthMod Dpt1", value=0.5, parent=device) for _ in range(2))
    sources = tuple(TrackedParameter("DepthMod Src1", value=0.8, parent=device) for _ in range(2))
    device.parameter_read_count = 0
    device.parameters = fixtures.CountingParameterSequence(device, (model,) + depths + sources)
    return device, model, depths, sources


class EncoderCompanionActionsTest(unittest.TestCase):
    def setUp(self):
        self.device, self.model, self.depths, self.sources = depth_device()
        self.track = fixtures.FakeTrack(
            "Diva", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), self.device)
        )
        self.component = ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.component.song = fixtures.FakeSong((self.track,), selected_track=self.track)
        self.control = NativeMappedControl()
        self.display = fixtures.FakeDisplayCommand()
        self.component.set_encoder_8_display(self.display)
        self.component.set_encoder_8(self.control)
        self.component.set_active(True)

    def test_left_turn_inverts_depth_and_sets_only_first_source_to_none(self):
        self.assertIsNone(self.control.mapped_parameter)
        self.assertIs(self.control.manual_led_parameter, self.depths[0])
        self.control.receive(63)
        self.assertAlmostEqual(self.depths[0].value, 0.5 + 1.0 / 127)
        self.assertEqual(self.sources[0].writes, [0.0])
        self.assertEqual(self.depths[1].writes, [])
        self.assertEqual(self.sources[1].writes, [])
        self.assertEqual(self.control.native_updates, [])
        self.assertEqual(display_lines(self.display)[1], "DepthMod Dpt1")

    def test_right_turn_inverts_depth_without_changing_source(self):
        self.control.receive(65)
        self.assertAlmostEqual(self.depths[0].value, 0.5 - 1.0 / 127)
        self.assertEqual(self.sources[0].writes, [])
        self.assertEqual(self.sources[1].writes, [])
        self.assertEqual(self.control.native_updates, [])

    def test_depth_endpoint_still_clears_source_but_does_not_repeat_writes(self):
        self.depths[0].value = 1.0
        self.depths[0].writes.clear()
        for midi in (63, 63, 0, 63):
            self.control.receive(midi)
        self.assertEqual(self.depths[0].writes, [])
        self.assertEqual(self.sources[0].writes, [0.0])
        # A subsequent external/automation change is cleared on the next left turn.
        self.sources[0].value = 0.4
        self.control.receive(63)
        self.assertEqual(self.sources[0].writes, [0.0, 0.4, 0.0])

    def test_assignment_refresh_no_input_shift_and_inactive_mode_do_not_write(self):
        for _ in range(3):
            self.component._update_assignments(force=True)
        self.control.receive(64)
        self.component.set_shift_pressed(True)
        for midi in (63, 65, 0):
            self.control.receive(midi)
        self.component.preview_encoder("encoder_8")
        self.component.set_shift_pressed(False)
        self.component.set_active(False)
        self.control.receive(63)
        for parameter in self.depths + self.sources:
            self.assertEqual(parameter.writes, [])
        self.assertEqual(self.control.native_updates, [])

    def test_source_absent_or_disabled_does_not_prevent_primary_control(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                device, model, depths, sources = depth_device()
                if missing:
                    # Partial-name matches must not be used as companions.
                    for source in sources:
                        source.name = "Other DepthMod Src1"
                else:
                    sources[0].is_enabled = False
                self.track.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                self.component._update_assignments()
                self.control.receive(63)
                self.assertGreater(depths[0].value, 0.5)
                self.assertEqual(sources[0].writes, [])
                self.assertEqual(sources[1].writes, [])

    def test_primary_absent_or_disabled_does_not_clear_source(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                device, model, depths, sources = depth_device()
                if missing:
                    device.parameters = (model,) + sources
                else:
                    depths[0].is_enabled = False
                self.track.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                self.component._update_assignments()
                self.control.receive(63)
                self.assertEqual(sources[0].writes, [])
                self.assertEqual(sources[1].writes, [])

    def test_all_oscillator_models_share_encoder_eight(self):
        for model in (0.0, 0.25, 0.5, 0.75, 1.0, 0.125):
            with self.subTest(model=model):
                self.model.value = model
                self.sources[0].value = 0.8
                self.sources[0].writes.clear()
                self.component._update_assignments()
                self.assertEqual(self.sources[0].writes, [])
                self.control.receive(63)
                self.assertIs(self.control.manual_led_parameter, self.depths[0])
                self.assertEqual(self.sources[0].writes, [0.0])

    def test_track_and_device_changes_before_periodic_refresh_use_only_new_pair(self):
        for replace_track in (False, True):
            with self.subTest(replace_track=replace_track):
                old_depths, old_sources = self.depths, self.sources
                device, model, depths, sources = depth_device()
                devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                if replace_track:
                    self.track = fixtures.FakeTrack("Replacement", devices=devices)
                    self.component.song.view.selected_track = self.track
                else:
                    self.track.devices = devices
                old_values = tuple(parameter.value for parameter in old_depths + old_sources)
                # No _update_assignments call before this physical turn.
                self.control.receive(63)
                self.assertEqual(tuple(parameter.value for parameter in old_depths + old_sources), old_values)
                self.assertGreater(depths[0].value, 0.5)
                self.assertEqual(sources[0].writes, [0.0])
                self.assertEqual(sources[1].writes, [])
                self.assertIs(self.control.manual_led_parameter, depths[0])
                self.depths, self.sources = depths, sources

    def test_normalized_companion_values_scale_to_live_parameter_range(self):
        self.sources[0].min = 10.0
        self.sources[0].max = 33.0
        self.sources[0].value = 25.0
        self.sources[0].writes.clear()
        self.control.receive(63)
        self.control.receive(63)
        self.assertEqual(self.sources[0].writes, [10.0])

    def test_model_override_changes_pair_together_before_periodic_refresh(self):
        action = {"parameter": "DepthMod Src1", "occurrence": 2, "normalized_value": 0.25}
        rules = ({"when": {"parameter": "Model", "normalized_value": 1.0},
                  "assignments": {"encoder_8": {"DepthMod Dpt1": {
                      "occurrence": 2, "invert_direction": True, "on_left": action}}}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
            self.component.set_active(False)
            self.component.set_active(True)
            self.model.value = 1.0
            self.control.receive(63)
            self.assertEqual(self.depths[0].writes, [])
            self.assertEqual(self.sources[0].writes, [])
            self.assertGreater(self.depths[1].value, 0.5)
            self.assertEqual(self.sources[1].writes, [0.25])

    def test_override_can_remove_assignment_without_stale_companion_writes(self):
        rules = ({"when": {"parameter": "Model", "normalized_value": 1.0},
                  "assignments": {"encoder_8": None}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
            self.component.set_active(False)
            self.component.set_active(True)
            self.model.value = 1.0
            self.control.receive(63)
            for parameter in self.depths + self.sources:
                self.assertEqual(parameter.writes, [])
            self.assertIsNone(self.control.manual_led_parameter)

    def test_model_can_add_companion_to_manual_control_before_periodic_refresh(self):
        base = (None,) * 7 + ({"DepthMod Dpt1": {"invert_direction": True}},)
        rules = ({"when": {"parameter": "Model", "normalized_value": 1.0},
                  "assignments": {"encoder_8": {"DepthMod Dpt1": {
                      "occurrence": 2, "invert_direction": True, "on_left": {
                          "parameter": "DepthMod Src1", "occurrence": 2,
                          "normalized_value": 0.0}}}}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_ORDER_INDEX", {"diva": base}):
            with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
                self.component.set_active(False)
                self.component.set_active(True)
                self.model.value = 1.0
                self.control.receive(63)
                self.assertEqual(self.depths[0].writes, [])
                self.assertEqual(self.sources[0].writes, [])
                self.assertGreater(self.depths[1].value, 0.5)
                self.assertEqual(self.sources[1].writes, [0.0])

    def test_left_action_without_inversion_still_releases_native_mapping(self):
        base = (None,) * 7 + ({"DepthMod Dpt1": {"on_left": {
            "parameter": "DepthMod Src1", "normalized_value": 0.0}}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_ORDER_INDEX", {"diva": base}):
            self.component.set_active(False)
            self.component.set_active(True)
            self.control.receive(63)
            self.assertAlmostEqual(self.depths[0].value, 0.5 - 1.0 / 127)
            self.assertEqual(self.sources[0].writes, [0.0])
            self.assertEqual(self.control.native_updates, [])

    def test_refresh_and_turns_do_not_enumerate_parameters_again(self):
        reads = self.device.parameter_read_count
        for _ in range(20):
            self.component._update_assignments()
            self.control.receive(63)
        self.assertEqual(self.device.parameter_read_count, reads)
        self.assertEqual(self.sources[0].writes, [0.0])


if __name__ == "__main__":
    unittest.main()
