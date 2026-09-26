"""Hardware can show a prepared assignment without sending a value or touch CC."""

import unittest

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl


class HardwareDisplay(fixtures.FakeDisplayCommand):
    """Keep per-control text locally, as the device does before a Shift turn."""

    def __init__(self):
        super().__init__()
        self.fields = None
        self.prepared_frames = []
        self.popup_count = 0
        self._cached_payload = None

    def clear_send_cache(self):
        self._cached_payload = None

    def send_data(self, config, text_fields, show_immediately, trigger):
        super().send_data(config, text_fields, show_immediately, trigger)
        payload = (config, text_fields, show_immediately)
        # DisplayTargetElement caches its prepared payload independently of
        # device memory. Explicit triggers resend fields even if unchanged.
        if payload != self._cached_payload or trigger:
            self.prepared_frames.append(payload)
            self.fields = tuple("".join(chr(value) for value in field) for field in text_fields)
            self._cached_payload = payload
        self.popup_count += bool(show_immediately or trigger)

    def local_shift_turn(self):
        # Deliberately no value listener or script-side preview callback.
        return self.fields


class InitialDisplayChecks:
    def bind(self, name=None, display_first=True):
        name = name or self.encoder_name
        control = NativeMappedControl(relative=name.startswith("encoder_"))
        display = HardwareDisplay()
        if display_first:
            getattr(self.component, "set_{}_display".format(name))(display)
        getattr(self.component, "set_{}".format(name))(control)
        self.component.set_active(True)
        if not display_first:
            getattr(self.component, "set_{}_display".format(name))(display)
        return control, display

    def assert_background_only(self, display):
        self.assertGreater(len(display.sent), 0)
        self.assertEqual(display.popup_count, 0)
        self.assertTrue(all(config == 98 and not immediate and not trigger
                            for config, _, immediate, trigger in display.sent))

    def test_first_shift_turn_has_assignment_without_any_input_cc(self):
        for display_first in (True, False):
            with self.subTest(display_first=display_first):
                self.component.set_shift_pressed(False)
                control, display = self.bind(display_first=display_first)
                parameter = control.mapped_parameter
                self.assertEqual(display.local_shift_turn(), (self.header, parameter.name, "0.0"))
                self.component.set_shift_pressed(True)

                self.assertEqual(display.local_shift_turn(), (self.header, parameter.name, "0.0"))
                self.assertEqual(parameter.value, 0.0)
                self.assertEqual(control.native_updates, [])
                self.assertIsNone(control.mapped_parameter)
                self.assert_background_only(display)
                self.component.set_shift_pressed(False)

    def test_missing_assignment_is_prepared_before_first_turn(self):
        self.song.view.selected_track = fixtures.FakeTrack("Empty")
        self.component.set_shift_pressed(True)
        control, display = self.bind()

        self.assertEqual(display.local_shift_turn(),
                         (self.encoder_name.replace("_", " ").title(), "Unassigned", ""))
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(control.native_updates, [])
        self.assert_background_only(display)

    def test_poll_refreshes_external_value_and_reassignment_without_popup(self):
        control, display = self.bind()
        original = control.mapped_parameter
        self.component.set_shift_pressed(True)
        original.value = 0.37
        self.component._update_assignments()
        self.assertEqual(display.local_shift_turn(), (self.header, original.name, "0.37"))

        replacement = self.replace_target()
        replacement.value = 0.75
        self.component._update_assignments()
        self.assertEqual(display.local_shift_turn(), ("Replacement", replacement.name, "0.75"))
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual((original.value, replacement.value), (0.37, 0.75))
        self.assertEqual(control.native_updates, [])
        self.assert_background_only(display)

    def test_unchanged_refresh_does_not_resend_prepared_text(self):
        control, display = self.bind()
        parameter = control.mapped_parameter
        parameter.name = "1234567890123456-A"
        self.component._update_assignments()
        count = len(display.prepared_frames)
        # These names have the same hardware-visible, 16-character payload.
        parameter.name = "1234567890123456-B"
        for _ in range(3):
            self.component._update_assignments()
            self.component._update_assignments(force=True)
        self.assertEqual(len(display.prepared_frames), count)
        self.assertEqual(display.local_shift_turn()[1], "1234567890123456")
        self.assert_background_only(display)

    def test_reidentification_restores_device_text_despite_existing_host_cache(self):
        control, display = self.bind()
        parameter = control.mapped_parameter
        count = len(display.prepared_frames)
        # Reconnection may erase the device text without clearing host caches.
        display.fields = None
        self.component._update_assignments()
        self.assertIsNone(display.local_shift_turn())
        self.assertEqual(len(display.prepared_frames), count)

        self.component.refresh_display_feedback()

        self.assertEqual(display.local_shift_turn(), (self.header, parameter.name, "0.0"))
        self.assertGreater(len(display.prepared_frames), count)
        self.assertEqual(control.native_updates, [])
        self.assertEqual(parameter.value, 0.0)
        self.assert_background_only(display)

    def test_explicit_value_and_touch_retrigger_even_when_text_is_unchanged(self):
        control, display = self.bind()
        parameter = control.mapped_parameter
        self.component.set_shift_pressed(True)
        for action in (lambda: control.receive(65),
                       lambda: self.component.preview_encoder(self.encoder_name)):
            for _ in range(2):
                popups = display.popup_count
                action()
                self.assertEqual(display.popup_count, popups + 1)
                self.assertTrue(display.sent[-1][3])
                self.assertEqual(display.local_shift_turn(), (self.header, parameter.name, "0.0"))
        self.assertEqual(parameter.value, 0.0)
        self.assertEqual(control.native_updates, [])


class FixedInitialDisplayTest(InitialDisplayChecks, unittest.TestCase):
    setUp = fixtures.FixedAssignmentsTest.setUp
    encoder_name = "encoder_11"
    header = "Device 4"

    def replace_target(self):
        track = fixtures.FakeTrack("Replacement", devices=tuple(fixtures.FakeDevice(i) for i in range(1, 10)))
        track.devices[3].name = "Replacement"
        self.song.view.selected_track = track
        return track.devices[3].parameters[3]

    def test_special_and_track_assignments_are_prepared_without_input(self):
        for name, expected in (
            ("encoder_1", ("Mode", "Loopcloud", "")),
            ("encoder_2", ("Device 1", "Device On", "1.0")),
            ("encoder_10", ("Encoder 10", "Unassigned", "")),
            ("encoder_16", ("Selected", "Selected Send 1", "0.0")),
        ):
            with self.subTest(control=name):
                control, display = self.bind(name)
                self.assertEqual(display.local_shift_turn(), expected)
                self.assertEqual(control.native_updates, [])
                self.assert_background_only(display)
        self.assertFalse(self.loopcloud.solo)
        self.assertEqual(self.selected.devices[0].parameters[0].value, 1.0)


class InstrumentInitialDisplayTest(InitialDisplayChecks, unittest.TestCase):
    setUp = fixtures.InstrumentAssignmentsTest.setUp
    encoder_name = "encoder_1"
    header = "Instrument"

    def replace_target(self):
        device = fixtures.FakeInstrumentDevice("Replacement")
        self.song.view.selected_track = fixtures.FakeTrack(
            "Replacement", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        )
        return device.parameters[1]


class SharedDisplayModeTest(unittest.TestCase):
    def test_mode_switch_refreshes_same_hardware_display_without_input_or_popup(self):
        track = fixtures.FakeTrack(
            "Selected", devices=tuple(fixtures.FakeInstrumentDevice("Device {}".format(i)) for i in range(9))
        )
        song = fixtures.FakeSong((track,))
        fixed = fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent()
        instrument = fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        fixed.song = instrument.song = song
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        control, display = NativeMappedControl(), HardwareDisplay()
        router.set_target_components(fixed, instrument)
        router.set_encoder_11(control)
        router.set_encoder_11_display(display)
        fixed_target = track.devices[3].parameters[3]
        instrument_target = track.devices[2].parameters[11]
        fixed_target.value, instrument_target.value = 0.3, 0.6
        fixed.set_shift_pressed(True)
        instrument.set_shift_pressed(True)

        for active, inactive, target in ((instrument, fixed, instrument_target),
                                         (fixed, instrument, fixed_target),
                                         (instrument, fixed, instrument_target)):
            inactive.set_active(False)
            active.set_active(True)
            fixed._update_assignments()
            instrument._update_assignments()
            self.assertEqual(display.local_shift_turn(),
                             (target.canonical_parent.name, target.name, str(target)))
            self.assertIsNone(control.mapped_parameter)
            self.assertEqual((fixed_target.value, instrument_target.value), (0.3, 0.6))
        self.assertEqual(display.popup_count, 0)
        self.assertEqual(control.native_updates, [])


if __name__ == "__main__":
    unittest.main()
