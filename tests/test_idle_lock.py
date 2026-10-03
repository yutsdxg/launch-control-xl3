"""Exercise the inactivity lock through the actual surface/component wiring."""

import importlib.util
import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_encoder_companion_actions import depth_device
from test_initial_assignment_display import HardwareDisplay
from test_instrument_keyboard_navigation import FakeKeyboardSender, surface_class
from test_mixing_colored_encoder import COLORED, FakeParameter as SaturnParameter
from test_shift_preview import NativeMappedControl, display_lines

from Launch_Control_XL_3_Mixing.keyboard_navigation import EncoderKeyboardNavigation
from Launch_Control_XL_3_Mixing.safety import LOCKED_MODE_RGB


class LockControl(NativeMappedControl):
    def set_locked(self, locked):
        self.locked = locked

    def set_shift_pressed(self, pressed):
        self.shift_pressed = pressed


class IdleLockTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.selected = self.track("Selected")
        self.other = self.track("Other")
        self.song = fixtures.FakeSong((self.selected, self.other))
        self.fixed = fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent()
        self.instrument = fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        self.tracks = fixtures.TRACK_BUTTONS.TrackButtonsComponent()
        for component in (self.fixed, self.instrument, self.tracks):
            component.song = self.song
        self.sender = FakeKeyboardSender()
        self.instrument._keyboard_navigation = EncoderKeyboardNavigation(
            sender=self.sender, clock=lambda: self.now, inputs_per_press=3)
        self.router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        self.manager = fixtures.MODE_MANAGER.ModeManagerComponent(clock=lambda: self.now)
        self.pages = {mode: fixtures.FakeButton(identifier) for mode, identifier in
                      (("mixing", 106), ("instrument", 107))}
        self.manager.set_mixing_button(self.pages["mixing"])
        self.manager.set_instrument_button(self.pages["instrument"])
        self.static, self.temp = HardwareDisplay(), HardwareDisplay()
        self.manager.set_static_display(self.static)
        self.manager.set_temp_display(self.temp)
        self.shift = fixtures.FakeButton(63)
        self.router.set_shift_button(self.shift)
        self.solo, self.mute = fixtures.FakeButton(65), fixtures.FakeButton(66)
        self.tracks.set_solo_modifier_button(self.solo)
        self.tracks.set_mute_modifier_button(self.mute)
        surface_type = surface_class()
        self.surface = surface_type.__new__(surface_type)
        self.surface.component_map = {
            "Control_Router": self.router, "Mode_Manager": self.manager,
            "Fixed_Assignments": self.fixed, "Instrument_Assignments": self.instrument,
            "Track_Buttons": self.tracks,
        }
        self.surface.sent_midi = []
        self.surface._tasks = self.fixed._tasks
        self.surface._setup_components()
        self.controls, self.displays, self.touches = {}, {}, {}
        for kind, count in (("encoder", 24), ("fader", 8)):
            for number in range(1, count + 1):
                name = "{}_{}".format(kind, number)
                control = LockControl(relative=kind == "encoder")
                display = HardwareDisplay()
                getattr(self.router, "set_{}".format(name))(control)
                getattr(self.router, "set_{}_display".format(name))(display)
                self.controls[name], self.displays[name] = control, display
                if kind == "encoder":
                    touch = fixtures.FakeButton()
                    getattr(self.router, "set_{}_touch".format(name))(touch)
                    self.touches[name] = touch
        self.buttons = [fixtures.FakeButton(37 + i) for i in range(16)]
        for i, button in enumerate(self.buttons, 1):
            getattr(self.router, "set_track_button_{}".format(i))(button)

    def tearDown(self):
        for component in (self.router, self.fixed, self.instrument, self.tracks, self.manager):
            component.disconnect()

    def track(self, name):
        return fixtures.FakeTrack(name, is_foldable=True, devices=tuple(
            fixtures.FakeInstrumentDevice("Device {}".format(i)) for i in range(1, 10)))

    def lock(self):
        self.now += 180.0
        self.manager.check_idle()
        self.assertTrue(self.manager.locked)

    def snapshot(self):
        return [(p, p.value) for track in self.song.tracks for device in track.devices
                for p in device.parameters] + [
                    (self.selected.mixer_device.volume, self.selected.mixer_device.volume.value),
                    (self.selected.mixer_device.panning, self.selected.mixer_device.panning.value),
                ]

    def test_timer_activity_filters_and_internal_updates(self):
        self.assertEqual(display_lines(self.static), ("MIXING", "", ""))
        self.now = 100
        for value in (64, -1, 128):
            self.controls["encoder_11"].receive(value)
        self.buttons[0].receive(0)
        self.assertEqual(self.manager._last_activity, 0)
        self.controls["encoder_11"].receive(65)
        self.assertEqual(self.manager._last_activity, 100)
        self.now = 110
        self.controls["fader_8"].receive(0)  # Zero is a valid absolute value.
        self.assertEqual(self.manager._last_activity, 110)
        self.now = 120
        self.buttons[0].receive(127)
        self.assertEqual(self.manager._last_activity, 120)
        self.now = 299.99
        self.selected.devices[3].parameters[3].value = 0.8
        self.fixed._update_assignments()
        self.tracks.refresh_led_feedback()
        self.surface.on_identified(())
        self.manager.check_idle()
        self.assertFalse(self.manager.locked)
        self.assertEqual(self.manager._last_activity, 120)
        self.now = 300
        self.manager.check_idle()
        self.assertTrue(self.manager.locked)
        self.now = 400
        self.controls["fader_8"].receive(127)
        self.assertEqual(self.manager._last_activity, 120)
        self.pages["mixing"].receive(0)
        self.assertTrue(self.manager.locked)

    def test_all_inputs_and_hardware_stored_text_are_protected_in_both_modes(self):
        for mode in ("mixing", "instrument"):
            with self.subTest(mode=mode):
                self.pages[mode].receive(127)
                before = self.snapshot()
                submode = self.fixed._loopcloud_metric_submode
                track_states = [(t, t.solo, t.mute) for t in self.song.tracks]
                self.lock()
                for name, control in self.controls.items():
                    self.assertTrue(control.locked)
                    self.assertIsNone(control.mapped_parameter)
                    self.assertEqual(self.displays[name].local_shift_turn(), ("LOCKED", "", ""))
                    for value in ((65, 63) if name.startswith("encoder_") else (127, 0)):
                        control.receive(value)
                        self.assertTrue(all(p.value == original for p, original in before))
                        self.assertEqual(self.fixed._loopcloud_metric_submode, submode)
                    self.assertIsNone(control.mapped_parameter)
                for button in self.buttons:
                    button.receive(127)
                    button.receive(0)
                self.solo.receive(127)
                self.mute.receive(127)
                self.assertEqual(self.tracks._button_mode, "select")
                self.shift.receive(127)
                for name, touch in self.touches.items():
                    touch.receive(127)
                    touch.receive(0)
                    self.assertEqual(self.displays[name].local_shift_turn(), ("LOCKED", "", ""))
                self.shift.receive(0)
                for component in (self.fixed, self.instrument):
                    component._update_assignments(force=True)
                    component.refresh_display_feedback()
                self.surface.on_identified(())
                self.assertEqual(display_lines(self.static), ("LOCKED", "", ""))
                self.assertTrue(all(p.value == value for p, value in before))
                self.assertTrue(all((t.solo, t.mute) == (solo, mute) for t, solo, mute in track_states))
                self.assertIs(self.song.view.selected_track, self.selected)
                self.assertEqual(self.sender.presses, [])
                self.assertEqual(self.manager.selected_mode, mode)
                for page in self.pages.values():
                    self.assertEqual(self.manager._led_sender.last[page], LOCKED_MODE_RGB)

    def test_unlock_by_same_or_other_mode_restores_mapping_and_does_not_replay(self):
        for initial, requested in (("mixing", "mixing"), ("instrument", "instrument"),
                                   ("mixing", "instrument"), ("instrument", "mixing")):
            with self.subTest(initial=initial, requested=requested):
                self.pages[initial].receive(127)
                self.lock()
                self.controls["encoder_24"].receive(65)
                self.controls["fader_8"].receive(127)
                before = self.snapshot()
                self.pages[requested].receive(127)
                self.assertFalse(self.manager.locked)
                self.assertEqual(display_lines(self.static), (requested.upper(), "", ""))
                self.assertEqual(self.temp.sent[-1][0], 0)  # Remove LOCKED overlay.
                self.assertTrue(all(p.value == value for p, value in before))
                self.assertIsNotNone(self.controls["fader_8"].mapped_parameter)
                self.assertNotEqual(self.displays["fader_8"].local_shift_turn()[0], "LOCKED")
                self.assertEqual(self.sender.presses, [])
        self.pages["instrument"].receive(127)
        self.controls["encoder_24"].receive(65)
        self.assertEqual(self.sender.presses, [1])
        self.lock()
        self.controls["encoder_24"].receive(65)
        self.instrument._update_assignments()
        self.pages["instrument"].receive(127)
        self.assertEqual(self.sender.presses, [1])
        self.controls["encoder_24"].receive(63)
        self.assertEqual(self.sender.presses, [1, -1])

    def test_reassignment_and_shift_release_never_reconnect_a_locked_control(self):
        self.pages["instrument"].receive(127)
        self.lock()
        self.song.view.selected_track = self.other
        self.shift.receive(127)
        self.shift.receive(0)
        self.instrument._update_assignments(force=True)
        self.assertIsNone(self.controls["fader_8"].mapped_parameter)
        self.shift.receive(127)
        self.pages["instrument"].receive(127)
        self.assertIsNone(self.controls["fader_8"].mapped_parameter)
        self.shift.receive(0)
        self.assertIs(self.controls["fader_8"].mapped_parameter, self.other.devices[2].parameters[32])

    def test_manual_primary_and_companion_actions_do_not_write_or_accumulate(self):
        device, _, depths, sources = depth_device()
        self.selected.devices = self.selected.devices[:2] + (device,) + self.selected.devices[3:]
        self.pages["instrument"].receive(127)
        self.assertIs(self.instrument._connected_parameters["encoder_22"], depths[0])
        self.lock()
        for value in (63, 65, 127, 0, 63):
            self.controls["encoder_22"].receive(value)
            self.instrument._update_assignments()
        self.pages["instrument"].receive(127)
        for parameter in depths + sources:
            self.assertEqual(parameter.writes, [])
        self.controls["encoder_22"].receive(63)
        for parameter in depths + sources:
            self.assertEqual(len(parameter.writes), 1)

    def test_selected_track_stops_blinking_and_led_refresh_stays_locked(self):
        self.tracks._selected_blink_is_on = lambda: False
        self.tracks.refresh_led_feedback()
        self.assertEqual(self.tracks._led_sender.last[self.buttons[0]], "off")
        self.lock()
        for _ in range(3):
            self.tracks._update_led_feedback()
            self.manager.refresh_led_feedback()
            self.assertEqual(self.tracks._led_sender.last[self.buttons[0]],
                             ("locked", ("active", self.selected.rgb)))
            self.assertEqual(self.manager._led_sender.last[self.pages["mixing"]], LOCKED_MODE_RGB)
            self.assertEqual(self.manager._led_sender.last[self.pages["instrument"]], LOCKED_MODE_RGB)

    def test_delayed_old_feedback_cannot_overwrite_lock_but_transport_still_sends(self):
        header = (240, 0, 32, 41, 2, 21)
        old_generation = self.surface._feedback_generation
        delayed = []
        self.surface._do_send_midi = delayed.append
        self.lock()
        stale_feedback = (
            header + (6, 13, 0, 77, 247), header + (4, 53, 127, 247),
            header + (1, 83, 106, 25, 25, 0, 247),
        )
        for message in stale_feedback:
            self.surface._send_deferred_feedback(message, old_generation)
        self.assertEqual(delayed, [])
        for message in ((182, 69, 127), header + (1, 83, 116, 0, 30, 0, 247)):
            self.surface._send_deferred_feedback(message, old_generation)
        self.assertEqual(len(delayed), 2)
        current = header + (1, 83, 106) + LOCKED_MODE_RGB + (247,)
        self.surface._send_deferred_feedback(current, self.surface._feedback_generation)
        self.assertEqual(delayed[-1], current)


class LockFeedbackTest(unittest.TestCase):
    def test_numeric_led_dimming_survives_updates_and_restores_latest_color(self):
        spec = importlib.util.spec_from_file_location(
            "Launch_Control_XL_3_Mixing.lock_test_led", fixtures.PACKAGE_ROOT / "led.py")
        led = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(led)
        sent = []
        button = fixtures.FakeButton(37)
        with patch.object(led.midi, "make_rgb_led_message", lambda index, rgb: (index, rgb)):
            sender = led.LedSender(sent.append)
            sender.send_rgb(button, (25, 5, 0))
            sender.set_locked(True)
            sender.send_rgb(button, (25, 5, 0))
            self.assertEqual(sent[-1], (37, (1, 0, 0)))
            sender.send_rgb(button, (0, 0, 0))
            self.assertEqual(sent[-1], (37, (0, 0, 0)))
            sender.send_rgb(button, (50, 25, 10))
            self.assertEqual(sent[-1], (37, (2, 1, 0)))
            sender.set_locked(False)
            sender.send_rgb(button, (50, 25, 10))
            self.assertEqual(sent[-1], (37, (50, 25, 10)))

    def test_element_special_handler_is_guarded_and_led_source_remains_dimmed(self):
        encoder = COLORED.ColoredEncoderElement()
        parameter = SaturnParameter(value=2.0)
        activities = []
        encoder.set_on_activity(activities.append)
        with patch.object(COLORED, "encoder_rgb_for_parameter", return_value=(25, 5, 0)):
            encoder.mapped_object = parameter
            encoder.set_locked(True)
            encoder.receive_value(65)
            encoder.notify_value(63)
            self.assertEqual(parameter.value, 2.0)
            self.assertEqual(activities, [])
            self.assertEqual(encoder.sent_midi[-1][2], (1, 0, 0))
            encoder._parameter_value_changed()
            self.assertEqual(encoder.sent_midi[-1][2], (1, 0, 0))
            encoder.set_locked(False)
            self.assertEqual(encoder.sent_midi[-1][2], (25, 5, 0))
            encoder.receive_value(65)
            self.assertEqual(parameter.value, 6.0)
            self.assertEqual(activities, [65])

    def test_custom_timeout_and_activity_listener_cleanup(self):
        now = [0.0]
        manager = fixtures.MODE_MANAGER.ModeManagerComponent(clock=lambda: now[0], idle_timeout=5)
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        router.set_on_activity(manager.record_activity)
        old, new = fixtures.FakeControl(), fixtures.FakeControl()
        router.set_encoder_11(old)
        router.set_encoder_11(new)
        now[0] = 4
        old.receive(65)
        self.assertEqual(manager._last_activity, 0)
        new.receive(65)
        now[0] = 8.99
        manager.check_idle()
        self.assertFalse(manager.locked)
        now[0] = 9
        manager.check_idle()
        self.assertTrue(manager.locked)
        router.disconnect()
        self.assertEqual(new.listeners, [])


if __name__ == "__main__":
    unittest.main()
