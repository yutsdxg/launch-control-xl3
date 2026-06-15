import importlib.util
import sys
import types
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = WORKSPACE_ROOT / "Launch_Control_XL_3_Custom"


def _ensure_package():
    package = sys.modules.get("Launch_Control_XL_3_Custom")
    if package is None:
        package = types.ModuleType("Launch_Control_XL_3_Custom")
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules["Launch_Control_XL_3_Custom"] = package


def _load_module(module_name, relative_path):
    _ensure_package()
    spec = importlib.util.spec_from_file_location(module_name, PACKAGE_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _install_component_stubs():
    ableton = sys.modules.setdefault("ableton", types.ModuleType("ableton"))
    ableton.__path__ = getattr(ableton, "__path__", [])

    ableton_v3 = sys.modules.setdefault("ableton.v3", types.ModuleType("ableton.v3"))
    ableton_v3.__path__ = getattr(ableton_v3, "__path__", [])

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface", types.ModuleType("ableton.v3.control_surface")
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    class _Slot(object):
        def __init__(self, button, listener):
            self._button = button
            self._listener = listener

        def disconnect(self):
            self._button.remove_value_listener(self._listener)

    class Component(object):
        def __init__(self, *a, **k):
            self.song = None

        def register_slot(self, subject, listener, event_name):
            if event_name != "value":
                raise AssertionError("unexpected event name: {}".format(event_name))
            subject.add_value_listener(listener)
            return _Slot(subject, listener)

    control_surface.Component = Component


_install_component_stubs()
LOCATOR_NAVIGATION = _load_module(
    "Launch_Control_XL_3_Custom.locator_navigation",
    "locator_navigation.py",
)


class FakeButton(object):
    def __init__(self):
        self.listeners = []

    def add_value_listener(self, listener):
        self.listeners.append(listener)

    def remove_value_listener(self, listener):
        self.listeners.remove(listener)

    def receive_value(self, value):
        for listener in tuple(self.listeners):
            listener(value)


class FakeSong(object):
    def __init__(self, can_jump_prev=True, can_jump_next=True, is_playing=False):
        self.can_jump_to_prev_cue = can_jump_prev
        self.can_jump_to_next_cue = can_jump_next
        self.is_playing = is_playing
        self.prev_jump_count = 0
        self.next_jump_count = 0
        self.start_playing_count = 0
        self.continue_playing_count = 0

    def jump_to_prev_cue(self):
        self.prev_jump_count += 1

    def jump_to_next_cue(self):
        self.next_jump_count += 1

    def start_playing(self):
        self.start_playing_count += 1
        self.is_playing = True

    def continue_playing(self):
        self.continue_playing_count += 1
        self.is_playing = True


class LocatorNavigationTest(unittest.TestCase):
    def _component(self, song):
        component = LOCATOR_NAVIGATION.LocatorNavigationComponent()
        component.song = song
        return component

    def test_buttons_jump_to_previous_and_next_locator(self):
        song = FakeSong()
        component = self._component(song)
        prev_button = FakeButton()
        next_button = FakeButton()
        component.set_prev_locator_button(prev_button)
        component.set_next_locator_button(next_button)

        prev_button.receive_value(127)
        next_button.receive_value(127)

        self.assertEqual(song.prev_jump_count, 1)
        self.assertEqual(song.next_jump_count, 1)

    def test_button_release_does_not_jump(self):
        song = FakeSong()
        component = self._component(song)
        prev_button = FakeButton()
        next_button = FakeButton()
        component.set_prev_locator_button(prev_button)
        component.set_next_locator_button(next_button)

        prev_button.receive_value(0)
        next_button.receive_value(0)

        self.assertEqual(song.prev_jump_count, 0)
        self.assertEqual(song.next_jump_count, 0)

    def test_unavailable_direction_does_not_jump(self):
        song = FakeSong(can_jump_prev=False, can_jump_next=False)
        component = self._component(song)
        prev_button = FakeButton()
        next_button = FakeButton()
        component.set_prev_locator_button(prev_button)
        component.set_next_locator_button(next_button)

        prev_button.receive_value(127)
        next_button.receive_value(127)

        self.assertEqual(song.prev_jump_count, 0)
        self.assertEqual(song.next_jump_count, 0)

    def test_jumps_preserve_stopped_state_without_starting_playback(self):
        song = FakeSong(is_playing=False)
        component = self._component(song)
        button = FakeButton()
        component.set_next_locator_button(button)

        button.receive_value(127)

        self.assertFalse(song.is_playing)
        self.assertEqual(song.start_playing_count, 0)
        self.assertEqual(song.continue_playing_count, 0)

    def test_jumps_preserve_playing_state(self):
        song = FakeSong(is_playing=True)
        component = self._component(song)
        button = FakeButton()
        component.set_prev_locator_button(button)

        button.receive_value(127)

        self.assertTrue(song.is_playing)
        self.assertEqual(song.start_playing_count, 0)
        self.assertEqual(song.continue_playing_count, 0)


if __name__ == "__main__":
    unittest.main()
