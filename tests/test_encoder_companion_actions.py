"""Encoder turns update only the configured primary and companion parameters."""

import unittest
from contextlib import contextmanager
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
    device.parameters = fixtures.CountingParameterSequence(
        device, (model, fixtures.FakeParameter("Feedback", parent=device)) + depths + sources
    )
    return device, model, depths, sources


class DepthControlFixture:
    def install_depth_control(self, number):
        self.device, self.model, self.depths, self.sources = depth_device()
        self.track = fixtures.FakeTrack(
            "Diva", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), self.device)
        )
        self.component = ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.component.song = fixtures.FakeSong((self.track,), selected_track=self.track)
        self.control = NativeMappedControl()
        self.display = fixtures.FakeDisplayCommand()
        getattr(self.component, "set_encoder_{}_display".format(number))(self.display)
        getattr(self.component, "set_encoder_{}".format(number))(self.control)
        self.component.set_active(True)


class EncoderCompanionActionsTest(DepthControlFixture, unittest.TestCase):
    """Keep the single-action dictionary API independent of Diva's current layout."""

    def setUp(self):
        base = (None,) * 7 + ({"DepthMod Dpt1": {
            "occurrence": 1,
            "invert_direction": True,
            "on_left": {
                "parameter": "DepthMod Src1", "occurrence": 1, "normalized_value": 0.0,
            },
        }},)
        for attribute, value in (
            ("CUSTOM_DEVICE_PARAMETER_ORDER_INDEX", {"diva": base}),
            ("CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {}),
        ):
            replacement = patch.object(ASSIGNMENTS, attribute, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        self.install_depth_control(8)

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

    def test_fixed_assignment_ignores_unrelated_model_values(self):
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


class DivaDualDepthActionsTest(DepthControlFixture, unittest.TestCase):
    """Exercise the production Encoder 23 assignment and both Configure pairs."""

    def setUp(self):
        self.install_depth_control(23)

    @contextmanager
    def configured_options(self, **updates):
        base = list(ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX["diva"])
        options = dict(base[22]["DepthMod Dpt1"])
        options.update(updates)
        base[22] = {"DepthMod Dpt1": options}
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_ORDER_INDEX", {"diva": tuple(base)}):
            self.component.set_active(False)
            self.component.set_active(True)
            yield

    def test_left_turn_inverts_each_depth_from_its_current_value_and_clears_both_sources(self):
        self.depths[1].value = 0.2
        self.depths[1].writes.clear()
        self.assertIsNone(self.control.mapped_parameter)
        self.assertIs(self.control.manual_led_parameter, self.depths[0])
        self.control.receive(63)
        self.assertAlmostEqual(self.depths[0].value, 0.5 + 1.0 / 127)
        self.assertAlmostEqual(self.depths[1].value, 0.2 + 1.0 / 127)
        for depth, source in zip(self.depths, self.sources):
            self.assertEqual(len(depth.writes), 1)
            self.assertEqual(source.writes, [0.0])
        self.assertEqual(self.control.native_updates, [])
        self.assertEqual(display_lines(self.display)[1], "DepthMod Dpt1")

    def test_right_turn_uses_each_depth_range_and_preserves_both_sources(self):
        self.depths[1].min, self.depths[1].max = -10.0, 20.0
        self.depths[1].value = 5.0
        self.depths[1].writes.clear()
        self.control.receive(67)
        self.assertAlmostEqual(self.depths[0].value, 0.5 - 3.0 / 127)
        self.assertAlmostEqual(self.depths[1].value, 5.0 - 90.0 / 127)
        for source in self.sources:
            self.assertEqual(source.writes, [])
        self.assertEqual(self.control.native_updates, [])

    def test_depth_endpoints_are_independent_and_still_clear_both_sources(self):
        for endpoint_index in (0, 1):
            for midi, endpoint, direction in ((63, 1.0, 1), (65, 0.0, -1)):
                with self.subTest(endpoint_index=endpoint_index, midi=midi):
                    for index, depth in enumerate(self.depths):
                        depth.value = endpoint if index == endpoint_index else 0.5
                        depth.writes.clear()
                    for source in self.sources:
                        source.value = 0.8
                        source.writes.clear()
                    self.control.receive(midi)
                    self.assertEqual(self.depths[endpoint_index].writes, [])
                    self.assertAlmostEqual(self.depths[1 - endpoint_index].value, 0.5 + direction / 127)
                    for source in self.sources:
                        self.assertEqual(source.writes, [0.0] if midi < 64 else [])

    def test_source_writes_are_not_repeated_and_latest_external_changes_are_cleared(self):
        for midi in (63, 63, 0, 63):
            self.control.receive(midi)
        for source in self.sources:
            self.assertEqual(source.writes, [0.0])
        self.sources[1].value = 0.4
        self.control.receive(63)
        self.assertEqual(self.sources[0].writes, [0.0])
        self.assertEqual(self.sources[1].writes, [0.0, 0.4, 0.0])

    def test_refresh_shift_inactive_and_no_movement_do_not_write_any_target(self):
        for _ in range(3):
            self.component._update_assignments(force=True)
        self.control.receive(64)
        self.component.set_shift_pressed(True)
        for midi in (63, 65, 0):
            self.control.receive(midi)
        self.component.preview_encoder("encoder_23")
        self.component.set_shift_pressed(False)
        self.component.set_active(False)
        self.control.receive(63)
        for parameter in self.depths + self.sources:
            self.assertEqual(parameter.writes, [])
        self.assertEqual(self.control.native_updates, [])

    def test_missing_or_disabled_secondary_depth_does_not_block_other_targets(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                device, model, depths, sources = depth_device()
                if missing:
                    depths[1].name = "Other DepthMod Dpt1"
                else:
                    depths[1].is_enabled = False
                self.track.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                self.component._update_assignments()
                self.control.receive(63)
                self.assertAlmostEqual(depths[0].value, 0.5 + 1.0 / 127)
                self.assertEqual(depths[1].writes, [])
                for source in sources:
                    self.assertEqual(source.writes, [0.0])

    def test_missing_or_disabled_source_does_not_block_the_other_source_or_depths(self):
        for missing, index in ((False, 0), (False, 1), (True, 1)):
            with self.subTest(missing=missing, index=index):
                device, model, depths, sources = depth_device()
                if missing:
                    sources[index].name = "Other DepthMod Src1"
                else:
                    sources[index].is_enabled = False
                self.track.devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                self.component._update_assignments()
                self.control.receive(63)
                for depth in depths:
                    self.assertAlmostEqual(depth.value, 0.5 + 1.0 / 127)
                self.assertEqual(sources[index].writes, [])
                self.assertEqual(sources[1 - index].writes, [0.0])

    def test_primary_missing_or_disabled_blocks_all_companion_writes(self):
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
                for parameter in depths + sources:
                    self.assertEqual(parameter.writes, [])

    def test_encoder_23_is_shared_and_encoder_8_controls_only_feedback(self):
        previous_control = NativeMappedControl()
        self.component.set_encoder_8(previous_control)
        for normalized in (0.0, 0.25, 0.5, 0.75, 1.0, 0.125):
            with self.subTest(model=normalized):
                self.model.value = normalized
                for source in self.sources:
                    source.value = 0.8
                for parameter in self.depths + self.sources:
                    parameter.writes.clear()
                self.component._update_assignments()
                previous_control.receive(63)
                previous_control.receive(65)
                for parameter in self.depths + self.sources:
                    self.assertEqual(parameter.writes, [])
                self.assertEqual(previous_control.mapped_parameter.name, "Feedback")
                self.assertIsNone(previous_control.manual_led_parameter)
                self.control.receive(63)
                self.assertIs(self.control.manual_led_parameter, self.depths[0])
                for depth, source in zip(self.depths, self.sources):
                    self.assertEqual(len(depth.writes), 1)
                    self.assertEqual(source.writes, [0.0])

    def test_track_and_device_changes_before_refresh_use_only_the_new_pairs(self):
        for replace_track in (False, True):
            with self.subTest(replace_track=replace_track):
                old_parameters = self.depths + self.sources
                device, model, depths, sources = depth_device()
                devices = (fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
                if replace_track:
                    self.track = fixtures.FakeTrack("Replacement", devices=devices)
                    self.component.song.view.selected_track = self.track
                else:
                    self.track.devices = devices
                old_writes = tuple(tuple(parameter.writes) for parameter in old_parameters)
                self.control.receive(63)
                self.assertEqual(tuple(tuple(parameter.writes) for parameter in old_parameters), old_writes)
                for depth, source in zip(depths, sources):
                    self.assertAlmostEqual(depth.value, 0.5 + 1.0 / 127)
                    self.assertEqual(source.writes, [0.0])
                self.assertIs(self.control.manual_led_parameter, depths[0])
                self.depths, self.sources = depths, sources

    def test_model_change_rebinds_all_targets_before_the_next_periodic_refresh(self):
        rules = ({"when": {"parameter": "Model", "normalized_value": 1.0},
                  "assignments": {"encoder_23": {"DepthMod Dpt1": {
                      "occurrence": 2, "invert_direction": True,
                      "relative_targets": ({"parameter": "DepthMod Dpt1", "occurrence": 1,
                                            "invert_direction": False},),
                      "on_left": (
                          {"parameter": "DepthMod Src1", "occurrence": 1, "normalized_value": 0.25},
                          {"parameter": "DepthMod Src1", "occurrence": 2, "normalized_value": 0.75},
                      ),
                  }}}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
            self.component.set_active(False)
            self.component.set_active(True)
            self.model.value = 1.0
            self.control.receive(63)
            self.assertAlmostEqual(self.depths[0].value, 0.5 - 1.0 / 127)
            self.assertAlmostEqual(self.depths[1].value, 0.5 + 1.0 / 127)
            self.assertEqual(self.sources[0].writes, [0.25])
            self.assertEqual(self.sources[1].writes, [0.75])
            self.assertIs(self.control.manual_led_parameter, self.depths[1])

    def test_override_can_remove_the_whole_compound_assignment_without_stale_writes(self):
        rules = ({"when": {"parameter": "Model", "normalized_value": 1.0},
                  "assignments": {"encoder_23": None}},)
        with patch.object(ASSIGNMENTS, "CUSTOM_DEVICE_PARAMETER_OVERRIDES_INDEX", {"diva": rules}):
            self.component.set_active(False)
            self.component.set_active(True)
            self.model.value = 1.0
            self.control.receive(63)
            for parameter in self.depths + self.sources:
                self.assertEqual(parameter.writes, [])
            self.assertIsNone(self.control.manual_led_parameter)

    def test_duplicate_relative_targets_never_apply_a_delta_twice(self):
        targets = tuple({"parameter": "DepthMod Dpt1", "occurrence": occurrence,
                         "invert_direction": True} for occurrence in (1, 2, 2))
        with self.configured_options(relative_targets=targets):
            self.control.receive(63)
            for depth in self.depths:
                self.assertAlmostEqual(depth.value, 0.5 + 1.0 / 127)
                self.assertEqual(len(depth.writes), 1)

    def test_relative_targets_do_not_inherit_primary_discrete_steps_or_input_count(self):
        for discrete in ({"discrete_values": (0.0, 0.5, 1.0)}, {"discrete_count": 3}):
            with self.subTest(discrete=discrete):
                for depth in self.depths:
                    depth.value = 0.5
                    depth.writes.clear()
                with self.configured_options(**discrete):
                    self.control.receive(63)
                    self.assertEqual(self.depths[0].writes, [])
                    self.assertAlmostEqual(self.depths[1].value, 0.5 + 1.0 / 127)
                    self.control.receive(63)
                    self.assertEqual(self.depths[0].writes, [1.0])
                    self.assertAlmostEqual(self.depths[1].value, 0.5 + 2.0 / 127)

    def test_relative_target_alone_releases_native_mapping_without_inverting_primary(self):
        with self.configured_options(invert_direction=False, on_left=None):
            self.control.receive(63)
            self.assertIsNone(self.control.mapped_parameter)
            self.assertAlmostEqual(self.depths[0].value, 0.5 - 1.0 / 127)
            self.assertAlmostEqual(self.depths[1].value, 0.5 + 1.0 / 127)
            self.assertEqual(self.control.native_updates, [])
            for source in self.sources:
                self.assertEqual(source.writes, [])

    def test_action_lists_are_supported_as_well_as_tuples(self):
        options = ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX["diva"][22]["DepthMod Dpt1"]
        with self.configured_options(on_left=list(options["on_left"]),
                                     relative_targets=list(options["relative_targets"])):
            self.control.receive(63)
            for depth, source in zip(self.depths, self.sources):
                self.assertAlmostEqual(depth.value, 0.5 + 1.0 / 127)
                self.assertEqual(source.writes, [0.0])

    def test_refresh_and_turns_do_not_reenumerate_parameters_or_repeat_source_writes(self):
        reads = self.device.parameter_read_count
        for _ in range(20):
            self.component._update_assignments()
            self.control.receive(63)
        self.assertEqual(self.device.parameter_read_count, reads)
        for source in self.sources:
            self.assertEqual(source.writes, [0.0])


if __name__ == "__main__":
    unittest.main()
