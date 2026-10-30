"""Configured Mixing must share the native mapping, preview and lock contracts."""

import ast
import types
import unittest
from unittest.mock import patch

import test_mixing as fixtures
from test_encoder_touch_preview import TouchPreviewChecks
from test_initial_assignment_display import HardwareDisplay, InitialDisplayChecks
from test_instrument_keyboard_navigation import surface_class
from test_mixing_colored_encoder import COLORED, FakeDevice as LedDevice, FakeParameter as LedParameter
from test_shift_preview import NativeMappedControl, ParameterPreviewChecks, display_lines

from Launch_Control_XL_3_Mixing import mixing_config
from Launch_Control_XL_3_Mixing.mixing_assignments import ConfiguredMixingAssignmentsComponent
from Launch_Control_XL_3_Mixing.mixing_targets import CONTROL_NAMES, validate_assignments


class ObservableDevice(fixtures.CountingDevice):
    def __init__(self, number=1):
        self.parameter_listeners = []
        super().__init__(number)

    def add_parameters_listener(self, callback):
        self.parameter_listeners.append(callback)

    def remove_parameters_listener(self, callback):
        self.parameter_listeners.remove(callback)

    def replace_parameters(self, parameters):
        self.parameters = parameters
        for parameter in parameters:
            parameter.canonical_parent = self
        for callback in tuple(self.parameter_listeners):
            callback()


class ObservableView:
    def __init__(self, track):
        self._track = track
        self.listeners = []

    @property
    def selected_track(self):
        return self._track

    @selected_track.setter
    def selected_track(self, track):
        self._track = track
        for callback in tuple(self.listeners):
            callback()

    def add_selected_track_listener(self, callback):
        self.listeners.append(callback)

    def remove_selected_track_listener(self, callback):
        self.listeners.remove(callback)


class ObservableTrack(fixtures.FakeTrack):
    def __init__(self, *a, **k):
        self.device_listeners = []
        super().__init__(*a, **k)

    @property
    def devices(self):
        return self._devices

    @devices.setter
    def devices(self, devices):
        self._devices = tuple(devices)
        for callback in tuple(self.device_listeners):
            callback()

    def add_devices_listener(self, callback):
        self.device_listeners.append(callback)

    def remove_devices_listener(self, callback):
        self.device_listeners.remove(callback)


def setup_configured(test, assignments=None):
    test.device = ObservableDevice()
    test.selected = ObservableTrack("Selected", devices=(test.device,), is_foldable=True)
    test.song = fixtures.FakeSong((test.selected,))
    test.song.view = ObservableView(test.selected)
    test.component = ConfiguredMixingAssignmentsComponent(assignments=assignments or {
        "encoder_1": {"device": 1, "parameter": "D1 P1"},
        "fader_1": {"device": 1, "parameter": "D1 P2"},
    })
    test.component.song = test.song
    test.addCleanup(test.component.disconnect)


def replace_target(test):
    device = ObservableDevice()
    device.name = "Replacement"
    test.song.view.selected_track = ObservableTrack("Replacement", devices=(device,))
    return device.parameters[1]


class MixingConfigurationTest(unittest.TestCase):
    def test_shipped_configuration_has_32_explicit_empty_slots(self):
        self.assertEqual(mixing_config.MIXING_IMPLEMENTATION, "configured")
        self.assertEqual(set(mixing_config.MIXING_ASSIGNMENTS), set(CONTROL_NAMES))
        self.assertTrue(all(value is None for value in mixing_config.MIXING_ASSIGNMENTS.values()))

    def test_surface_selects_configured_or_legacy_without_changing_router_contract(self):
        source = ast.parse((fixtures.PACKAGE_ROOT / "__init__.py").read_text())
        specification = next(node for node in source.body
                             if isinstance(node, ast.ClassDef) and node.name == "Specification")
        mapping = next(node.value for node in specification.body if isinstance(node, ast.Assign)
                       and node.targets[0].id == "component_map")
        namespace = {
            "ControlRouterComponent": fixtures.CONTROL_ROUTER.ControlRouterComponent,
            "FixedAssignmentsComponent": fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent,
            "ConfiguredMixingAssignmentsComponent": ConfiguredMixingAssignmentsComponent,
            "InstrumentAssignmentsComponent": fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent,
            "LocatorNavigationComponent": object, "ModeManagerComponent": object,
            "TrackButtonsComponent": object, "TransportComponent": object,
        }
        for setting, expected in (("configured", ConfiguredMixingAssignmentsComponent),
                                  ("legacy", fixtures.FIXED_ASSIGNMENTS.FixedAssignmentsComponent)):
            with self.subTest(setting=setting):
                namespace["MIXING_IMPLEMENTATION"] = setting
                components = eval(compile(ast.Expression(mapping), "specification", "eval"), namespace)
                self.assertIs(components["Fixed_Assignments"], expected)
                self.assertIs(components["Instrument_Assignments"],
                              fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent)

    def test_invalid_entries_are_isolated_and_logged(self):
        bad_entries = (
            "Attack", {}, {"device": 0, "parameter": "Attack"},
            {"device": True, "parameter": "Attack"}, {"device": 1, "parameter": ""},
            {"device": 1, "parameter": "Attack", "occurrence": 0},
            {"device": 1, "parameter": "Attack", "occurrence": 1.5},
            {"device": 1, "parameter": "Attack", "mixer": "pan"},
            {"mixer": "send"}, {"mixer": "send", "send": -1}, {"mixer": "cue"},
            {"mixer": "volume", "send": 1}, {"mixer": "pan", "directional_on_off": 1},
        )
        for entry in bad_entries:
            with self.subTest(entry=entry), self.assertLogs(level="WARNING"):
                result = validate_assignments({"encoder_1": entry, "fader_8": {"mixer": "volume"}})
                self.assertIsNone(result["encoder_1"])
                self.assertEqual(result["fader_8"], {"mixer": "volume"})
        for option in (True, False):
            with self.assertLogs(level="WARNING"):
                result = validate_assignments({"fader_1": {
                    "device": 1, "parameter": "Device On", "directional_on_off": option}})
            self.assertIsNone(result["fader_1"])
        with self.assertLogs(level="WARNING"):
            self.assertEqual(validate_assignments(None), dict.fromkeys(CONTROL_NAMES))
        with self.assertLogs(level="WARNING"):
            result = validate_assignments({"encoder_25": {"mixer": "volume"}})
        self.assertTrue(all(entry is None for entry in result.values()))


class ConfiguredAssignmentsTest(unittest.TestCase):
    def setUp(self):
        setup_configured(self)

    def bind(self, name):
        control = NativeMappedControl(relative=name.startswith("encoder_"))
        display = HardwareDisplay()
        getattr(self.component, "set_{}_display".format(name))(display)
        getattr(self.component, "set_{}".format(name))(control)
        return control, display

    def configure(self, assignments):
        self.component.disconnect()
        self.component = ConfiguredMixingAssignmentsComponent(assignments=assignments)
        self.component.song = self.song
        self.addCleanup(self.component.disconnect)

    def test_every_control_can_target_arbitrary_named_parameters_and_cache_is_shared(self):
        parameters = tuple(fixtures.FakeParameter("P{}".format(i)) for i in range(32))
        self.device.replace_parameters(parameters)
        self.configure({name: {"device": 2, "parameter": parameters[i].name}
                        for i, name in enumerate(CONTROL_NAMES)})
        self.selected.devices = (fixtures.FakeDevice(8), self.device)
        self.device.parameter_read_count = 0
        controls = [self.bind(name)[0] for name in CONTROL_NAMES]
        self.assertEqual(self.device.parameter_read_count, 1)
        for i, control in enumerate(controls):
            self.assertIs(control.mapped_parameter, parameters[i])
        counts = [len(control.connected) for control in controls]
        for _ in range(4):
            self.component._update_assignments()
        self.assertEqual(self.device.parameter_read_count, 1)
        self.assertEqual([len(control.connected) for control in controls], counts)

    def test_exact_names_duplicate_occurrence_and_device_on_use_raw_parameters(self):
        first, second = fixtures.FakeParameter("Gain"), fixtures.FakeParameter("Gain")
        self.device.name = "Wavetable"  # An Instrument custom order must not affect Mixing.
        self.device.replace_parameters((self.device.parameters[0], first, second,
                                        fixtures.FakeParameter("Attack Time")))
        self.configure({
            "encoder_1": {"device": 1, "parameter": "Gain"},
            "encoder_2": {"device": 1, "parameter": "Gain", "occurrence": 2},
            "encoder_3": {"device": 1, "parameter": "gain"},
            "encoder_4": {"device": 1, "parameter": "Attack"},
            "encoder_5": {"device": 1, "parameter": "Gain", "occurrence": 3},
            "fader_1": {"device": 1, "parameter": "Device On"},
        })
        for number, expected in ((1, first), (2, second), (3, None), (4, None), (5, None)):
            control, _ = self.bind("encoder_{}".format(number))
            self.assertIs(control.mapped_parameter, expected)
        control, _ = self.bind("fader_1")
        self.assertIs(control.mapped_parameter, self.device.parameters[0])

    def test_subject_without_structure_notifications_reads_once_per_device_per_update(self):
        device = fixtures.CountingDevice(1)
        self.selected.devices = (device,)
        self.bind("encoder_1")
        self.bind("fader_1")
        device.parameter_read_count = 0
        replacement = fixtures.FakeParameter("D1 P1", parent=device)
        device.parameters = (replacement,)
        self.component._update_assignments()
        self.assertEqual(device.parameter_read_count, 1)
        self.assertIs(self.component._connected_parameters["encoder_1"], replacement)
        self.assertNotIn("fader_1", self.component._connected_parameters)

    def test_volume_pan_and_sends_follow_selected_track_and_missing_sends_are_empty(self):
        self.configure({"fader_8": {"mixer": "volume"}, "encoder_24": {"mixer": "pan"},
                        "encoder_16": {"mixer": "send", "send": 2}})
        controls = {name: self.bind(name) for name in ("fader_8", "encoder_24", "encoder_16")}
        for track in (self.selected, self.song.master_track):
            self.song.view.selected_track = track
            for name, attribute in (("fader_8", "volume"), ("encoder_24", "panning")):
                control, display = controls[name]
                self.assertIs(control.mapped_parameter, getattr(track.mixer_device, attribute))
                self.assertEqual(display.local_shift_turn()[0], track.name)
            self.assertIs(controls["encoder_16"][0].mapped_parameter, track.mixer_device.sends[1])
        self.song.master_track.mixer_device.sends = ()
        self.component._update_assignments()
        self.assertIsNone(controls["encoder_16"][0].mapped_parameter)
        self.assertEqual(controls["encoder_16"][1].local_shift_turn()[1], "Unassigned")

    def test_track_and_device_notifications_replace_native_map_before_the_next_input(self):
        control, _ = self.bind("encoder_1")
        original = control.mapped_parameter
        other = ObservableDevice()
        self.song.view.selected_track = ObservableTrack("Other", devices=(other,))
        self.assertIs(control.mapped_parameter, other.parameters[1])
        control.receive(65)
        self.assertEqual(original.value, 0.0)
        self.assertGreater(other.parameters[1].value, 0.0)
        self.assertEqual(self.device.parameter_listeners, [])
        replacement = ObservableDevice()  # Same count/name/class; different Live object.
        self.song.view.selected_track.devices = (replacement,)
        self.assertIs(control.mapped_parameter, replacement.parameters[1])
        self.assertEqual(other.parameter_listeners, [])
        self.song.view.selected_track.devices = ()
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(replacement.parameter_listeners, [])

    def test_reorder_and_configure_change_rebind_even_with_the_same_names_and_counts(self):
        control, _ = self.bind("encoder_1")
        other = ObservableDevice()
        self.selected.devices = (self.device, other)
        self.selected.devices = (other, self.device)
        self.assertIs(control.mapped_parameter, other.parameters[1])
        replacement = fixtures.FakeParameter("D1 P1")
        other.replace_parameters((other.parameters[0], replacement))
        self.assertIs(control.mapped_parameter, replacement)
        replacement.name = "Renamed"
        self.component._update_assignments()
        self.assertIsNone(control.mapped_parameter)

    def test_empty_selected_track_does_not_search_loopcloud_master_or_inside_a_rack(self):
        self.song.master_track.devices = (ObservableDevice(),)
        self.song.tracks += (ObservableTrack("Loopcloud", devices=(ObservableDevice(),)),)
        rack = ObservableDevice()
        rack.replace_parameters((fixtures.FakeParameter("Device On"),))
        rack.chains = (fixtures.FakeTrack("Inside", devices=(self.device,)),)
        self.selected.devices = (rack,)
        control, display = self.bind("encoder_1")
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(display.local_shift_turn(), ("Encoder 1", "Unassigned", ""))

    def test_directional_on_off_is_opt_in_on_any_encoder_and_guarded_by_shift_and_lock(self):
        self.configure({"encoder_24": {"device": 1, "parameter": "Device On",
                                       "directional_on_off": True},
                        "encoder_2": {"device": 1, "parameter": "Device On",
                                      "directional_on_off": False}})
        control, display = self.bind("encoder_24")
        ordinary, _ = self.bind("encoder_2")
        parameter = ordinary.mapped_parameter
        parameter.min, parameter.max = -2.0, 3.0
        self.component._update_assignments()
        self.assertIsNone(control.mapped_parameter)
        self.assertIs(control.manual_led_parameter, parameter)
        for value, expected in ((63, -2.0), (65, 3.0), (64, 3.0), (0, -2.0), (127, 3.0)):
            control.receive(value)
            self.assertEqual(parameter.value, expected)
        for setter in (self.component.set_shift_pressed, self.component.set_locked):
            parameter.value = 0.25
            setter(True)
            for value in (63, 65, 127):
                control.receive(value)
            self.assertEqual(parameter.value, 0.25)
            setter(False)
            self.assertEqual(parameter.value, 0.25)
        self.assertEqual(control.native_updates, [])
        self.assertEqual(display.local_shift_turn()[1], "Device On")
        ordinary.receive(65)
        self.assertGreater(parameter.value, 0.25)
        self.assertLess(parameter.value, 3.0)

    def test_disconnect_and_inactive_mode_drop_observers_without_releasing_another_mapping(self):
        control, _ = self.bind("encoder_1")
        self.component.set_active(False)
        self.assertEqual(self.song.view.listeners, [])
        self.assertEqual(self.selected.device_listeners, [])
        self.assertEqual(self.device.parameter_listeners, [])
        other = fixtures.FakeParameter("Other mode")
        control.connect_to(other)
        self.component.set_shift_pressed(True)
        self.component.set_locked(True)
        self.component._update_assignments(force=True)
        self.component.disconnect()
        self.assertIs(control.mapped_parameter, other)
        self.assertEqual(control.listeners, [])

    def test_fader_without_encoder_led_methods_is_released_on_shift_and_disconnect(self):
        class Fader(NativeMappedControl):
            def clear_manual_led_parameter(self, *a):
                raise AttributeError("A real fader has no encoder LED API")

        control = Fader(relative=False)
        self.component.set_fader_1(control)
        self.component.set_shift_pressed(True)
        self.assertIsNone(control.mapped_parameter)
        self.component.set_shift_pressed(False)
        self.assertIsNotNone(control.mapped_parameter)
        self.component.disconnect()
        self.assertIsNone(control.mapped_parameter)


class ConfiguredShiftPreviewTest(ParameterPreviewChecks, unittest.TestCase):
    encoder_name = "encoder_1"
    fader_name = "fader_1"

    def setUp(self):
        setup_configured(self)

    def expected_lines(self, name, parameter):
        return (parameter.canonical_parent.name, parameter.name, str(parameter))

    def replace_selected_track(self):
        return replace_target(self)


class ConfiguredTouchPreviewTest(TouchPreviewChecks, unittest.TestCase):
    target_key = "fixed_assignments"
    encoder_name = "encoder_1"

    def setUp(self):
        setup_configured(self)

    def expected_lines(self, parameter):
        return (parameter.canonical_parent.name, parameter.name, str(parameter))

    def replace_target(self):
        return replace_target(self)


class ConfiguredInitialDisplayTest(InitialDisplayChecks, unittest.TestCase):
    encoder_name = "encoder_1"
    header = "Device 1"

    def setUp(self):
        setup_configured(self)

    def replace_target(self):
        return replace_target(self)

    def test_unchanged_refresh_does_not_resend_prepared_text(self):
        _, display = self.bind()
        count = len(display.prepared_frames)
        for _ in range(3):
            self.component._update_assignments()
            self.component._update_assignments(force=True)
        self.assertEqual(len(display.prepared_frames), count)
        self.assert_background_only(display)


class ConfiguredModeLockTest(unittest.TestCase):
    def test_surface_switch_lock_and_reidentification_protect_all_32_controls(self):
        setup_configured(self, {name: {"device": 1, "parameter": "D1 P1"}
                                for name in CONTROL_NAMES})
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        instrument = fixtures.INSTRUMENT_ASSIGNMENTS.InstrumentAssignmentsComponent()
        instrument.song = self.song
        self.addCleanup(router.disconnect)
        self.addCleanup(instrument.disconnect)
        now = [0.0]
        manager = fixtures.MODE_MANAGER.ModeManagerComponent(clock=lambda: now[0])
        pages = (fixtures.FakeButton(106), fixtures.FakeButton(107))
        manager.set_mixing_button(pages[0])
        manager.set_instrument_button(pages[1])
        self.addCleanup(manager.disconnect)
        surface_type = surface_class()
        surface = surface_type.__new__(surface_type)
        surface.component_map = {"Control_Router": router, "Mode_Manager": manager,
                                 "Fixed_Assignments": self.component, "Instrument_Assignments": instrument}
        surface.sent_midi = []
        surface._tasks = self.component._tasks
        with patch.object(instrument, "start_keyboard_navigation"):
            surface._setup_components()
        controls = []
        for name in CONTROL_NAMES:
            control = NativeMappedControl(relative=name.startswith("encoder_"))
            display = HardwareDisplay()
            getattr(router, "set_{}_display".format(name))(display)
            getattr(router, "set_{}".format(name))(control)
            controls.append((name, control, display))
        parameter = self.device.parameters[1]
        now[0] = 180.0
        manager.check_idle()
        self.assertTrue(manager.locked)
        for name, control, display in controls:
            self.assertIsNone(control.mapped_parameter)
            control.receive(65 if name.startswith("encoder_") else 127)
            self.assertEqual(display.local_shift_turn(), ("LOCKED", "", ""))
        self.assertEqual(parameter.value, 0.0)
        surface.on_identified(())
        self.assertTrue(all(display.local_shift_turn() == ("LOCKED", "", "")
                            for _, _, display in controls))
        pages[1].receive(127)
        self.assertFalse(manager.locked)
        self.assertFalse(self.component._active)
        self.assertTrue(instrument._active)
        self.assertEqual(parameter.value, 0.0)
        pages[0].receive(127)
        self.assertTrue(self.component._active)
        self.assertFalse(instrument._active)
        self.assertTrue(all(control.mapped_parameter is parameter for _, control, _ in controls))


class ElementControl(COLORED.ColoredEncoderElement):
    """Use the actual colored encoder with a minimal native mapping adapter."""

    def __init__(self):
        super().__init__()
        self.listeners = []

    def add_value_listener(self, callback):
        self.listeners.append(callback)

    def remove_value_listener(self, callback):
        self.listeners.remove(callback)

    def connect_to(self, parameter):
        self.mapped_object = parameter
        self._update_parameter_listeners()

    def release_parameter(self):
        self.mapped_object = None
        self._update_parameter_listeners()


class ConfiguredEncoderFeedbackTest(unittest.TestCase):
    def setUp(self):
        setup_configured(self)
        self.router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        self.router.set_target_components(fixed_assignments=self.component)
        self.addCleanup(self.router.disconnect)
        self.theme = patch.object(COLORED, "Theme", types.SimpleNamespace(OFF=(0, 0, 0)))
        self.theme.start()
        self.addCleanup(self.theme.stop)
        self.colors = patch.object(COLORED, "encoder_rgb_for_parameter",
                                   lambda parameter, is_device_parameter=False:
                                   (round(parameter.value * 100), 20, 0))
        self.colors.start()
        self.addCleanup(self.colors.stop)

    def bind(self, name):
        encoder = ElementControl()
        getattr(self.router, "set_{}".format(name))(encoder)
        return encoder

    def test_common_value_led_survives_shift_external_changes_lock_and_unassignment(self):
        encoder = self.bind("encoder_1")
        parameter = encoder.mapped_object
        shift = fixtures.FakeButton()
        self.router.set_shift_button(shift)
        shift.receive(127)
        self.assertIsNone(encoder.mapped_object)
        parameter.value = 0.5
        self.component._update_assignments()
        self.assertEqual(encoder.sent_midi[-1][2], (50, 20, 0))
        self.router.set_locked(True)
        self.assertEqual(encoder.sent_midi[-1][2], (2, 1, 0))
        parameter.value = 0.8
        self.component._update_assignments()
        self.assertEqual(encoder.sent_midi[-1][2], (4, 1, 0))
        self.router.set_locked(False)
        self.assertEqual(encoder.sent_midi[-1][2], (80, 20, 0))
        shift.receive(0)
        self.assertIs(encoder.mapped_object, parameter)
        self.selected.devices = ()
        self.assertIsNone(encoder.mapped_object)
        self.assertEqual(encoder.sent_midi[-1][2], (0, 0, 0))

    def test_saturn_common_element_behavior_remains_enabled_with_configured_mapping(self):
        device = LedDevice()
        parameter = LedParameter(parent=device, value=2.0)
        device.parameters = (parameter,)
        self.component.disconnect()
        self.component = ConfiguredMixingAssignmentsComponent(assignments={
            "encoder_22": {"device": 1, "parameter": "Band 1 Style"}})
        self.component.song = self.song
        self.addCleanup(self.component.disconnect)
        self.router.set_target_components(fixed_assignments=self.component)
        self.selected.devices = (device,)
        encoder = self.bind("encoder_22")
        encoder.receive_value(65)
        self.assertEqual(parameter.value, 6.0)
        shift = fixtures.FakeButton()
        self.router.set_shift_button(shift)
        shift.receive(127)
        encoder.receive_value(65)
        self.assertEqual(parameter.value, 6.0)
        shift.receive(0)
        self.router.set_locked(True)
        encoder.receive_value(63)
        self.assertEqual(parameter.value, 6.0)

    def test_directional_device_on_uses_same_value_colors_at_any_encoder_number(self):
        self.component.disconnect()
        self.component = ConfiguredMixingAssignmentsComponent(assignments={
            name: {"device": 1, "parameter": "Device On", "directional_on_off": True}
            for name in ("encoder_2", "encoder_24")})
        self.component.song = self.song
        self.addCleanup(self.component.disconnect)
        self.router.set_target_components(fixed_assignments=self.component)
        first, last = self.bind("encoder_2"), self.bind("encoder_24")
        self.assertIsNone(first.mapped_object)
        self.assertIsNone(last.mapped_object)
        self.component._on_parameter_control_value("encoder_24", 63)
        self.component._update_assignments()
        self.assertEqual(first.sent_midi[-1][2], (0, 20, 0))
        self.assertEqual(last.sent_midi[-1][2], (0, 20, 0))
        self.component._on_parameter_control_value("encoder_2", 65)
        self.component._update_assignments()
        self.assertEqual(first.sent_midi[-1][2], (100, 20, 0))
        self.assertEqual(last.sent_midi[-1][2], (100, 20, 0))


if __name__ == "__main__":
    unittest.main()
