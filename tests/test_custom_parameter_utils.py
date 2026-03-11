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


def _install_device_stubs():
    ableton = sys.modules.setdefault("ableton", types.ModuleType("ableton"))
    ableton.__path__ = getattr(ableton, "__path__", [])

    ableton_v3 = sys.modules.setdefault("ableton.v3", types.ModuleType("ableton.v3"))
    ableton_v3.__path__ = getattr(ableton_v3, "__path__", [])

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface", types.ModuleType("ableton.v3.control_surface")
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    components = types.ModuleType("ableton.v3.control_surface.components")

    class DeviceBankNavigationComponent(object):
        pass

    class DeviceComponent(object):
        pass

    components.DeviceBankNavigationComponent = DeviceBankNavigationComponent
    components.DeviceComponent = DeviceComponent
    sys.modules["ableton.v3.control_surface.components"] = components


def _install_device_toggle_stubs():
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

    class Component(object):
        pass

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
        WHITE_HALF = _Color(1)

    colors.Rgb = Rgb
    sys.modules["Launch_Control_XL_3_Custom.colors"] = colors


UTILS = _load_module("Launch_Control_XL_3_Custom.custom_parameter_utils", "custom_parameter_utils.py")
_load_module("Launch_Control_XL_3_Custom.custom_parameter_order", "custom_parameter_order.py")
_install_device_stubs()
DEVICE = _load_module("Launch_Control_XL_3_Custom.device", "device.py")
_install_device_toggle_stubs()
DEVICE_TOGGLE = _load_module("Launch_Control_XL_3_Custom.device_toggle", "device_toggle.py")


class FakeDevice(object):
    def __init__(self, name, parameters, class_name=None, class_display_name=None):
        self.name = name
        self.parameters = tuple(parameters)
        self.class_name = class_name or name
        self.class_display_name = class_display_name or name


class FakeParameter(object):
    def __init__(self, name):
        self.name = name


class FakeParameterInfo(object):
    def __init__(self, parameter, name):
        self.parameter = parameter
        self.name = name


class FakeDelegate(object):
    def device_bank_count(self, device, *a, **k):
        parameters = tuple(getattr(device, "parameters", ()))
        return max(1, (len(parameters) + 7) // 8)

    def device_bank_names(self, device, *a, **k):
        return ("Bank 1", "Bank 2", "Bank 3", "Bank 4")

    def device_bank_parameters(self, device, bank_index, *a, **k):
        parameters = tuple(getattr(device, "parameters", ()))
        start = bank_index * 8
        end = start + 8
        return tuple(parameters[start:end])

    def device_bank_definition(self, device, *a, **k):
        return "delegate-definition"


class CustomParameterUtilsTest(unittest.TestCase):
    def setUp(self):
        self.parameters = (
            FakeParameter("Attack"),
            FakeParameter("Decay"),
            FakeParameter("Sustain"),
            FakeParameter("Release"),
            FakeParameter("Attack"),
            FakeParameter("Decay"),
            FakeParameter("Sustain"),
            FakeParameter("Release"),
        )

    def _parameter_name(self, parameter):
        return getattr(parameter, "name", "") or ""

    def _is_parameter(self, parameter):
        return parameter is not None and self._parameter_name(parameter) not in ("", UTILS.DEVICE_ON_PARAMETER_NAME)

    def test_duplicate_names_are_consumed_in_order(self):
        ordered, missing = UTILS.order_named_items(
            self.parameters,
            ("Attack", "Decay", "Sustain", "Release", "Attack", "Decay", "Sustain", "Release"),
            append_rest=False,
            get_name=self._parameter_name,
            is_valid_item=self._is_parameter,
            keep_missing_slots=True,
        )
        self.assertEqual(ordered, self.parameters)
        self.assertEqual(missing, ())

    def test_occurrence_selects_nth_duplicate_and_out_of_range_leaves_empty_slot(self):
        ordered, missing = UTILS.order_named_items(
            self.parameters,
            (
                {"Attack": {"occurrence": 2}},
                {"Decay": {"occurrence": 2}},
                {"Release": {"occurrence": 3}},
            ),
            append_rest=False,
            get_name=self._parameter_name,
            is_valid_item=self._is_parameter,
            keep_missing_slots=True,
        )
        self.assertIs(ordered[0], self.parameters[4])
        self.assertIs(ordered[1], self.parameters[5])
        self.assertIsNone(ordered[2])
        self.assertEqual(missing, ("Release (occurrence=3)",))

    def test_append_rest_does_not_reappend_consumed_duplicates(self):
        ordered, _ = UTILS.order_named_items(
            self.parameters,
            ("Attack", "Attack"),
            append_rest=True,
            get_name=self._parameter_name,
            is_valid_item=self._is_parameter,
            keep_missing_slots=True,
        )
        self.assertEqual(len(ordered), len(self.parameters))
        self.assertEqual(sum(1 for parameter in ordered if parameter.name == "Attack"), 2)
        self.assertIs(ordered[0], self.parameters[0])
        self.assertIs(ordered[1], self.parameters[4])

    def test_mode_switch_indexes_ignore_occurrence_only_entries(self):
        raw_mapping = {
            "Test Device": (
                {"Attack": {"occurrence": 2}},
                {"Decay": {"mode_count": 7}},
                {"Release": {"mode_count": 5, "occurrence": 2}},
            )
        }
        rule_index = UTILS.build_mode_switch_rules_index(raw_mapping)
        global_index = UTILS.build_global_parameter_rule_index(raw_mapping)
        self.assertEqual(set(rule_index["test device"].keys()), {"Decay", "Release"})
        self.assertNotIn(UTILS.compact_name("Attack"), global_index)
        self.assertEqual(global_index[UTILS.compact_name("Decay")]["mode_count"], 7)

    def test_device_and_toggle_use_the_same_ordering_logic(self):
        custom_order = (
            "Attack",
            {"Attack": {"occurrence": 2}},
            "Decay",
            {"Release": {"occurrence": 2}},
            {"Release": {"occurrence": 3}},
        )
        device = FakeDevice("Diva", self.parameters)

        banking_info = DEVICE._CustomParameterBankingInfo(delegate=object(), bank_size=8)
        banking_info._resolve_custom_order = lambda _: custom_order
        banking_info._get_base_flat_parameters = lambda _: self.parameters
        bank_order = banking_info._build_custom_flat_parameters(device)

        class ToggleHarness(object):
            def _resolve_custom_order(self, _selected_device):
                return custom_order

        toggle_order = DEVICE_TOGGLE.DeviceToggleComponent._ordered_parameters(ToggleHarness(), device)

        self.assertEqual(bank_order, toggle_order)
        self.assertIs(bank_order[0], self.parameters[0])
        self.assertIs(bank_order[1], self.parameters[4])
        self.assertIs(bank_order[2], self.parameters[1])
        self.assertIs(bank_order[3], self.parameters[7])
        self.assertIsNone(bank_order[4])

    def test_duplicate_name_devices_use_raw_parameter_banks(self):
        duplicate_parameters = self.parameters + (
            FakeParameter("Cutoff"),
            FakeParameter("Resonance"),
        )
        device = FakeDevice("Diva", duplicate_parameters)
        banking_info = DEVICE._CustomParameterBankingInfo(delegate=FakeDelegate(), bank_size=8)

        self.assertTrue(banking_info.uses_duplicate_name_banking(device))
        self.assertIsNone(banking_info.device_bank_definition(device))
        self.assertEqual(banking_info.device_bank_count(device), 2)
        self.assertEqual(banking_info.device_bank_parameters(device, 0), duplicate_parameters[:8])
        self.assertEqual(
            banking_info.device_bank_parameters(device, 1),
            duplicate_parameters[8:] + (None, None, None, None, None, None),
        )

    def test_duplicate_parameter_info_names_are_uniquified(self):
        infos = (
            FakeParameterInfo(self.parameters[0], "Attack"),
            FakeParameterInfo(self.parameters[4], "Attack"),
            FakeParameterInfo(self.parameters[1], "Decay"),
            FakeParameterInfo(self.parameters[5], "Decay"),
        )

        class InfoHarness(object):
            _parameter_info_base_name = DEVICE.DeviceComponent._parameter_info_base_name
            _uniquify_parameter_infos = DEVICE.DeviceComponent._uniquify_parameter_infos

            def _extract_parameter_from_info(self, info):
                return getattr(info, "parameter", None)

            def _get_parameter_name(self, parameter):
                return getattr(parameter, "name", "") or ""

            def _get_parameter_name_for_info(self, info):
                return self._get_parameter_name(self._extract_parameter_from_info(info))

            def _create_parameter_info(self, parameter, name):
                return FakeParameterInfo(parameter, name)

        uniquified = InfoHarness()._uniquify_parameter_infos(infos)
        self.assertEqual([info.name for info in uniquified], ["Attack", "Attack [2]", "Decay", "Decay [2]"])
        self.assertIs(uniquified[1].parameter, self.parameters[4])


if __name__ == "__main__":
    unittest.main()
