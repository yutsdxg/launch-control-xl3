"""The optional Live probe must observe native input without changing mappings."""

import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


def load_probe():
    base = types.ModuleType("ableton.v2.base")
    base.task = object()
    surface = types.ModuleType("ableton.v2.control_surface")
    surface.ControlSurface = object
    path = Path(__file__).resolve().parents[1] / "diagnostics/LCXL3_Saturator_Probe/__init__.py"
    spec = importlib.util.spec_from_file_location("saturator_probe_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"ableton.v2.base": base, "ableton.v2.control_surface": surface}):
        spec.loader.exec_module(module)
    return module


PROBE = load_probe()


class ObservedParameter:
    min, max = -36.0, 36.0
    is_enabled, is_quantized, automation_state, state = True, False, 0, 0
    value_items = ()

    def __init__(self, name, value=0.0):
        self.name = self.original_name = name
        self._value = value
        self.listeners = []

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, unused):
        raise AssertionError("The diagnostic must never write parameter values")

    def add_value_listener(self, callback):
        self.listeners.append(callback)

    def remove_value_listener(self, callback):
        self.listeners.remove(callback)

    def native_change(self, value):
        self._value = value
        for callback in tuple(self.listeners):
            callback()


class ObservedControl:
    def __init__(self, parameter):
        self.mapped_parameter = parameter
        self.listeners = []

    def add_value_listener(self, callback):
        self.listeners.append(callback)

    def remove_value_listener(self, callback):
        self.listeners.remove(callback)

    def forward_input(self, value):
        for callback in tuple(self.listeners):
            callback(value)

    def connect_to(self, unused):
        raise AssertionError("The diagnostic must never change a native map")

    def release_parameter(self):
        raise AssertionError("The diagnostic must never release a native map")


class SaturatorProbeTest(unittest.TestCase):
    def setUp(self):
        self.drive = ObservedParameter("Drive")
        self.output = ObservedParameter("Output", -4.0)
        self.owner = types.SimpleNamespace(name="Renamed device", class_name="Saturator",
                                           parameters=(self.drive, self.output))
        self.control = ObservedControl(self.drive)
        self.second_control = ObservedControl(self.drive)
        self.entry = {"device": 6, "parameter": "Drive"}
        self.component = type("ConfiguredMixingAssignmentsComponent", (), {})()
        self.component._assignments = {"fader_7": self.entry, "encoder_2": self.entry,
                                       "encoder_3": {"device": 6, "parameter": "Output"}}
        self.component._controls = {"fader_7": self.control, "encoder_2": self.second_control}
        self.component._active = True
        self.component._shift_pressed = self.component._locked = False
        self.component._resolver = types.SimpleNamespace(
            resolve=lambda entry: self.drive if entry["parameter"] == "Drive" else self.output,
            owner=lambda unused: self.owner, track=types.SimpleNamespace(name="Test"))
        self.probe = PROBE.SaturatorInputProbe.__new__(PROBE.SaturatorInputProbe)
        self.probe._probe_started = 0.0
        self.probe._sequence = self.probe._probe_tick = self.probe._event_count = 0
        self.probe._probe_scripts = (types.SimpleNamespace(
            component_map={"Fixed_Assignments": self.component}),)
        self.probe._bindings = []
        self.probe._last_status = None
        self.probe._closed = False
        self.records = []
        self.probe.log_message = lambda message: self.records.append(
            json.loads(message.removeprefix(PROBE.PREFIX)))
        self.probe._refresh_bindings()
        self.addCleanup(self.cleanup_bindings)

    def cleanup_bindings(self):
        for binding in self.probe._bindings:
            binding.disconnect()

    def test_duplicate_drive_assignments_share_observer_and_preserve_native_maps(self):
        self.assertEqual(len(self.probe._bindings), 1)
        self.assertEqual(len(self.drive.listeners), 1)
        self.assertEqual(len(self.control.listeners), 1)
        self.assertEqual(len(self.second_control.listeners), 1)
        self.probe._refresh_bindings()
        self.assertEqual(len(self.drive.listeners), 1)
        self.assertIs(self.control.mapped_parameter, self.drive)
        self.assertIs(self.second_control.mapped_parameter, self.drive)
        self.assertEqual(self.output.value, -4.0)

    def test_other_v3_surfaces_can_raise_key_error_from_component_map_get(self):
        class ComponentMap:
            def get(self, name):
                raise KeyError(name)

        unrelated = types.SimpleNamespace(component_map=ComponentMap())
        self.probe._probe_scripts = (unrelated,) + self.probe._probe_scripts
        self.probe._refresh_bindings()
        self.assertEqual(len(self.probe._bindings), 1)
        self.assertEqual(len(self.drive.listeners), 1)

    def test_inspecting_lazy_v3_map_never_constructs_an_unrelated_component(self):
        class LazyComponentMap(dict):
            def get(self, name):
                raise AssertionError("ComponentMap.get can instantiate a component")

        unrelated = types.SimpleNamespace(component_map=LazyComponentMap(
            Fixed_Assignments=lambda: object()))
        self.probe._probe_scripts = (unrelated,) + self.probe._probe_scripts
        self.probe._refresh_bindings()
        self.assertEqual(len(self.probe._bindings), 1)
        self.assertEqual(len(self.drive.listeners), 1)

    def test_actual_event_order_is_retained_in_both_directions_without_value_writes(self):
        for native_first in (True, False):
            with self.subTest(native_first=native_first):
                self.records.clear()
                if native_first:
                    self.drive.native_change(6.0)
                    self.control.forward_input(74)
                else:
                    self.control.forward_input(75)
                    self.drive.native_change(9.0)
                self.probe._tick()
                expected = ["drive_value", "control_input"] if native_first else ["control_input", "drive_value"]
                self.assertEqual([record["event"] for record in self.records], expected + ["task_boundary"])
                self.assertEqual(self.records[-1]["input_and_value_events"], 2)
                self.assertEqual(self.output.value, -4.0)

    def test_takeover_wait_and_mouse_change_remain_distinguishable_in_log(self):
        self.records.clear()
        self.control.forward_input(20)
        self.probe._tick()
        self.assertEqual([record["event"] for record in self.records], ["control_input", "task_boundary"])
        self.assertEqual(self.records[0]["drive"]["value"], 0.0)
        self.records.clear()
        self.drive.native_change(12.0)
        self.probe._tick()
        self.assertEqual([record["event"] for record in self.records], ["drive_value", "task_boundary"])
        self.assertEqual(self.records[0]["previous"], 0.0)

    def test_reassignment_removes_observers_from_old_controls_and_parameter(self):
        self.component._assignments = {}
        self.probe._refresh_bindings()
        self.assertEqual(self.drive.listeners, [])
        self.assertEqual(self.control.listeners, [])
        self.assertEqual(self.second_control.listeners, [])
        count = len(self.records)
        self.drive.native_change(15.0)
        self.control.forward_input(90)
        self.assertEqual(len(self.records), count)
        self.assertIs(self.control.mapped_parameter, self.drive)


if __name__ == "__main__":
    unittest.main()
