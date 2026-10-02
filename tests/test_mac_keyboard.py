import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "Launch_Control_XL_3_Mixing" / "mac_keyboard.py"
SPEC = importlib.util.spec_from_file_location("lcxl3_mac_keyboard_test", MODULE_PATH)
MAC_KEYBOARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MAC_KEYBOARD)


class FakeNative:
    def __init__(self, foreground=True, permission=True):
        self.foreground = foreground
        self.permission = permission
        self.calls = []
        self.creation_results = ["down", "up"]
        self.foreground_results = []
        self.permission_results = []
        self.release_errors = set()
        self.post_errors = set()

    def is_frontmost(self, pid):
        self.calls.append(("foreground", pid))
        if self.foreground_results:
            return self.foreground_results.pop(0)
        return self.foreground

    def can_post(self):
        self.calls.append(("permission",))
        if self.permission_results:
            return self.permission_results.pop(0)
        return self.permission

    def create_keyboard_event(self, keycode, key_down):
        self.calls.append(("create", keycode, key_down))
        return self.creation_results.pop(0)

    def set_flags(self, event, flags):
        self.calls.append(("flags", event, flags))

    def post(self, pid, event):
        self.calls.append(("post", pid, event))
        if event in self.post_errors:
            raise RuntimeError("post failure")

    def release(self, event):
        self.calls.append(("release", event))
        if event in self.release_errors:
            raise RuntimeError("release failure")


class MacKeyboardSenderTest(unittest.TestCase):
    def setUp(self):
        self.native = FakeNative()
        self.factory = self.start_patch(patch.object(MAC_KEYBOARD, "_NativeBindings", return_value=self.native))
        self.start_patch(patch.object(MAC_KEYBOARD.sys, "platform", "darwin"))
        self.start_patch(patch.object(MAC_KEYBOARD.os, "getpid", return_value=12345))
        self.logger = self.start_patch(patch.object(MAC_KEYBOARD, "LOGGER"))
        self.sender = MAC_KEYBOARD.MacKeyboardSender()

    def start_patch(self, patcher):
        self.addCleanup(patcher.stop)
        return patcher.start()

    def calls(self, kind):
        return [call for call in self.native.calls if call[0] == kind]

    def test_initializes_lazily_and_reuses_native_bindings(self):
        self.factory.assert_not_called()
        self.assertTrue(self.sender.is_frontmost())
        self.assertTrue(self.sender.is_frontmost())
        self.factory.assert_called_once_with()
        self.assertEqual(self.calls("foreground"), [("foreground", 12345)] * 2)

    def test_background_input_does_not_create_or_send_events(self):
        self.native.foreground = False
        self.assertFalse(self.sender.press(-1))
        self.assertFalse(self.calls("permission"))
        self.assertFalse(self.calls("create"))
        self.assertFalse(self.calls("post"))

    def test_missing_permission_stops_events_and_logs_only_transition(self):
        self.native.permission = False
        self.assertFalse(self.sender.press(1))
        self.assertFalse(self.sender.press(1))
        self.assertFalse(self.calls("create"))
        self.logger.warning.assert_called_once()
        self.native.permission = True
        self.assertTrue(self.sender.press(1))
        self.logger.info.assert_called_once()
        self.native.permission = False
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.logger.warning.call_count, 2)

    def test_directions_generate_plain_down_then_up_before_posting(self):
        for direction, keycode in ((-1, 126), (1, 125)):
            with self.subTest(direction=direction):
                self.native.calls.clear()
                self.native.creation_results = ["down", "up"]
                self.assertTrue(self.sender.press(direction))
                self.assertEqual(self.calls("create"), [("create", keycode, True), ("create", keycode, False)])
                self.assertEqual(self.calls("flags"), [("flags", "down", 0), ("flags", "up", 0)])
                self.assertEqual(self.calls("post"), [("post", 12345, "down"), ("post", 12345, "up")])
                self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])
                first_post = next(index for index, call in enumerate(self.native.calls) if call[0] == "post")
                self.assertEqual(sum(call[0] == "create" for call in self.native.calls[:first_post]), 2)

    def test_creation_failure_never_posts_partial_key_pair(self):
        for results, released in (([None], []), (["down", None], [("release", "down")])):
            with self.subTest(results=results):
                self.native.calls.clear()
                self.native.creation_results = list(results)
                self.assertFalse(self.sender.press(-1))
                self.assertFalse(self.calls("post"))
                self.assertEqual(self.calls("release"), released)

    def test_foreground_is_rechecked_before_post_and_created_events_released(self):
        self.native.foreground_results = [True, False]
        self.assertFalse(self.sender.press(-1))
        self.assertFalse(self.calls("post"))
        self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])

    def test_permission_is_rechecked_before_post_and_created_events_released(self):
        self.native.permission_results = [True, False]
        self.assertFalse(self.sender.press(-1))
        self.assertFalse(self.calls("post"))
        self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])

    def test_cleanup_failure_does_not_skip_other_release_or_escape(self):
        self.native.release_errors.add("down")
        self.assertFalse(self.sender.press(-1))
        self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])
        self.logger.warning.assert_called_once()

    def test_key_up_post_failure_retries_release_and_cleans_up(self):
        self.native.post_errors.add("up")
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.calls("post"), [("post", 12345, "down"), ("post", 12345, "up"), ("post", 12345, "up")])
        self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])

    def test_key_down_post_failure_still_attempts_key_up(self):
        self.native.post_errors.add("down")
        self.assertFalse(self.sender.press(1))
        self.assertEqual(self.calls("post"), [("post", 12345, "down"), ("post", 12345, "up")])
        self.assertEqual(self.calls("release"), [("release", "down"), ("release", "up")])

    def test_exception_while_creating_key_up_releases_created_key_down(self):
        with patch.object(self.native, "create_keyboard_event", side_effect=["down", RuntimeError("creation failure")]):
            self.assertFalse(self.sender.press(-1))
        self.assertFalse(self.calls("post"))
        self.assertEqual(self.calls("release"), [("release", "down")])

    def test_foreground_native_exception_is_isolated(self):
        with patch.object(self.native, "is_frontmost", side_effect=RuntimeError("focus failure")):
            self.assertFalse(self.sender.is_frontmost())
            self.assertFalse(self.sender.is_frontmost())
        self.logger.warning.assert_called_once()

    def test_initialization_failure_is_isolated_and_not_retried_per_event(self):
        self.factory.side_effect = ImportError("_ctypes unavailable")
        self.assertFalse(self.sender.is_frontmost())
        self.assertFalse(self.sender.press(1))
        self.factory.assert_called_once_with()
        self.logger.warning.assert_called_once()

    def test_unsupported_platform_never_initializes_native_libraries(self):
        for platform in ("linux", "win32"):
            with self.subTest(platform=platform), patch.object(MAC_KEYBOARD.sys, "platform", platform):
                sender = MAC_KEYBOARD.MacKeyboardSender()
                self.assertFalse(sender.is_frontmost())
                self.assertFalse(sender.press(-1))
        self.factory.assert_not_called()

    def test_invalid_direction_is_ignored_without_initialization(self):
        for direction in (0, 2, None, "up"):
            self.assertFalse(self.sender.press(direction))
        self.factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
