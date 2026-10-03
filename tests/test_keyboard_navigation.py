import importlib.util
import sys
import types
import unittest
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = WORKSPACE_ROOT / "Launch_Control_XL_3_Mixing"


def _load_navigation_module():
    package_name = "Launch_Control_XL_3_Mixing"
    package = sys.modules.get(package_name)
    if package is None:
        package = types.ModuleType(package_name)
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules[package_name] = package
    module_name = package_name + ".keyboard_navigation"
    spec = importlib.util.spec_from_file_location(
        module_name, PACKAGE_ROOT / "keyboard_navigation.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


NAVIGATION = _load_navigation_module()


class FakeClock(object):
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeSender(object):
    def __init__(self):
        self.frontmost = True
        self.succeeds = True
        self.presses = []
        self.focus_epoch = 0
        self.cancels = 0
        self.closed = False
        self.started = False
        self.input_times = []

    def start(self):
        self.started = True
        return True

    def cancel(self):
        self.cancels += 1

    def close(self):
        self.closed = True

    def is_frontmost(self):
        return self.frontmost

    def press(self, direction, at=None):
        self.presses.append(direction)
        self.input_times.append(at)
        return self.succeeds


class EncoderKeyboardNavigationTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.sender = FakeSender()

    def navigation(self, **settings):
        return NAVIGATION.EncoderKeyboardNavigation(
            sender=self.sender, clock=self.clock, **settings
        )

    def test_minimum_rotation_sends_up_and_down_and_updates_display(self):
        navigation = self.navigation()

        self.assertEqual(navigation.last_action, "")
        self.assertTrue(navigation.receive_value(63))
        self.assertEqual(navigation.last_action, "Up")
        self.assertTrue(navigation.receive_value(65))
        self.assertEqual(navigation.last_action, "Down")
        self.assertEqual(self.sender.presses, [-1, 1])

    def test_neutral_and_invalid_input_do_not_send_keys(self):
        navigation = self.navigation()

        for value in (64, -1, 128, None, "63", 63.5, True, False):
            with self.subTest(value=value):
                self.assertFalse(navigation.receive_value(value))

        self.assertEqual(self.sender.presses, [])
        self.assertEqual(navigation.last_action, "")

    def test_accelerated_values_send_one_key_per_message(self):
        navigation = self.navigation()

        self.assertTrue(navigation.receive_value(0))
        self.assertTrue(navigation.receive_value(1))
        self.assertTrue(navigation.receive_value(127))
        self.assertTrue(navigation.receive_value(126))

        self.assertEqual(self.sender.presses, [-1, -1, 1, 1])

    def test_default_continuous_rotation_sends_each_input_immediately(self):
        navigation = self.navigation()

        for _ in range(4):
            self.assertTrue(navigation.receive_value(65))

        self.assertEqual(self.sender.presses, [1, 1, 1, 1])

    def test_input_threshold_preserves_immediate_first_press(self):
        navigation = self.navigation(inputs_per_press=3)

        self.assertTrue(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(127))
        self.assertTrue(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        self.assertTrue(navigation.receive_value(65))

        self.assertEqual(self.sender.presses, [1, 1, 1])

    def test_minimum_interval_waits_for_a_new_input_without_replaying(self):
        navigation = self.navigation(min_press_interval=0.1)

        self.assertTrue(navigation.receive_value(65))
        self.clock.advance(0.05)
        self.assertFalse(navigation.receive_value(65))
        self.clock.advance(0.06)
        self.assertTrue(navigation.poll())
        self.assertEqual(self.sender.presses, [1])
        self.assertTrue(navigation.receive_value(65))
        self.assertEqual(self.sender.presses, [1, 1])

    def test_threshold_reached_before_interval_retries_on_next_input(self):
        navigation = self.navigation(inputs_per_press=2, min_press_interval=0.1)

        self.assertTrue(navigation.receive_value(65))
        self.clock.advance(0.02)
        self.assertFalse(navigation.receive_value(65))
        self.clock.advance(0.02)
        self.assertFalse(navigation.receive_value(65))
        self.clock.advance(0.07)
        self.assertTrue(navigation.receive_value(65))

        self.assertEqual(self.sender.presses, [1, 1])

    def test_direction_reversal_is_immediate_and_starts_fresh_threshold(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=0.1)

        self.assertTrue(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        self.clock.advance(0.01)
        self.assertTrue(navigation.receive_value(63))
        self.clock.advance(0.11)
        self.assertFalse(navigation.receive_value(63))
        self.assertFalse(navigation.receive_value(63))
        self.assertTrue(navigation.receive_value(63))

        self.assertEqual(self.sender.presses, [1, -1, -1])

    def test_poll_clears_idle_gesture_without_sending_additional_keys(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(65))
        self.clock.advance(0.25)
        self.assertTrue(navigation.poll())
        self.assertEqual(navigation.last_action, "")
        self.assertEqual(self.sender.presses, [1])
        self.assertTrue(navigation.receive_value(65))
        self.assertEqual(self.sender.presses, [1, 1])

    def test_idle_gap_restarts_gesture_without_a_poll(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(63))
        self.clock.advance(0.25)
        self.assertTrue(navigation.receive_value(63))

        self.assertEqual(self.sender.presses, [-1, -1])

    def test_reset_clears_direction_display_and_pending_inputs(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        navigation.reset()
        self.assertEqual(navigation.last_action, "")
        self.assertTrue(navigation.receive_value(65))

        self.assertEqual(self.sender.presses, [1, 1])

    def test_focus_loss_during_poll_resets_gesture_before_return_to_live(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(65))
        self.assertFalse(navigation.receive_value(65))
        self.sender.frontmost = False
        self.assertFalse(navigation.poll())
        self.assertEqual(navigation.last_action, "")
        self.sender.frontmost = True
        self.assertTrue(navigation.poll())
        self.assertTrue(navigation.receive_value(65))

        self.assertEqual(self.sender.presses, [1, 1])

    def test_input_while_another_app_is_frontmost_is_suppressed_and_resets(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(63))
        self.sender.frontmost = False
        self.assertFalse(navigation.receive_value(63))
        self.assertEqual(navigation.last_action, "")
        self.assertEqual(self.sender.presses, [-1])
        self.sender.frontmost = True
        self.assertTrue(navigation.receive_value(63))

        self.assertEqual(self.sender.presses, [-1, -1])

    def test_failed_sender_clears_gesture_and_allows_fresh_retry(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)

        self.assertTrue(navigation.receive_value(65))
        self.sender.succeeds = False
        self.assertFalse(navigation.receive_value(63))
        self.assertEqual(navigation.last_action, "")
        self.sender.succeeds = True
        self.assertTrue(navigation.receive_value(63))

        self.assertEqual(self.sender.presses, [1, -1, -1])

    def test_out_and_back_focus_epoch_clears_threshold_even_when_frontmost(self):
        navigation = self.navigation(inputs_per_press=3, min_press_interval=1.0)
        navigation.receive_value(65)
        navigation.receive_value(65)
        self.sender.focus_epoch += 2
        self.assertTrue(navigation.receive_value(65))
        self.assertEqual(self.sender.presses, [1, 1])
        self.assertEqual(self.sender.cancels, 1)

    def test_busy_drop_does_not_cancel_the_previous_inflight_press(self):
        navigation = self.navigation()
        navigation.receive_value(65)
        self.sender.succeeds = False
        self.assertFalse(navigation.receive_value(65))
        self.assertEqual(self.sender.cancels, 0)
        # A lifecycle reset still cancels the outstanding request.
        navigation.reset()
        self.assertEqual(self.sender.cancels, 1)

    def test_start_and_close_delegate_without_posting_a_key(self):
        navigation = self.navigation()
        self.assertFalse(self.sender.started)
        self.assertTrue(navigation.start())
        navigation.close()
        self.assertTrue(self.sender.started)
        self.assertTrue(self.sender.closed)
        self.assertEqual(self.sender.presses, [])

    def test_input_that_ages_during_initial_focus_poll_is_dropped(self):
        navigation = self.navigation()

        def delayed_focus():
            self.clock.advance(0.1)
            return True

        self.sender.is_frontmost = delayed_focus
        self.assertFalse(navigation.receive_value(65))
        self.assertEqual(self.sender.presses, [])

    def test_sender_receives_original_input_time_before_focus_poll(self):
        navigation = self.navigation()

        def delayed_focus():
            self.clock.advance(0.01)
            return True

        self.sender.is_frontmost = delayed_focus
        self.assertTrue(navigation.receive_value(65))
        self.assertEqual(self.sender.input_times, [0.0])


if __name__ == "__main__":
    unittest.main()
