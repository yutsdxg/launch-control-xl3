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

    live = types.ModuleType("ableton.v3.live")
    action = types.SimpleNamespace(selected_tracks=[])
    action.select = lambda track: action.selected_tracks.append(track)
    live.action = action
    live.liveobj_valid = lambda obj: obj is not None
    sys.modules["ableton.v3.live"] = live

    colors = types.ModuleType("Launch_Control_XL_3_Custom.colors")

    class _Color(object):
        def __init__(self, midi_value):
            self.midi_value = midi_value

    class Rgb(object):
        WHITE_DIM = _Color(103)
        YELLOW = _Color(97)

    colors.Rgb = Rgb
    sys.modules["Launch_Control_XL_3_Custom.colors"] = colors


_install_component_stubs()
FADER_ASSIGNMENT_TOGGLE = _load_module(
    "Launch_Control_XL_3_Custom.fader_assignment_toggle",
    "fader_assignment_toggle.py",
)


class FakeButton(object):
    def __init__(self):
        self.listeners = []
        self.sent_values = []

    def add_value_listener(self, listener):
        self.listeners.append(listener)

    def remove_value_listener(self, listener):
        self.listeners.remove(listener)

    def send_value(self, value):
        self.sent_values.append(value)

    def receive_value(self, value):
        for listener in tuple(self.listeners):
            listener(value)


class FakeFader(object):
    def __init__(self):
        self.connected_parameters = []
        self.release_count = 0

    def connect_to(self, parameter):
        self.connected_parameters.append(parameter)

    def release_parameter(self):
        self.release_count += 1


class FakeParameter(object):
    def __init__(self, name, is_enabled=True):
        self.name = name
        self.is_enabled = is_enabled


class FakeMixerDevice(object):
    def __init__(self, volume=None, cue_volume=None):
        self.volume = volume
        self.cue_volume = cue_volume


class FakeTrack(object):
    def __init__(self, name, volume):
        self.name = name
        self.mixer_device = FakeMixerDevice(volume=volume)


class FakeSong(object):
    def __init__(self, tracks=(), cue_volume=None):
        self.tracks = tuple(tracks)
        self.master_track = FakeTrack("Master", FakeParameter("Master Volume"))
        self.master_track.mixer_device.cue_volume = cue_volume


class FaderAssignmentToggleTest(unittest.TestCase):
    def setUp(self):
        FADER_ASSIGNMENT_TOGGLE.action.selected_tracks[:] = []

    def _component(self, tracks=(), cue_volume=None):
        component = FADER_ASSIGNMENT_TOGGLE.FaderAssignmentToggleComponent()
        component.song = FakeSong(tracks=tracks, cue_volume=cue_volume)
        return component

    def test_initial_assignment_connects_fader_to_loopcloud_volume_and_sets_yellow_led(self):
        cue_volume = FakeParameter("Cue Volume")
        loopcloud_volume = FakeParameter("Loopcloud Volume")
        tracks = (FakeTrack("Loopcloud", loopcloud_volume),)
        component = self._component(cue_volume=cue_volume)
        component.song.tracks = tracks
        fader = FakeFader()
        button = FakeButton()

        component.set_fader(fader)
        component.set_toggle_button(button)

        self.assertEqual(fader.connected_parameters[-1], loopcloud_volume)
        self.assertEqual(button.sent_values[-1], FADER_ASSIGNMENT_TOGGLE.ASSIGNMENT_2_LED_VALUE)

    def test_refresh_led_feedback_forces_current_assignment_led(self):
        component = self._component(
            tracks=(FakeTrack("Loopcloud", FakeParameter("Loopcloud Volume")),),
            cue_volume=FakeParameter("Cue Volume"),
        )
        component.set_fader(FakeFader())
        button = FakeButton()

        component.set_toggle_button(button)
        component.refresh_led_feedback()

        self.assertEqual(
            button.sent_values[-2:],
            [
                FADER_ASSIGNMENT_TOGGLE.ASSIGNMENT_2_LED_VALUE,
                FADER_ASSIGNMENT_TOGGLE.ASSIGNMENT_2_LED_VALUE,
            ],
        )

    def test_button_press_switches_to_cue_volume_and_dark_grey_led(self):
        cue_volume = FakeParameter("Cue Volume")
        loopcloud_volume = FakeParameter("Loopcloud Volume")
        tracks = (
            FakeTrack("Drums", FakeParameter("Drums Volume")),
            FakeTrack("Loopcloud", loopcloud_volume),
        )
        component = self._component(tracks=tracks, cue_volume=cue_volume)
        fader = FakeFader()
        button = FakeButton()

        component.set_fader(fader)
        component.set_toggle_button(button)
        button.receive_value(127)

        self.assertEqual(fader.connected_parameters[-1], cue_volume)
        self.assertEqual(button.sent_values[-1], FADER_ASSIGNMENT_TOGGLE.ASSIGNMENT_1_LED_VALUE)

    def test_button_press_selects_loopcloud_track_on_both_toggle_sides(self):
        loopcloud_track = FakeTrack("Loopcloud", FakeParameter("Loopcloud Volume"))
        component = self._component(
            tracks=(FakeTrack("Drums", FakeParameter("Drums Volume")), loopcloud_track),
            cue_volume=FakeParameter("Cue Volume"),
        )
        component.set_fader(FakeFader())
        button = FakeButton()
        component.set_toggle_button(button)

        button.receive_value(127)
        button.receive_value(127)

        self.assertEqual(
            FADER_ASSIGNMENT_TOGGLE.action.selected_tracks,
            [loopcloud_track, loopcloud_track],
        )

    def test_button_release_does_not_toggle_assignment(self):
        cue_volume = FakeParameter("Cue Volume")
        loopcloud_volume = FakeParameter("Loopcloud Volume")
        component = self._component(
            tracks=(FakeTrack("Loopcloud", loopcloud_volume),),
            cue_volume=cue_volume,
        )
        fader = FakeFader()
        button = FakeButton()

        component.set_fader(fader)
        component.set_toggle_button(button)
        button.receive_value(0)

        self.assertEqual(fader.connected_parameters[-1], loopcloud_volume)
        self.assertEqual(button.sent_values[-1], FADER_ASSIGNMENT_TOGGLE.ASSIGNMENT_2_LED_VALUE)
        self.assertEqual(FADER_ASSIGNMENT_TOGGLE.action.selected_tracks, [])

    def test_initial_missing_loopcloud_falls_back_to_first_track_volume(self):
        first_track_volume = FakeParameter("Track 1 Volume")
        component = self._component(
            tracks=(
                FakeTrack("Track 1", first_track_volume),
                FakeTrack("Track 2", FakeParameter("Track 2 Volume")),
            ),
            cue_volume=FakeParameter("Cue Volume"),
        )
        fader = FakeFader()
        button = FakeButton()

        component.set_fader(fader)
        component.set_toggle_button(button)

        self.assertEqual(fader.connected_parameters[-1], first_track_volume)

    def test_button_press_without_loopcloud_does_not_select_first_track(self):
        component = self._component(
            tracks=(FakeTrack("Track 1", FakeParameter("Track 1 Volume")),),
            cue_volume=FakeParameter("Cue Volume"),
        )
        component.set_fader(FakeFader())
        button = FakeButton()
        component.set_toggle_button(button)

        button.receive_value(127)

        self.assertEqual(FADER_ASSIGNMENT_TOGGLE.action.selected_tracks, [])

    def test_switching_releases_previous_parameter_before_connecting_next(self):
        component = self._component(
            tracks=(FakeTrack("Loopcloud", FakeParameter("Loopcloud Volume")),),
            cue_volume=FakeParameter("Cue Volume"),
        )
        fader = FakeFader()
        button = FakeButton()

        component.set_fader(fader)
        component.set_toggle_button(button)
        release_count_before_toggle = fader.release_count
        button.receive_value(127)

        self.assertEqual(fader.release_count, release_count_before_toggle + 1)
        self.assertEqual(len(fader.connected_parameters), 2)


if __name__ == "__main__":
    unittest.main()
