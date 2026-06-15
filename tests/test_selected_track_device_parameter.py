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

    class Component(object):
        def __init__(self, *a, **k):
            self._tasks = _Tasks()
            self.song = None

        def disconnect(self):
            pass

    control_surface.Component = Component

    live = types.ModuleType("ableton.v3.live")
    live.liveobj_valid = lambda obj: obj is not None
    sys.modules["ableton.v3.live"] = live

    utils = types.ModuleType("Launch_Control_XL_3_Custom.custom_parameter_utils")
    utils.DEVICE_ON_PARAMETER_NAME = "Device On"
    sys.modules["Launch_Control_XL_3_Custom.custom_parameter_utils"] = utils


_install_component_stubs()
SELECTED_TRACK_DEVICE_PARAMETER = _load_module(
    "Launch_Control_XL_3_Custom.selected_track_device_parameter",
    "selected_track_device_parameter.py",
)


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


def _target_track(parameter_1=None, parameter_2=None):
    parameter_1 = parameter_1 or FakeParameter("Parameter 1")
    parameter_2 = parameter_2 or FakeParameter("Parameter 2")
    target_device = FakeDevice(
        parameters=(
            FakeParameter("Device On"),
            parameter_1,
            parameter_2,
        )
    )
    return FakeTrack(devices=(FakeDevice(), FakeDevice(), FakeDevice(), target_device))


class SelectedTrackDeviceParameterTest(unittest.TestCase):
    def _component(self, selected_track):
        component = SELECTED_TRACK_DEVICE_PARAMETER.SelectedTrackDeviceParameterComponent()
        component.song = FakeSong(selected_track)
        return component

    def test_fader_connects_to_selected_track_device_4_parameter_2(self):
        target = FakeParameter("Parameter 2")
        component = self._component(_target_track(parameter_2=target))
        fader = FakeFader()

        component.set_fader(fader)

        self.assertEqual(fader.connected_parameters[-1], target)

    def test_device_on_is_excluded_from_parameter_numbering(self):
        parameter_1 = FakeParameter("Parameter 1")
        parameter_2 = FakeParameter("Parameter 2")
        component = self._component(_target_track(parameter_1=parameter_1, parameter_2=parameter_2))
        fader = FakeFader()

        component.set_fader(fader)

        self.assertIs(fader.connected_parameters[-1], parameter_2)

    def test_assignment_retargets_when_selected_track_changes(self):
        first_target = FakeParameter("First Parameter 2")
        second_target = FakeParameter("Second Parameter 2")
        component = self._component(_target_track(parameter_2=first_target))
        fader = FakeFader()
        component.set_fader(fader)

        component.song.view.selected_track = _target_track(parameter_2=second_target)
        component._update_assignment()

        self.assertEqual(fader.connected_parameters, [first_target, second_target])

    def test_missing_device_releases_existing_assignment(self):
        component = self._component(_target_track())
        fader = FakeFader()
        component.set_fader(fader)
        release_count = fader.release_count

        component.song.view.selected_track = FakeTrack(devices=(FakeDevice(),))
        component._update_assignment()

        self.assertEqual(fader.release_count, release_count + 1)

    def test_disabled_parameter_is_not_connected(self):
        component = self._component(_target_track(parameter_2=FakeParameter("Parameter 2", is_enabled=False)))
        fader = FakeFader()

        component.set_fader(fader)

        self.assertEqual(fader.connected_parameters, [])

    def test_connected_parameter_is_released_when_it_becomes_disabled(self):
        target = FakeParameter("Parameter 2")
        component = self._component(_target_track(parameter_2=target))
        fader = FakeFader()
        component.set_fader(fader)
        release_count = fader.release_count

        target.is_enabled = False
        component._update_assignment()

        self.assertEqual(fader.release_count, release_count + 1)


if __name__ == "__main__":
    unittest.main()
