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


def _install_mapping_stubs():
    ableton = sys.modules.setdefault("ableton", types.ModuleType("ableton"))
    ableton.__path__ = getattr(ableton, "__path__", [])

    ableton_v3 = sys.modules.setdefault("ableton.v3", types.ModuleType("ableton.v3"))
    ableton_v3.__path__ = getattr(ableton_v3, "__path__", [])

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface", types.ModuleType("ableton.v3.control_surface")
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    mode = types.ModuleType("ableton.v3.control_surface.mode")

    class ImmediateBehaviour(object):
        pass

    mode.ImmediateBehaviour = ImmediateBehaviour
    mode.make_reenter_behaviour = lambda behaviour, on_reenter=None: (behaviour, on_reenter)
    sys.modules["ableton.v3.control_surface.mode"] = mode

    midi = types.ModuleType("ableton.v3.control_surface.midi")
    midi.SYSEX_START = 240
    midi.SYSEX_END = 247
    sys.modules["ableton.v3.control_surface.midi"] = midi


_install_mapping_stubs()
MAPPINGS = _load_module("Launch_Control_XL_3_Custom.mappings", "mappings.py")


class FakeControlSurface(object):
    def __init__(self):
        self.sent_messages = []

    def send_midi(self, message):
        self.sent_messages.append(message)


class MappingsTest(unittest.TestCase):
    def setUp(self):
        self.mappings = MAPPINGS.create_mappings(FakeControlSurface())

    def test_daw_control_button_modes_are_removed(self):
        self.assertNotIn("Daw_Control_Button_Modes", self.mappings)

    def test_performance_buttons_use_buttons_7_8_15_16(self):
        self.assertEqual(
            self.mappings["Performance_Buttons"],
            {
                "cursor_up_button": "daw_control_buttons_raw[6]",
                "pitch_up_button": "daw_control_buttons_raw[7]",
                "cursor_down_button": "device_toggle_7_button",
                "pitch_down_button": "device_toggle_8_button",
            },
        )

    def test_device_toggle_keeps_only_buttons_9_to_14(self):
        device_toggle = self.mappings["Daw_Mixer_Button_Modes"]["device_toggle"]

        self.assertEqual(device_toggle["toggle_button_1"], "device_toggle_1_button")
        self.assertEqual(device_toggle["toggle_button_6"], "device_toggle_6_button")
        self.assertNotIn("toggle_button_7", device_toggle)
        self.assertNotIn("toggle_button_8", device_toggle)


if __name__ == "__main__":
    unittest.main()
