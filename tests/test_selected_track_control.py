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


def _install_selected_track_control_stubs():
    ableton = sys.modules.setdefault("ableton", types.ModuleType("ableton"))
    ableton.__path__ = getattr(ableton, "__path__", [])

    ableton_v3 = sys.modules.setdefault("ableton.v3", types.ModuleType("ableton.v3"))
    ableton_v3.__path__ = getattr(ableton_v3, "__path__", [])

    base = types.ModuleType("ableton.v3.base")

    class _TaskModule(object):
        @staticmethod
        def loop(value):
            return value

        @staticmethod
        def sequence(*values):
            return values

        @staticmethod
        def run(callback):
            return callback

        @staticmethod
        def delay(value):
            return value

    base.task = _TaskModule
    sys.modules["ableton.v3.base"] = base

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface", types.ModuleType("ableton.v3.control_surface")
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    class _Tasks(object):
        def __init__(self):
            self.added = []

        def add(self, value):
            self.added.append(value)
            return value

    class _Slot(object):
        def __init__(self, button, listener):
            self._button = button
            self._listener = listener

        def disconnect(self):
            self._button.remove_value_listener(self._listener)

    class Component(object):
        def __init__(self, *a, **k):
            self._tasks = _Tasks()
            self.song = None

        def register_slot(self, subject, listener, event_name):
            if event_name != "value":
                raise AssertionError("unexpected event name: {}".format(event_name))
            subject.add_value_listener(listener)
            return _Slot(subject, listener)

    control_surface.Component = Component

    live = types.ModuleType("ableton.v3.live")
    live.liveobj_valid = lambda obj: obj is not None
    sys.modules["ableton.v3.live"] = live

    colors = types.ModuleType("Launch_Control_XL_3_Custom.colors")

    class _Color(object):
        def __init__(self, midi_value):
            self.midi_value = midi_value

    class Rgb(object):
        BLUE = _Color(41)
        BLUE_HALF = _Color(43)
        YELLOW = _Color(97)
        DARK_YELLOW = _Color(15)

    colors.Rgb = Rgb
    sys.modules["Launch_Control_XL_3_Custom.colors"] = colors

    midi = types.ModuleType("Launch_Control_XL_3_Custom.midi")
    midi.SYSEX_HEADER = (240, 0, 32, 41, 2, 21)
    midi.SYSEX_END = 247
    sys.modules["Launch_Control_XL_3_Custom.midi"] = midi


_install_selected_track_control_stubs()
SELECTED_TRACK_CONTROL = _load_module(
    "Launch_Control_XL_3_Custom.selected_track_control",
    "selected_track_control.py",
)


class FakeButton(object):
    def __init__(self, identifier=0):
        self.identifier = identifier
        self.listeners = []
        self.sent_values = []
        self.sent_midi = []

    def add_value_listener(self, listener):
        self.listeners.append(listener)

    def remove_value_listener(self, listener):
        self.listeners.remove(listener)

    def send_value(self, value):
        self.sent_values.append(value)

    def send_midi(self, message):
        self.sent_midi.append(message)

    def message_identifier(self):
        return self.identifier

    def receive_value(self, value):
        for listener in tuple(self.listeners):
            listener(value)


class FakeTrack(object):
    def __init__(self, solo=False, mute=False):
        self.solo = solo
        self.mute = mute


class FakeView(object):
    def __init__(self, selected_track):
        self.selected_track = selected_track


class FakeSong(object):
    def __init__(self, selected_track):
        self.view = FakeView(selected_track)


def _rgb_led_message(control_index, rgb):
    return SELECTED_TRACK_CONTROL.RGB_LED_SYSEX_PREFIX + (control_index,) + rgb + (247,)


class SelectedTrackControlTest(unittest.TestCase):
    def _component(self, selected_track):
        component = SELECTED_TRACK_CONTROL.SelectedTrackControlComponent()
        component.song = FakeSong(selected_track)
        return component

    def test_solo_button_toggles_selected_track_solo(self):
        track = FakeTrack(solo=False)
        component = self._component(track)
        button = FakeButton(identifier=65)

        component.set_solo_button(button)
        self.assertEqual(button.sent_midi[-1], _rgb_led_message(65, SELECTED_TRACK_CONTROL.SOLO_LED_OFF_VALUE))

        button.receive_value(127)
        self.assertTrue(track.solo)
        self.assertEqual(button.sent_values[-1], SELECTED_TRACK_CONTROL.SOLO_LED_ON_VALUE)

        button.receive_value(127)
        self.assertFalse(track.solo)
        self.assertEqual(button.sent_midi[-1], _rgb_led_message(65, SELECTED_TRACK_CONTROL.SOLO_LED_OFF_VALUE))

    def test_track_on_button_toggles_mute_and_keeps_led_polarity(self):
        track = FakeTrack(mute=False)
        component = self._component(track)
        button = FakeButton(identifier=66)

        component.set_track_on_button(button)
        self.assertEqual(button.sent_values[-1], SELECTED_TRACK_CONTROL.TRACK_ON_LED_VALUE)

        button.receive_value(127)
        self.assertTrue(track.mute)
        self.assertEqual(button.sent_midi[-1], _rgb_led_message(66, SELECTED_TRACK_CONTROL.TRACK_OFF_LED_VALUE))

        button.receive_value(127)
        self.assertFalse(track.mute)
        self.assertEqual(button.sent_values[-1], SELECTED_TRACK_CONTROL.TRACK_ON_LED_VALUE)

    def test_release_value_does_not_toggle(self):
        track = FakeTrack(solo=False, mute=False)
        component = self._component(track)
        solo_button = FakeButton(identifier=65)
        track_on_button = FakeButton(identifier=66)

        component.set_solo_button(solo_button)
        component.set_track_on_button(track_on_button)
        solo_button.receive_value(0)
        track_on_button.receive_value(0)

        self.assertFalse(track.solo)
        self.assertFalse(track.mute)

    def test_missing_or_invalid_selected_track_does_not_raise(self):
        missing_property_track = object()
        component = self._component(missing_property_track)
        solo_button = FakeButton(identifier=65)
        track_on_button = FakeButton(identifier=66)

        component.set_solo_button(solo_button)
        component.set_track_on_button(track_on_button)
        solo_button.receive_value(127)
        track_on_button.receive_value(127)

        self.assertEqual(solo_button.sent_midi[-1], _rgb_led_message(65, SELECTED_TRACK_CONTROL.SOLO_LED_OFF_VALUE))
        self.assertEqual(track_on_button.sent_midi[-1], _rgb_led_message(66, SELECTED_TRACK_CONTROL.TRACK_OFF_LED_VALUE))

        component.song.view.selected_track = None
        solo_button.receive_value(127)
        track_on_button.receive_value(127)

        self.assertEqual(solo_button.sent_midi[-1], _rgb_led_message(65, SELECTED_TRACK_CONTROL.SOLO_LED_OFF_VALUE))
        self.assertEqual(track_on_button.sent_midi[-1], _rgb_led_message(66, SELECTED_TRACK_CONTROL.TRACK_OFF_LED_VALUE))

    def test_led_feedback_updates_after_external_state_change(self):
        track = FakeTrack(solo=False, mute=False)
        component = self._component(track)
        solo_button = FakeButton(identifier=65)
        track_on_button = FakeButton(identifier=66)

        component.set_solo_button(solo_button)
        component.set_track_on_button(track_on_button)

        track.solo = True
        track.mute = True
        component._update_led_feedback()

        self.assertEqual(solo_button.sent_values[-1], SELECTED_TRACK_CONTROL.SOLO_LED_ON_VALUE)
        self.assertEqual(track_on_button.sent_midi[-1], _rgb_led_message(66, SELECTED_TRACK_CONTROL.TRACK_OFF_LED_VALUE))

    def test_refresh_led_feedback_forces_current_state_to_buttons(self):
        track = FakeTrack(solo=True, mute=False)
        component = self._component(track)
        solo_button = FakeButton(identifier=65)
        track_on_button = FakeButton(identifier=66)

        component.set_solo_button(solo_button)
        component.set_track_on_button(track_on_button)
        solo_send_count = len(solo_button.sent_values)
        track_on_send_count = len(track_on_button.sent_values)

        component.refresh_led_feedback()

        self.assertEqual(len(solo_button.sent_values), solo_send_count + 1)
        self.assertEqual(len(track_on_button.sent_values), track_on_send_count + 1)
        self.assertEqual(solo_button.sent_values[-1], SELECTED_TRACK_CONTROL.SOLO_LED_ON_VALUE)
        self.assertEqual(track_on_button.sent_values[-1], SELECTED_TRACK_CONTROL.TRACK_ON_LED_VALUE)

    def test_custom_rgb_uses_configured_midi_sender(self):
        track = FakeTrack(solo=False)
        component = self._component(track)
        midi_messages = []
        component.set_midi_sender(midi_messages.append)
        button = FakeButton(identifier=65)

        component.set_solo_button(button)

        self.assertEqual(midi_messages[-1], _rgb_led_message(65, SELECTED_TRACK_CONTROL.SOLO_LED_OFF_VALUE))
        self.assertEqual(button.sent_midi, [])


if __name__ == "__main__":
    unittest.main()
