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
        OFF = _Color(0)
        WHITE = _Color(3)
        RED = _Color(5)
        DARK_RED = _Color(2)
        RED_HALF = _Color(7)
        BLUE = _Color(41)
        BLUE_HALF = _Color(43)
        DARK_BLUE = _Color(47)

    colors.Rgb = Rgb
    sys.modules["Launch_Control_XL_3_Custom.colors"] = colors

    midi = types.ModuleType("Launch_Control_XL_3_Custom.midi")
    midi.SYSEX_HEADER = (240, 0, 32, 41, 2, 21)
    midi.SYSEX_END = 247
    sys.modules["Launch_Control_XL_3_Custom.midi"] = midi


_install_component_stubs()
PERFORMANCE_BUTTONS = _load_module(
    "Launch_Control_XL_3_Custom.performance_buttons",
    "performance_buttons.py",
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


class FakeParameter(object):
    def __init__(self, name, value=0.0, min_value=-128.0, max_value=127.0, is_enabled=True):
        self.name = name
        self._value = value
        self.min = min_value
        self.max = max_value
        self.is_enabled = is_enabled
        self.listeners = []

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        for listener in tuple(self.listeners):
            listener()

    def add_value_listener(self, listener):
        self.listeners.append(listener)

    def remove_value_listener(self, listener):
        self.listeners.remove(listener)


class FakeDevice(object):
    def __init__(self, parameters=()):
        self.parameters = tuple(parameters)


class FakeTrack(object):
    def __init__(self, devices=()):
        self.devices = tuple(devices)


class FakeView(object):
    def __init__(self, selected_track):
        self.selected_track = selected_track


class FakeSong(object):
    def __init__(self, selected_track):
        self.view = FakeView(selected_track)


def _rgb_led_message(control_index, rgb):
    return PERFORMANCE_BUTTONS.RGB_LED_SYSEX_PREFIX + (control_index,) + rgb + (247,)


class PerformanceButtonsTest(unittest.TestCase):
    def _component(self, selected_track):
        component = PERFORMANCE_BUTTONS.PerformanceButtonsComponent()
        component.song = FakeSong(selected_track)
        return component

    def _track_with_pitch(self, pitch_value=0.0, is_enabled=True):
        pitch = FakeParameter("Pitch", value=pitch_value, is_enabled=is_enabled)
        return FakeTrack(devices=(FakeDevice(), FakeDevice(parameters=(pitch,)))), pitch

    def test_cursor_buttons_are_white_only_while_held(self):
        component = self._component(FakeTrack())
        cursor_up = FakeButton()
        cursor_down = FakeButton()

        component.set_cursor_up_button(cursor_up)
        component.set_cursor_down_button(cursor_down)

        self.assertEqual(cursor_up.sent_values[-1], PERFORMANCE_BUTTONS.BUTTON_LED_OFF_VALUE)
        self.assertEqual(cursor_down.sent_values[-1], PERFORMANCE_BUTTONS.BUTTON_LED_OFF_VALUE)

        cursor_up.receive_value(127)
        cursor_down.receive_value(127)
        self.assertEqual(cursor_up.sent_values[-1], PERFORMANCE_BUTTONS.MOMENTARY_BUTTON_LED_ON_VALUE)
        self.assertEqual(cursor_down.sent_values[-1], PERFORMANCE_BUTTONS.MOMENTARY_BUTTON_LED_ON_VALUE)

        cursor_up.receive_value(0)
        cursor_down.receive_value(0)
        self.assertEqual(cursor_up.sent_values[-1], PERFORMANCE_BUTTONS.BUTTON_LED_OFF_VALUE)
        self.assertEqual(cursor_down.sent_values[-1], PERFORMANCE_BUTTONS.BUTTON_LED_OFF_VALUE)

    def test_pitch_up_button_steps_pitch_and_uses_red_led_levels(self):
        track, pitch = self._track_with_pitch()
        component = self._component(track)
        pitch_up = FakeButton(identifier=44)
        pitch_down = FakeButton(identifier=52)

        component.set_pitch_up_button(pitch_up)
        component.set_pitch_down_button(pitch_down)

        pitch_up.receive_value(127)
        self.assertEqual(pitch.value, 12.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (127, 42, 42)))

        pitch_up.receive_value(127)
        self.assertEqual(pitch.value, 24.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (127, 12, 12)))

        pitch_up.receive_value(127)
        self.assertEqual(pitch.value, 36.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (64, 10, 10)))

        pitch_up.receive_value(127)
        self.assertEqual(pitch.value, 48.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (64, 10, 10)))
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))

    def test_pitch_down_button_steps_pitch_and_uses_blue_led_levels(self):
        track, pitch = self._track_with_pitch()
        component = self._component(track)
        pitch_up = FakeButton(identifier=44)
        pitch_down = FakeButton(identifier=52)

        component.set_pitch_up_button(pitch_up)
        component.set_pitch_down_button(pitch_down)

        pitch_down.receive_value(127)
        self.assertEqual(pitch.value, -12.0)
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, (44, 84, 127)))

        pitch_down.receive_value(127)
        self.assertEqual(pitch.value, -24.0)
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, (14, 54, 127)))

        pitch_down.receive_value(127)
        self.assertEqual(pitch.value, -36.0)
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, (10, 34, 96)))

        pitch_down.receive_value(127)
        self.assertEqual(pitch.value, -48.0)
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, (10, 34, 96)))
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))

    def test_pitch_steps_are_clamped_to_parameter_range(self):
        track, pitch = self._track_with_pitch(pitch_value=120.0)
        component = self._component(track)
        pitch_up = FakeButton()

        component.set_pitch_up_button(pitch_up)
        pitch_up.receive_value(127)

        self.assertEqual(pitch.value, 127.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(0, (64, 10, 10)))

    def test_missing_or_invalid_pitch_target_turns_pitch_leds_off(self):
        cases = (
            None,
            FakeTrack(devices=()),
            FakeTrack(devices=(FakeDevice(),)),
            FakeTrack(devices=(FakeDevice(), FakeDevice(parameters=(FakeParameter("Transpose"),)))),
        )

        for track in cases:
            component = self._component(track)
            pitch_up = FakeButton()
            pitch_down = FakeButton()

            component.set_pitch_up_button(pitch_up)
            component.set_pitch_down_button(pitch_down)
            pitch_up.receive_value(127)
            pitch_down.receive_value(127)

            self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(0, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))
            self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(0, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))

    def test_disabled_pitch_parameter_is_ignored_and_leds_off(self):
        track, pitch = self._track_with_pitch(is_enabled=False)
        component = self._component(track)
        pitch_up = FakeButton()

        component.set_pitch_up_button(pitch_up)
        pitch_up.receive_value(127)

        self.assertEqual(pitch.value, 0.0)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(0, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))

    def test_external_pitch_value_change_updates_leds_from_current_value(self):
        track, pitch = self._track_with_pitch()
        component = self._component(track)
        pitch_up = FakeButton(identifier=44)
        pitch_down = FakeButton(identifier=52)

        component.set_pitch_up_button(pitch_up)
        component.set_pitch_down_button(pitch_down)

        pitch.value = 24.0
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (127, 12, 12)))
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))

        pitch.value = -36.0
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, PERFORMANCE_BUTTONS.PITCH_LED_OFF_VALUE))
        self.assertEqual(pitch_down.sent_midi[-1], _rgb_led_message(52, (10, 34, 96)))

    def test_polling_retargets_pitch_listener_when_selected_track_changes(self):
        first_track, first_pitch = self._track_with_pitch()
        second_track, second_pitch = self._track_with_pitch(pitch_value=36.0)
        component = self._component(first_track)
        pitch_up = FakeButton(identifier=44)

        component.set_pitch_up_button(pitch_up)
        self.assertIn(component._on_pitch_parameter_value_changed, first_pitch.listeners)

        component.song.view.selected_track = second_track
        component._update_pitch_led_feedback()

        self.assertNotIn(component._on_pitch_parameter_value_changed, first_pitch.listeners)
        self.assertIn(component._on_pitch_parameter_value_changed, second_pitch.listeners)
        self.assertEqual(pitch_up.sent_midi[-1], _rgb_led_message(44, (64, 10, 10)))


if __name__ == "__main__":
    unittest.main()
