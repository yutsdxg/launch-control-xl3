"""Keyboard navigation must never leak into Live's native parameter map."""

import ast
import types
import unittest

import test_mixing as fixtures
from test_shift_preview import NativeMappedControl, display_lines

from Launch_Control_XL_3_Mixing.keyboard_navigation import EncoderKeyboardNavigation


def surface_class():
    """Exercise surface wiring without loading Ableton's concrete elements."""
    source = ast.parse((fixtures.PACKAGE_ROOT / "__init__.py").read_text())
    surface = next(node for node in source.body if isinstance(node, ast.ClassDef)
                   and node.name == "Launch_Control_XL_3_Mixing")

    class BaseSurface:
        def _send_midi(self, message):
            self.sent_midi.append(message)

        def port_settings_changed(self):
            self.port_changes += 1

        def on_identified(self, response):
            pass

    namespace = {
        "ControlSurface": BaseSurface,
        "MODE_MIXING": "mixing",
        "MODE_INSTRUMENT": "instrument",
        "task": fixtures.sys.modules["ableton.v3.base"].task,
        "midi": types.SimpleNamespace(
            make_connection_message=lambda connect=True: (240, int(connect), 247),
            SET_RELATIVE_ENCODER_MODES=((182, 69, 127), (182, 72, 127), (182, 73, 127)),
        ),
    }
    exec(compile(ast.Module(body=[surface], type_ignores=[]), "surface_lifecycle", "exec"), namespace)
    return namespace["Launch_Control_XL_3_Mixing"]


class FakeKeyboardSender:
    def __init__(self):
        self.foreground = True
        self.success = True
        self.presses = []
        self.focus_epoch = 0
        self.starts = 0
        self.polls = 0
        self.cancels = 0
        self.closed = False

    def start(self):
        self.starts += 1
        return self.success

    def cancel(self):
        self.cancels += 1

    def close(self):
        self.closed = True

    def poll(self):
        self.polls += 1

    def is_frontmost(self):
        self.poll()
        return self.foreground and not self.closed

    def press(self, direction, at=None):
        if not self.success:
            return False
        self.presses.append(direction)
        return True


class InstrumentKeyboardNavigationTest(unittest.TestCase):
    def setUp(self):
        fixtures.InstrumentAssignmentsTest.setUp(self)
        self.sender = FakeKeyboardSender()
        self.now = 0.0
        self.component._keyboard_navigation = EncoderKeyboardNavigation(
            sender=self.sender, clock=lambda: self.now, inputs_per_press=3
        )
        self.control = NativeMappedControl(identifier=100)
        self.display = fixtures.FakeDisplayCommand()
        self.component.set_encoder_24_display(self.display)
        self.component.set_encoder_24(self.control)

    def tearDown(self):
        self.component.disconnect()

    def activate(self):
        self.component.set_active(True)

    def test_construction_does_not_start_worker_and_surface_starts_once(self):
        self.assertEqual(self.sender.starts, 0)
        surface_type = surface_class()
        surface = surface_type.__new__(surface_type)
        surface.component_map = {"Instrument_Assignments": self.component}
        surface.sent_midi = []
        surface.port_changes = 0
        surface._tasks = self.component._tasks
        surface._setup_components()
        self.assertEqual(self.sender.starts, 1)
        for mode in ("instrument", "mixing", "instrument"):
            surface._on_mode_changed(mode)
        surface.on_identified(())
        surface.port_settings_changed()
        self.assertEqual(self.sender.starts, 1)
        self.assertEqual(surface.port_changes, 1)
        self.assertFalse(any(len(message) == 3 and message[1] in (118, 119)
                             for message in surface.sent_midi))
        self.assertEqual(self.sender.presses, [])

    def test_inactive_component_polls_worker_without_changing_mixing_control(self):
        self.control.connect_to(self.selected.mixer_device.panning)
        before = self.control.release_count
        polls = self.sender.polls
        self.component._update_assignments()
        self.component._update_assignments()
        self.assertEqual(self.sender.polls, polls + 2)
        self.assertEqual(self.control.release_count, before)
        self.assertIs(self.control.mapped_parameter, self.selected.mixer_device.panning)
        self.assertEqual(self.sender.presses, [])

    def test_port_change_cancels_navigation_and_blanks_display(self):
        self.activate()
        self.control.receive(65)
        surface_type = surface_class()
        surface = surface_type.__new__(surface_type)
        surface.component_map = {"Instrument_Assignments": self.component}
        surface.sent_midi = []
        surface.port_changes = 0
        before = self.sender.cancels
        surface.port_settings_changed()
        self.assertEqual(self.sender.cancels, before + 1)
        self.assertEqual(display_lines(self.display)[2], "")
        self.control.receive(65)
        self.assertEqual(self.sender.presses, [1, 1])

    def test_reserves_encoder_and_prepares_display_and_blue_led(self):
        self.activate()
        self.assertIsNone(self.control.mapped_parameter)
        self.assertEqual(self.control.connected, [])
        self.assertEqual(self.control.manual_led_rgb, ("mode", True, "blue"))
        self.assertEqual(display_lines(self.display), ("Keyboard", "Preset Up-Down", ""))
        self.assertFalse(self.display.sent[-1][3])
        self.assertIsNone(self.component._parameter_for_control("encoder_24"))

    def test_turns_send_keys_without_changing_instrument_parameter(self):
        self.activate()
        parameter = self.target_device.parameters[24]
        parameter.value = 0.5
        self.control.receive(63)
        self.assertEqual(display_lines(self.display)[2], "Up")
        self.control.receive(127)
        self.assertEqual(display_lines(self.display)[2], "Down")
        self.assertEqual(self.sender.presses, [-1, 1])
        self.assertTrue(self.display.sent[-1][3])
        self.assertEqual(parameter.value, 0.5)
        self.assertEqual(self.control.native_updates, [])

    def test_shift_and_touch_preview_never_send_keys_and_reset_gesture(self):
        self.activate()
        self.control.receive(65)
        self.control.receive(65)
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        router.set_target_components(instrument_assignments=self.component)
        shift, touch = fixtures.FakeButton(63), fixtures.FakeButton(100)
        router.set_shift_button(shift)
        router.set_encoder_24_touch(touch)
        shift.receive(127)
        for value in (127, 63, 65):
            self.control.receive(value)
            touch.receive(127)
        self.assertEqual(self.sender.presses, [1])
        self.assertEqual(display_lines(self.display), ("Keyboard", "Preset Up-Down", ""))
        self.assertTrue(self.display.sent[-1][3])
        self.assertEqual(self.control.native_updates, [])
        shift.receive(0)
        self.control.receive(65)
        self.assertEqual(self.sender.presses, [1, 1])

    def test_idle_and_background_poll_clear_display_without_repeating(self):
        self.activate()
        self.control.receive(65)
        self.now = 0.25
        self.component._update_assignments()
        self.assertEqual(display_lines(self.display)[2], "")
        self.assertEqual(self.sender.presses, [1])
        self.control.receive(65)
        self.sender.foreground = False
        self.component._update_assignments()
        self.control.receive(63)
        self.assertEqual(display_lines(self.display)[2], "")
        self.assertEqual(self.sender.presses, [1, 1])
        self.sender.foreground = True
        self.control.receive(65)
        self.assertEqual(self.sender.presses, [1, 1, 1])

    def test_keyboard_navigation_is_independent_of_target_device(self):
        self.song.view.selected_track = fixtures.FakeTrack("Empty")
        self.activate()
        self.control.receive(63)
        self.assertEqual(self.sender.presses, [-1])
        self.assertEqual(display_lines(self.display)[2], "Up")

    def test_target_track_change_does_not_reconnect_reserved_encoder(self):
        self.activate()
        release_count = self.control.release_count
        for track in (fixtures.FakeTrack("Empty"), self.selected):
            self.song.view.selected_track = track
            self.component._update_assignments()
            self.control.receive(63)
        self.assertEqual(self.control.connected, [])
        self.assertEqual(self.control.release_count, release_count)
        self.assertEqual(self.control.native_updates, [])

    def test_inactive_assignment_and_disconnect_preserve_mixing_pan(self):
        self.control.connect_to(self.selected.mixer_device.panning)
        before = self.control.release_count
        self.component.set_encoder_24(self.control)
        self.component.disconnect()
        self.assertTrue(self.sender.closed)
        self.assertIs(self.control.mapped_parameter, self.selected.mixer_device.panning)
        self.assertEqual(self.control.release_count, before)
        self.assertEqual(self.sender.presses, [])

    def test_mode_switch_restores_pan_and_clears_navigation_led(self):
        fixed = fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent()
        fixed.song = self.song
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        router.set_target_components(fixed_assignments=fixed, instrument_assignments=self.component)
        router.set_encoder_24(self.control)
        fixed.set_active(True)
        self.assertIs(self.control.mapped_parameter, self.selected.mixer_device.panning)
        fixed.set_active(False)
        self.activate()
        self.assertIsNone(self.control.mapped_parameter)
        self.control.receive(65)
        self.component.set_active(False)
        fixed.set_active(True)
        self.assertIsNone(self.control.manual_led_rgb)
        self.assertIs(self.control.mapped_parameter, self.selected.mixer_device.panning)
        self.control.receive(65)
        self.assertEqual(self.sender.presses, [1])
        self.component.disconnect()
        self.assertIs(self.control.mapped_parameter, self.selected.mixer_device.panning)
        fixed.set_active(False)
        self.activate()
        self.control.receive(65)
        # Disconnect removed the listener, so there cannot be a deferred key.
        self.assertEqual(self.sender.presses, [1])

    def test_replacing_control_releases_old_led_and_resets_gesture(self):
        self.activate()
        self.control.receive(65)
        self.control.receive(65)
        replacement = NativeMappedControl(identifier=100)
        self.component.set_encoder_24(replacement)
        self.control.receive(65)
        self.assertIsNone(self.control.manual_led_rgb)
        self.assertEqual(self.control.listeners, [])
        replacement.receive(65)
        self.assertEqual(self.sender.presses, [1, 1])
        self.assertIsNone(replacement.mapped_parameter)

    def test_failure_isolated_from_other_instrument_controls(self):
        other = NativeMappedControl(identifier=77)
        self.component.set_encoder_1(other)
        self.activate()
        self.sender.success = False
        self.control.receive(65)
        other.receive(65)
        self.assertEqual(self.sender.presses, [])
        self.assertGreater(self.target_device.parameters[1].value, 0)
        self.assertEqual(self.target_device.parameters[24].value, 0)

    def test_failed_press_immediately_clears_previous_action_display(self):
        self.activate()
        self.control.receive(65)
        self.sender.success = False
        self.control.receive(63)
        self.assertEqual(self.sender.presses, [1])
        self.assertEqual(display_lines(self.display)[2], "")
        self.assertFalse(self.display.sent[-1][3])

    def test_sender_start_failure_does_not_disable_other_controls(self):
        self.sender.success = False
        self.assertFalse(self.component.start_keyboard_navigation())
        other = NativeMappedControl(identifier=77)
        self.component.set_encoder_1(other)
        self.activate()
        other.receive(65)
        self.assertGreater(self.target_device.parameters[1].value, 0)


if __name__ == "__main__":
    unittest.main()
