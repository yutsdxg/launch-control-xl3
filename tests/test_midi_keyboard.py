import unittest

import test_mixing as fixtures

from Launch_Control_XL_3_Mixing.keyboard_navigation import EncoderKeyboardNavigation
from Launch_Control_XL_3_Mixing.midi_keyboard import MidiKeyboardSender
from test_shift_preview import NativeMappedControl, display_lines


class MidiKeyboardSenderTest(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.sender = MidiKeyboardSender(self.messages.append)

    def test_unknown_focus_suppresses_navigation_but_allows_query(self):
        self.assertFalse(self.sender.is_frontmost())
        self.assertFalse(self.sender.press(-1))
        self.assertTrue(self.sender.request_focus())
        self.assertEqual(self.messages, [(0xBF, 119, 0)])

    def test_up_down_and_same_direction_repetitions_are_distinct_ccs(self):
        self.sender.set_focus(1)
        for direction in (-1, -1, 1, 1):
            self.assertTrue(self.sender.press(direction))
        self.assertEqual(self.messages, [
            (0xBF, 119, 1), (0xBF, 119, 1), (0xBF, 119, 2), (0xBF, 119, 2)
        ])

    def test_background_and_invalid_directions_do_not_send(self):
        self.sender.set_focus(1)
        for direction in (0, None, 2):
            self.assertFalse(self.sender.press(direction))
        self.sender.set_focus(0)
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.messages, [])

    def test_invalid_focus_values_do_not_enable_sender(self):
        for value in (127, 64, -1, None, "1"):
            self.assertFalse(self.sender.set_focus(value))
            self.assertFalse(self.sender.is_frontmost())

    def test_port_change_and_query_invalidate_old_foreground_state(self):
        self.sender.set_focus(1)
        self.sender.set_midi_sender(self.messages.append)
        self.assertFalse(self.sender.press(1))
        self.sender.set_focus(1)
        self.sender.request_focus()
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.messages, [(0xBF, 119, 0)])

    def test_missing_or_failed_midi_output_stops_navigation(self):
        sender = MidiKeyboardSender()
        sender.set_focus(1)
        self.assertFalse(sender.press(1))
        self.sender.set_midi_sender(lambda message: False)
        self.sender.set_focus(1)
        with self.assertLogs("Launch_Control_XL_3_Mixing.midi_keyboard", level="WARNING") as log:
            self.assertFalse(self.sender.press(1))
            self.sender.set_focus(1)
            self.assertFalse(self.sender.press(1))
        self.assertEqual(len(log.output), 1)
        self.assertFalse(self.sender.is_frontmost())

    def test_output_exception_is_contained(self):
        def fail(message):
            raise RuntimeError("Port disconnected")
        self.sender.set_midi_sender(fail)
        self.sender.set_focus(1)
        with self.assertLogs("Launch_Control_XL_3_Mixing.midi_keyboard", level="WARNING"):
            self.assertFalse(self.sender.press(-1))
        self.assertFalse(self.sender.is_frontmost())


class BomeInstrumentNavigationTest(unittest.TestCase):
    def setUp(self):
        fixtures.InstrumentAssignmentsTest.setUp(self)
        self.messages = []
        self.now = 0.0
        self.component._keyboard_navigation = EncoderKeyboardNavigation(
            clock=lambda: self.now, inputs_per_press=3, min_press_interval=1.0
        )
        self.component.set_keyboard_midi_sender(self.messages.append)
        self.focus = fixtures.FakeButton(118)
        self.component.set_keyboard_focus_button(self.focus)
        self.control = NativeMappedControl(identifier=100)
        self.display = fixtures.FakeDisplayCommand()
        self.component.set_encoder_24_display(self.display)
        self.component.set_encoder_24(self.control)
        self.component.set_active(True)

    def test_focus_feedback_resets_gesture_even_without_an_assignment_poll(self):
        self.control.receive(65)
        self.assertEqual(self.messages, [])
        self.focus.receive(1)
        self.control.receive(65)
        self.control.receive(65)
        self.focus.receive(0)
        self.assertEqual(display_lines(self.display)[2], "")
        self.control.receive(65)
        self.focus.receive(1)
        self.control.receive(65)
        self.assertEqual(self.messages, [(0xBF, 119, 2), (0xBF, 119, 2)])

    def test_query_requires_new_focus_response(self):
        self.focus.receive(1)
        self.assertTrue(self.component.request_keyboard_focus())
        self.control.receive(65)
        self.focus.receive(1)
        self.control.receive(63)
        self.assertEqual(self.messages, [(0xBF, 119, 0), (0xBF, 119, 1)])

    def test_shift_and_mode_changes_leave_next_input_immediate(self):
        self.focus.receive(1)
        self.control.receive(65)
        self.control.receive(65)
        self.component.set_shift_pressed(True)
        self.control.receive(63)
        self.component.preview_encoder("encoder_24")
        self.component.set_shift_pressed(False)
        self.control.receive(65)
        self.component.set_active(False)
        self.control.receive(63)
        self.component.set_active(True)
        self.control.receive(65)
        self.assertEqual(self.messages, [(0xBF, 119, 2)] * 3)

    def test_focus_listener_is_replaced_and_disconnected(self):
        replacement = fixtures.FakeButton(118)
        self.component.set_keyboard_focus_button(replacement)
        self.assertEqual(self.focus.listeners, [])
        self.assertEqual(len(replacement.listeners), 1)
        self.component.disconnect()
        self.assertEqual(replacement.listeners, [])


if __name__ == "__main__":
    unittest.main()
