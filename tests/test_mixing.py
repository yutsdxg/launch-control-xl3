import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = WORKSPACE_ROOT / "Launch_Control_XL_3_Mixing"

SATURN_STYLE_ITEMS = (
    "Subtle Tube",
    "Clean Tube",
    "Warm Tube",
    "Broken Tube",
    "Subtle Tape",
    "Clean Tape",
    "Warm Tape",
    "Old Tape",
    "American Tweed Amp",
    "American Plexi Amp",
    "British Rock Amp",
    "British Pop Amp",
    "Smooth",
    "Crunchy",
    "Lead",
    "Screaming",
    "Power",
    "Subtle Saturation",
    "Gentle Saturation",
    "Heavy Saturation",
    "Subtle Transformer",
    "Gentle Transformer",
    "Warm Transformer",
    "Smudge",
    "Breakdown",
    "Foldback",
    "Rectify",
    "Destroy",
)


def _ensure_package():
    package = sys.modules.get("Launch_Control_XL_3_Mixing")
    if package is None:
        package = types.ModuleType("Launch_Control_XL_3_Mixing")
        package.__path__ = [str(PACKAGE_ROOT)]
        sys.modules["Launch_Control_XL_3_Mixing"] = package


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

    class Task:
        loop = staticmethod(lambda value: value)
        sequence = staticmethod(lambda *values: values)
        run = staticmethod(lambda callback, *args: (callback, args))
        delay = staticmethod(lambda value: value)

    base.task = Task
    sys.modules["ableton.v3.base"] = base

    control_surface = sys.modules.setdefault(
        "ableton.v3.control_surface",
        types.ModuleType("ableton.v3.control_surface"),
    )
    control_surface.__path__ = getattr(control_surface, "__path__", [])

    class Tasks:
        def add(self, value):
            return value

    class Slot:
        def __init__(self, subject, listener):
            self._subject = subject
            self._listener = listener

        def disconnect(self):
            self._subject.remove_value_listener(self._listener)

    class Component:
        def __init__(self, *a, **k):
            self.song = None
            self._tasks = Tasks()

        def register_slot(self, subject, listener, event_name):
            if event_name != "value":
                raise AssertionError(event_name)
            subject.add_value_listener(listener)
            return Slot(subject, listener)

        def disconnect(self):
            pass

    control_surface.Component = Component

    live = types.ModuleType("ableton.v3.live")
    live.liveobj_valid = lambda obj: obj is not None
    live.action = types.SimpleNamespace(selected=[])
    live.action.select = lambda track: live.action.selected.append(track)
    sys.modules["ableton.v3.live"] = live

    colors = types.ModuleType("Launch_Control_XL_3_Mixing.colors")

    class Theme:
        OFF = "off"
        DEVICE_ON = "device-on"
        DEVICE_OFF = "device-off"
        SOLO_ON = "solo-on"
        SOLO_MODIFIER_IDLE = "solo-idle"
        MUTE_MODIFIER_ON = "mute-on"
        MUTE_MODIFIER_IDLE = "mute-idle"

    colors.Theme = Theme
    colors.active_track_rgb = lambda rgb: ("active", rgb)
    colors.dim_track_rgb = lambda rgb: ("dim", rgb)
    colors.track_rgb = lambda track: track.rgb
    colors.encoder_rgb_for_parameter = lambda parameter, is_device_parameter=False: (
        "encoder",
        parameter.value,
        is_device_parameter,
    )
    colors.device_toggle_encoder_rgb = lambda encoder_number, is_on: (
        "device-toggle",
        encoder_number,
        is_on,
    )
    sys.modules["Launch_Control_XL_3_Mixing.colors"] = colors

    led = types.ModuleType("Launch_Control_XL_3_Mixing.led")

    class LedSender:
        def __init__(self, midi_sender=None):
            self.midi_sender = midi_sender
            self.last = {}

        def set_midi_sender(self, midi_sender):
            self.midi_sender = midi_sender

        def send_rgb(self, control, rgb, control_index=None, force=False):
            self.last[control] = rgb
            return True

        def forget(self, control, control_index=None):
            self.last.pop(control, None)

    led.LedSender = LedSender
    sys.modules["Launch_Control_XL_3_Mixing.led"] = led


_install_component_stubs()
TRACK_RESOLVER = _load_module("Launch_Control_XL_3_Mixing.track_resolver", "track_resolver.py")
FIXED_ASSIGNMENTS = _load_module("Launch_Control_XL_3_Mixing.fixed_assignments", "fixed_assignments.py")
TRACK_BUTTONS = _load_module("Launch_Control_XL_3_Mixing.track_buttons", "track_buttons.py")
MAPPINGS = _load_module("Launch_Control_XL_3_Mixing.mappings", "mappings.py")
MIXING_ACTION = TRACK_BUTTONS.action


class FakeButton:
    def __init__(self, identifier=0):
        self.identifier = identifier
        self.listeners = []

    def add_value_listener(self, listener):
        self.listeners.append(listener)

    def remove_value_listener(self, listener):
        self.listeners.remove(listener)

    def message_identifier(self):
        return self.identifier

    def receive(self, value):
        for listener in tuple(self.listeners):
            listener(value)


class FakeControl(FakeButton):
    def __init__(self, identifier=0):
        super().__init__(identifier)
        self.connected = []
        self.release_count = 0
        self.manual_led_parameter = None
        self.manual_led_clear_count = 0

    def connect_to(self, parameter):
        self.connected.append(parameter)

    def release_parameter(self):
        self.release_count += 1

    def set_manual_led_parameter(self, parameter):
        self.manual_led_parameter = parameter

    def clear_manual_led_parameter(self, parameter=None):
        if parameter is None or parameter is self.manual_led_parameter:
            self.manual_led_parameter = None
            self.manual_led_clear_count += 1


class FakeManualLedControl(FakeControl):
    def __init__(self, identifier=0):
        super().__init__(identifier=identifier)
        self.manual_led_rgb = None
        self.manual_led_rgb_force = None
        self.manual_led_rgb_clear_count = 0

    def set_manual_led_rgb(self, rgb, force=False):
        self.manual_led_rgb = rgb
        self.manual_led_rgb_force = force

    def clear_manual_led_rgb(self):
        self.manual_led_rgb = None
        self.manual_led_rgb_clear_count += 1


class FakeDisplayCommand:
    def __init__(self):
        self.sent = []

    def send_data(self, config, text_fields, show_immediately, trigger):
        self.sent.append((config, text_fields, show_immediately, trigger))


class FakeParameter:
    def __init__(
        self,
        name,
        value=0.0,
        minimum=0.0,
        maximum=1.0,
        enabled=True,
        parent=None,
        value_items=(),
    ):
        self.name = name
        self.value = value
        self.min = minimum
        self.max = maximum
        self.is_enabled = enabled
        self.canonical_parent = parent
        self.value_items = tuple(value_items)

    def __str__(self):
        return str(self.value)


class FakeDevice:
    def __init__(self, number, on=True):
        self.name = "Device {}".format(number)
        self.class_name = self.name
        self.class_display_name = self.name
        self.parameters = (
            FakeParameter("Device On", value=1.0 if on else 0.0),
            FakeParameter("D{} P1".format(number)),
            FakeParameter("D{} P2".format(number)),
            FakeParameter("D{} P3".format(number)),
            FakeParameter("D{} P4".format(number)),
        )
        for parameter in self.parameters:
            parameter.canonical_parent = self


class FakeMixer:
    def __init__(self, name):
        self.volume = FakeParameter("{} Volume".format(name))
        self.panning = FakeParameter("Track Panning", minimum=-1.0, maximum=1.0)
        self.sends = (
            FakeParameter("{} Send 1".format(name)),
            FakeParameter("{} Send 2".format(name)),
        )
        self.cue_volume = FakeParameter("Cue Volume")


class FakeTrack:
    def __init__(
        self,
        name,
        devices=(),
        is_foldable=False,
        is_grouped=False,
        group_track=None,
        color=0x336699,
    ):
        self.name = name
        self.devices = tuple(devices)
        self.mixer_device = FakeMixer(name)
        self.is_foldable = is_foldable
        self.is_grouped = is_grouped
        self.group_track = group_track
        self.color = color
        self.rgb = "{}-rgb".format(name)
        self.solo = False
        self.mute = False


class FakeView:
    def __init__(self, selected_track):
        self.selected_track = selected_track


class FakeSong:
    def __init__(self, tracks, selected_track=None):
        self.tracks = tuple(tracks)
        self.view = FakeView(selected_track or (tracks[0] if tracks else None))
        self.master_track = FakeTrack("Master")


def _track_layout():
    group_1 = FakeTrack("Group 1", is_foldable=True)
    child_1 = FakeTrack("G1 Child 1", is_grouped=True, group_track=group_1)
    nested_group = FakeTrack("Nested", is_foldable=True, is_grouped=True, group_track=group_1)
    group_2 = FakeTrack("Group 2", is_foldable=True)
    child_2 = FakeTrack("G2 Child 1", is_grouped=True, group_track=group_2)
    bass_group = FakeTrack("Bass", is_foldable=True, is_grouped=True, group_track=group_2)
    return group_1, child_1, nested_group, group_2, child_2, bass_group


class MixingMappingsTest(unittest.TestCase):
    def test_mapping_contains_only_planned_controls(self):
        mappings = MAPPINGS.create_mappings(None)

        self.assertEqual(mappings["Locator_Navigation"]["prev_locator_button"], "track_left_button")
        self.assertEqual(mappings["Locator_Navigation"]["next_locator_button"], "track_right_button")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_1"], "upper_encoders_raw[0]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_9"], "upper_encoders_raw[8]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_11"], "upper_encoders_raw[10]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_12"], "upper_encoders_raw[11]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_13"], "upper_encoders_raw[12]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_14"], "upper_encoders_raw[13]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_15"], "upper_encoders_raw[14]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_19"], "lower_encoders_raw[2]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_20"], "lower_encoders_raw[3]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_21"], "lower_encoders_raw[4]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_22"], "lower_encoders_raw[5]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_23"], "lower_encoders_raw[6]")
        self.assertEqual(mappings["Fixed_Assignments"]["fader_3"], "faders_raw[2]")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_1_display"], "upper_encoder_0_display_command")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_9_display"], "upper_encoder_8_display_command")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_11_display"], "upper_encoder_10_display_command")
        self.assertEqual(mappings["Fixed_Assignments"]["encoder_22_display"], "lower_encoder_5_display_command")
        self.assertEqual(mappings["Fixed_Assignments"]["fader_3_display"], "fader_2_display_command")
        self.assertNotIn("Encoder_Modes", mappings)
        self.assertNotIn("Mixer", mappings)

    def test_auto_load_is_not_enabled(self):
        source = (PACKAGE_ROOT / "__init__.py").read_text()
        self.assertNotIn("AUTO_LOAD", source)


class TrackResolverTest(unittest.TestCase):
    def test_top_level_groups_ignore_nested_groups_and_children_include_them(self):
        group_1, child_1, nested_group, group_2, child_2, bass_group = _track_layout()
        song = FakeSong((group_1, child_1, nested_group, group_2, child_2, bass_group))

        self.assertEqual(TRACK_RESOLVER.top_level_groups(song), (group_1, group_2))
        self.assertEqual(TRACK_RESOLVER.direct_group_children(song, group_1), (child_1, nested_group))

    def test_button_8_can_target_a_bass_group_track(self):
        layout = _track_layout()
        song = FakeSong(layout)

        self.assertIs(TRACK_RESOLVER.track_button_targets(song)[7], layout[-1])


class FixedAssignmentsTest(unittest.TestCase):
    def setUp(self):
        self.loopcloud = FakeTrack("Loopcloud", devices=(FakeDevice(1), FakeDevice(2)))
        self.selected = FakeTrack("Selected", devices=tuple(FakeDevice(index) for index in range(1, 10)))
        self.song = FakeSong((self.loopcloud, self.selected), selected_track=self.selected)
        self.component = FIXED_ASSIGNMENTS.FixedAssignmentsComponent()
        self.component.song = self.song

    def _display_lines(self, display):
        _, text_fields, _, _ = display.sent[-1]
        return tuple("".join(chr(value) for value in field) for field in text_fields)

    def test_fixed_parameter_numbers_and_named_track_assignment(self):
        controls = {}
        for name in (
            "encoder_1",
            "encoder_8",
            "encoder_9",
            "encoder_11",
            "encoder_12",
            "encoder_13",
            "encoder_14",
            "encoder_15",
            "encoder_16",
            "encoder_17",
            "encoder_19",
            "encoder_20",
            "encoder_21",
            "encoder_22",
            "encoder_23",
            "encoder_24",
        ):
            controls[name] = FakeControl()
            getattr(self.component, "set_{}".format(name))(controls[name])
        for number in (1, 3, 4, 5, 6, 7, 8):
            name = "fader_{}".format(number)
            controls[name] = FakeControl()
            getattr(self.component, "set_{}".format(name))(controls[name])

        self.assertIs(controls["encoder_1"].connected[-1], self.loopcloud.devices[1].parameters[3])
        self.assertIs(controls["encoder_8"].connected[-1], self.song.master_track.mixer_device.cue_volume)
        self.assertIs(controls["encoder_9"].connected[-1], self.loopcloud.devices[1].parameters[2])
        self.assertIs(controls["encoder_11"].connected[-1], self.selected.devices[3].parameters[3])
        self.assertIs(controls["encoder_12"].connected[-1], self.selected.devices[4].parameters[3])
        self.assertIs(controls["encoder_13"].connected[-1], self.selected.devices[5].parameters[3])
        self.assertIs(controls["encoder_14"].connected[-1], self.selected.devices[6].parameters[3])
        self.assertIs(controls["encoder_15"].connected[-1], self.selected.devices[8].parameters[3])
        self.assertIs(controls["encoder_16"].connected[-1], self.selected.mixer_device.sends[0])
        self.assertIs(controls["encoder_17"].connected[-1], self.loopcloud.devices[1].parameters[1])
        self.assertIs(controls["encoder_19"].connected[-1], self.selected.devices[3].parameters[2])
        self.assertIs(controls["encoder_20"].connected[-1], self.selected.devices[4].parameters[2])
        self.assertIs(controls["encoder_21"].connected[-1], self.selected.devices[5].parameters[2])
        self.assertIs(controls["encoder_22"].connected[-1], self.selected.devices[6].parameters[2])
        self.assertIs(controls["encoder_23"].connected[-1], self.selected.devices[8].parameters[2])
        self.assertIs(controls["fader_1"].connected[-1], self.loopcloud.mixer_device.volume)
        self.assertIs(controls["fader_3"].connected[-1], self.selected.devices[3].parameters[1])
        self.assertIs(controls["fader_7"].connected[-1], self.selected.devices[8].parameters[1])
        self.assertIs(controls["fader_8"].connected[-1], self.selected.mixer_device.volume)

    def test_custom_parameter_order_changes_device_parameter_numbering(self):
        device = self.selected.devices[3]
        device.name = "Custom Ordered 2"
        old_index = FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX
        old_append_rest = FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST
        try:
            FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = FIXED_ASSIGNMENTS.build_device_order_index(
                {
                    "Custom Ordered": (
                        "D4 P4",
                        "D4 P2",
                        "D4 P1",
                        "D4 P3",
                    )
                }
            )
            FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST = False
            control = FakeControl()

            self.component.set_encoder_11(control)

            self.assertIs(control.connected[-1], device.parameters[1])
        finally:
            FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = old_index
            FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST = old_append_rest

    def test_custom_parameter_order_supports_occurrence_and_skip_slots(self):
        device = self.selected.devices[3]
        device.name = "Duplicate Device"
        device.parameters = (
            device.parameters[0],
            FakeParameter("Repeated", parent=device),
            FakeParameter("Other", parent=device),
            FakeParameter("Repeated", parent=device),
        )
        old_index = FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX
        old_append_rest = FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST
        try:
            FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = FIXED_ASSIGNMENTS.build_device_order_index(
                {
                    "Duplicate Device": (
                        {"Repeated": {"occurrence": 2}},
                        "SKIP",
                        "Other",
                    )
                }
            )
            FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST = False
            first_slot = FakeControl()
            skipped_slot = FakeControl()
            third_slot = FakeControl()

            self.component.set_fader_3(first_slot)
            self.component.set_encoder_19(skipped_slot)
            self.component.set_encoder_11(third_slot)

            self.assertIs(first_slot.connected[-1], device.parameters[3])
            self.assertEqual(skipped_slot.connected, [])
            self.assertIs(third_slot.connected[-1], device.parameters[2])
        finally:
            FIXED_ASSIGNMENTS.CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = old_index
            FIXED_ASSIGNMENTS.CUSTOM_PARAMETER_APPEND_REST = old_append_rest

    def test_on_off_encoder_direction_sets_device_state(self):
        encoder = FakeControl(identifier=78)
        self.component.set_encoder_2(encoder)
        device_on = self.selected.devices[0].parameters[0]

        self.assertEqual(self.component._led_sender.last[encoder], ("device-toggle", 2, True))
        encoder.receive(63)
        self.assertEqual(device_on.value, device_on.min)
        self.assertEqual(self.component._led_sender.last[encoder], ("device-toggle", 2, False))
        encoder.receive(65)
        self.assertEqual(device_on.value, device_on.max)
        self.assertEqual(self.component._led_sender.last[encoder], ("device-toggle", 2, True))

    def test_parameter_encoder_operation_shows_device_parameter_and_value(self):
        display = FakeDisplayCommand()
        encoder = FakeControl(identifier=88)
        self.component.set_encoder_11_display(display)
        self.component.set_encoder_11(encoder)

        encoder.receive(65)

        self.assertEqual(self._display_lines(display), ("Device 4", "D4 P3", "0.0"))
        self.assertEqual(display.sent[-1][0], 98)
        self.assertFalse(display.sent[-1][2])
        self.assertTrue(display.sent[-1][3])

    def test_on_off_encoder_operation_shows_device_on_parameter(self):
        display = FakeDisplayCommand()
        encoder = FakeControl(identifier=78)
        self.component.set_encoder_2_display(display)
        self.component.set_encoder_2(encoder)

        encoder.receive(63)

        self.assertEqual(self._display_lines(display), ("Device 1", "Device On", "0.0"))

    def test_on_off_encoder_leds_use_per_encoder_device_toggle_colors(self):
        self.selected.devices[3].parameters[0].value = 0.0
        controls = {}
        for encoder_number in range(2, 8):
            controls[encoder_number] = FakeControl(identifier=76 + encoder_number)
            getattr(self.component, "set_encoder_{}".format(encoder_number))(controls[encoder_number])

        self.assertEqual(self.component._led_sender.last[controls[2]], ("device-toggle", 2, True))
        self.assertEqual(self.component._led_sender.last[controls[3]], ("device-toggle", 3, False))
        self.assertEqual(self.component._led_sender.last[controls[4]], ("device-toggle", 4, True))
        self.assertEqual(self.component._led_sender.last[controls[5]], ("device-toggle", 5, True))
        self.assertEqual(self.component._led_sender.last[controls[6]], ("device-toggle", 6, True))
        self.assertEqual(self.component._led_sender.last[controls[7]], ("device-toggle", 7, True))

    def test_on_off_encoder_without_target_turns_led_off(self):
        self.selected.devices = self.selected.devices[:8]
        encoder = FakeControl(identifier=83)

        self.component.set_encoder_7(encoder)

        self.assertEqual(self.component._led_sender.last[encoder], ("device-toggle", 7, None))

    def test_on_off_encoder_led_state_is_retained_by_colored_encoder(self):
        encoder = FakeManualLedControl(identifier=78)

        self.component.set_encoder_2(encoder)

        self.assertEqual(encoder.manual_led_rgb, ("device-toggle", 2, True))
        self.assertNotIn(encoder, self.component._led_sender.last)

    def test_replacing_on_off_encoder_clears_retained_led_state(self):
        first = FakeManualLedControl(identifier=78)
        second = FakeManualLedControl(identifier=78)

        self.component.set_encoder_2(first)
        self.component.set_encoder_2(second)

        self.assertIsNone(first.manual_led_rgb)
        self.assertEqual(first.manual_led_rgb_clear_count, 1)
        self.assertEqual(second.manual_led_rgb, ("device-toggle", 2, True))

    def test_on_off_encoder_led_state_is_forced_during_polling(self):
        encoder = FakeManualLedControl(identifier=78)

        self.component.set_encoder_2(encoder)
        encoder.manual_led_rgb_force = None
        self.component._update_assignments()

        self.assertEqual(encoder.manual_led_rgb, ("device-toggle", 2, True))
        self.assertTrue(encoder.manual_led_rgb_force)

    def test_encoder_7_controls_device_9_on_off(self):
        encoder = FakeControl(identifier=83)
        self.component.set_encoder_7(encoder)
        device_8_on = self.selected.devices[7].parameters[0]
        device_9_on = self.selected.devices[8].parameters[0]

        encoder.receive(63)

        self.assertEqual(device_8_on.value, device_8_on.max)
        self.assertEqual(device_9_on.value, device_9_on.min)

    def test_encoder_22_special_listener_limits_saturn_band_1_style(self):
        saturn = self.selected.devices[6]
        saturn.name = "Saturn 2"
        saturn.class_name = "Saturn 2"
        saturn.class_display_name = "Saturn 2"
        style = FakeParameter(
            "Band 1 Style",
            value=2.0,
            minimum=0.0,
            maximum=27.0,
            parent=saturn,
            value_items=SATURN_STYLE_ITEMS,
        )
        saturn.parameters = (
            saturn.parameters[0],
            saturn.parameters[1],
            style,
            saturn.parameters[3],
            saturn.parameters[4],
        )
        encoder = FakeControl(identifier=99)

        self.component.set_encoder_22(encoder)
        self.assertIs(encoder.manual_led_parameter, style)
        encoder.receive(65)
        self.assertEqual(style.value, 6.0)
        encoder.receive(65)
        self.assertEqual(style.value, 22.0)
        style.value = 21.0
        encoder.receive(63)
        self.assertEqual(style.value, 6.0)

    def test_encoder_22_special_listener_handles_saturn_style_without_value_items(self):
        saturn = self.selected.devices[6]
        saturn.name = "Saturn 2"
        saturn.class_name = "PluginDevice"
        saturn.class_display_name = "Saturn 2"
        style = FakeParameter(
            "Band 1 Style",
            value=2.0 / 27.0,
            minimum=0.0,
            maximum=1.0,
            parent=saturn,
        )
        saturn.parameters = (
            saturn.parameters[0],
            saturn.parameters[1],
            style,
            saturn.parameters[3],
            saturn.parameters[4],
        )
        encoder = FakeControl(identifier=99)

        self.component.set_encoder_22(encoder)
        self.assertEqual(encoder.connected, [])
        self.assertIs(encoder.manual_led_parameter, style)
        encoder.receive(65)
        self.assertAlmostEqual(style.value, 6.0 / 27.0)
        encoder.receive(65)
        self.assertAlmostEqual(style.value, 22.0 / 27.0)
        style.value = 21.0 / 27.0
        encoder.receive(63)
        self.assertAlmostEqual(style.value, 6.0 / 27.0)

    def test_special_manual_led_parameter_is_cleared_when_retargeted(self):
        saturn = self.selected.devices[6]
        saturn.name = "Saturn 2"
        saturn.class_name = "PluginDevice"
        saturn.class_display_name = "Saturn 2"
        style = FakeParameter(
            "Band 1 Style",
            value=2.0 / 27.0,
            minimum=0.0,
            maximum=1.0,
            parent=saturn,
        )
        saturn.parameters = (
            saturn.parameters[0],
            saturn.parameters[1],
            style,
            saturn.parameters[3],
            saturn.parameters[4],
        )
        encoder = FakeControl(identifier=99)
        replacement = FakeTrack("Replacement", devices=tuple(FakeDevice(index) for index in range(1, 10)))

        self.component.set_encoder_22(encoder)
        self.song.view.selected_track = replacement
        self.component._update_assignments()

        self.assertIsNone(encoder.manual_led_parameter)
        self.assertEqual(encoder.manual_led_clear_count, 1)
        self.assertIs(encoder.connected[-1], replacement.devices[6].parameters[2])

    def test_assignment_retargets_after_selected_track_change(self):
        control = FakeControl()
        self.component.set_fader_8(control)
        replacement = FakeTrack("Replacement", devices=tuple(FakeDevice(index) for index in range(1, 10)))

        self.song.view.selected_track = replacement
        self.component._update_assignments()

        self.assertIs(control.connected[-1], replacement.mixer_device.volume)


class TrackButtonsTest(unittest.TestCase):
    def setUp(self):
        MIXING_ACTION.selected[:] = []
        self.layout = _track_layout()
        self.song = FakeSong(self.layout, selected_track=self.layout[0])
        self.component = TRACK_BUTTONS.TrackButtonsComponent()
        self.component.song = self.song
        self.component._selected_blink_is_on = lambda: True
        self.buttons = [FakeButton(index + 37) for index in range(16)]
        for index, button in enumerate(self.buttons, start=1):
            getattr(self.component, "set_track_button_{}".format(index))(button)
        self.shift = FakeButton()
        self.solo = FakeButton(65)
        self.mute = FakeButton(66)
        self.component.set_shift_button(self.shift)
        self.component.set_solo_modifier_button(self.solo)
        self.component.set_mute_modifier_button(self.mute)

    def test_select_mode_repressing_selected_track_toggles_mute(self):
        child = self.layout[1]

        self.buttons[1].receive(127)

        self.assertIs(self.song.view.selected_track, child)
        self.assertEqual(MIXING_ACTION.selected[-1], child)
        self.assertFalse(child.mute)

        self.buttons[1].receive(127)

        self.assertTrue(child.mute)
        self.assertFalse(child.solo)

        self.buttons[1].receive(127)

        self.assertFalse(child.mute)

    def test_solo_button_toggles_persistent_solo_mode(self):
        child = self.layout[1]

        self.solo.receive(127)
        self.solo.receive(0)
        self.buttons[1].receive(127)

        self.assertTrue(child.solo)
        self.assertFalse(child.mute)
        self.assertEqual(MIXING_ACTION.selected, [])
        self.assertEqual(
            self.component._led_sender.last[self.solo],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.SOLO_ON,
        )

        self.solo.receive(127)

        self.assertEqual(
            self.component._led_sender.last[self.solo],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.SOLO_MODIFIER_IDLE,
        )

    def test_mute_button_toggles_persistent_mute_mode_and_switches_from_solo_mode(self):
        child = self.layout[1]

        self.solo.receive(127)
        self.mute.receive(127)
        self.mute.receive(0)

        self.buttons[1].receive(127)

        self.assertFalse(child.solo)
        self.assertTrue(child.mute)
        self.assertEqual(MIXING_ACTION.selected, [])
        self.assertEqual(
            self.component._led_sender.last[self.solo],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.SOLO_MODIFIER_IDLE,
        )
        self.assertEqual(
            self.component._led_sender.last[self.mute],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.MUTE_MODIFIER_ON,
        )

        self.mute.receive(127)

        self.assertEqual(
            self.component._led_sender.last[self.mute],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.MUTE_MODIFIER_IDLE,
        )

    def test_shift_does_not_intercept_track_button_actions(self):
        self.shift.receive(127)
        self.buttons[1].receive(127)
        self.buttons[8].receive(127)

        self.assertEqual(MIXING_ACTION.selected[-2:], [self.layout[1], self.layout[3]])

    def test_shift_leds_keep_showing_normal_track_states(self):
        self.song.view.selected_track = self.layout[3]
        self.component.refresh_led_feedback()
        before = dict(self.component._led_sender.last)

        self.shift.receive(127)
        last = self.component._led_sender.last

        self.assertEqual(last[self.buttons[0]], before[self.buttons[0]])
        self.assertEqual(last[self.buttons[1]], before[self.buttons[1]])
        self.assertEqual(last[self.buttons[7]], before[self.buttons[7]])

    def test_normal_led_priority_is_solo_selected_then_mute(self):
        child = self.layout[1]
        child.solo = True
        self.component._update_track_button_led(1, force=True)
        self.assertEqual(
            self.component._led_sender.last[self.buttons[1]],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.SOLO_ON,
        )

        child.solo = False
        child.mute = True
        self.song.view.selected_track = self.layout[3]
        self.component._update_track_button_led(1, force=True)
        self.assertEqual(self.component._led_sender.last[self.buttons[1]], ("dim", child.rgb))

        child.mute = False
        self.component._update_track_button_led(1, force=True)
        self.assertEqual(self.component._led_sender.last[self.buttons[1]], ("active", child.rgb))

    def test_selected_muted_track_blinks_with_dim_track_color(self):
        child = self.layout[1]
        child.mute = True
        self.song.view.selected_track = child

        self.component._selected_blink_is_on = lambda: True
        self.component._update_track_button_led(1, force=True)

        self.assertEqual(self.component._led_sender.last[self.buttons[1]], ("dim", child.rgb))

        self.component._selected_blink_is_on = lambda: False
        self.component._update_track_button_led(1, force=True)

        self.assertEqual(
            self.component._led_sender.last[self.buttons[1]],
            sys.modules["Launch_Control_XL_3_Mixing.colors"].Theme.OFF,
        )


class ColorManagementTest(unittest.TestCase):
    def test_button_and_device_toggle_brightness_coefficients(self):
        tree = ast.parse((PACKAGE_ROOT / "colors.py").read_text())
        constants = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Constant):
                constants[target.id] = node.value.value

        self.assertEqual(constants["TRACK_ON_BRIGHTNESS"], 0.25)
        self.assertEqual(constants["TRACK_MUTED_BRIGHTNESS"], 0.03)
        self.assertEqual(constants["ENCODER_MIN_BRIGHTNESS"], 0.03)
        self.assertEqual(constants["ENCODER_CENTER_BRIGHTNESS"], 0.175)
        self.assertEqual(constants["ENCODER_MAX_BRIGHTNESS"], 0.38)
        self.assertEqual(constants["ENCODER_PARAMETER_BRIGHTNESS"], 0.25)
        self.assertEqual(constants["DEVICE_TOGGLE_ENCODER_ON_BRIGHTNESS"], 0.25)
        self.assertEqual(constants["DEVICE_TOGGLE_ENCODER_OFF_BRIGHTNESS"], 0.03)

    def test_encoder_min_center_max_use_white_base_color(self):
        tree = ast.parse((PACKAGE_ROOT / "colors.py").read_text())
        palette = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Palette")
        assignments = {}
        for node in palette.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name):
                assignments[target.id] = node.value

        for name in ("ENCODER_MIN", "ENCODER_CENTER", "ENCODER_MAX"):
            value = assignments[name]
            self.assertIsInstance(value, ast.Name)
            self.assertEqual(value.id, "WHITE")

    def test_led_calls_do_not_use_inline_rgb_literals(self):
        violations = []
        for path in PACKAGE_ROOT.glob("*.py"):
            if path.name == "colors.py":
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr not in ("send_rgb", "make_rgb_led_message") or len(node.args) < 2:
                    continue
                rgb_arg = node.args[1]
                if isinstance(rgb_arg, (ast.Tuple, ast.List)):
                    violations.append("{}:{}".format(path.name, node.lineno))
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
