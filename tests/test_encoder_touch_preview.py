"""Hardware Shift+turn can report touch without a normal encoder value CC."""

import ast
import types
import unittest

import test_mixing as fixtures
import test_shift_preview as preview


class TouchPreviewChecks:
    bind = preview.ParameterPreviewChecks.bind

    def touch_binding(self, name):
        control, display = self.bind(name)
        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        router.set_target_components(**{self.target_key: self.component})
        shift, touch = fixtures.FakeButton(63), fixtures.FakeButton(76 + int(name.split("_")[1]))
        router.set_shift_button(shift)
        getattr(router, "set_{}_touch".format(name))(touch)
        return router, shift, touch, control, display

    def test_touch_only_displays_current_assignment_without_value_cc(self):
        _, shift, touch, control, display = self.touch_binding(self.encoder_name)
        parameter = control.mapped_parameter
        parameter.value = 0.37
        shift.receive(127)
        touch.receive(127)

        self.assertEqual(preview.display_lines(display), self.expected_lines(parameter))
        self.assertTrue(display.sent[-1][3])
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(control.native_updates, [])
        self.assertEqual(parameter.value, 0.37)

        count = len(display.sent)
        touch.receive(0)
        self.assertEqual(len(display.sent), count)
        parameter.value = 0.42
        touch.receive(127)
        self.assertEqual(preview.display_lines(display)[2], "0.42")
        self.assertTrue(display.sent[-1][3])
        self.assertEqual(len(display.sent), count + 1)

        shift.receive(0)
        count = len(display.sent)
        touch.receive(0)
        touch.receive(127)
        self.assertEqual(len(display.sent), count)
        self.assertIs(control.mapped_parameter, parameter)
        self.assertEqual(parameter.value, 0.42)

    def test_touch_ignores_inactive_and_unshifted_components(self):
        _, shift, touch, control, display = self.touch_binding(self.encoder_name)
        prepared = list(display.sent)
        self.assertTrue(all(not immediate and not trigger for _, _, immediate, trigger in prepared))
        touch.receive(127)
        self.component.preview_encoder(self.encoder_name)
        self.assertEqual(display.sent, prepared)
        shift.receive(127)
        self.component.set_active(False)
        prepared = list(display.sent)
        touch.receive(127)
        self.component.preview_encoder(self.encoder_name)
        self.assertEqual(display.sent, prepared)
        self.assertEqual(control.native_updates, [])

    def test_touch_resolves_track_change_and_missing_target_without_polling(self):
        _, shift, touch, control, display = self.touch_binding(self.encoder_name)
        original = control.mapped_parameter
        shift.receive(127)
        replacement = self.replace_target()
        replacement.value = 0.75
        touch.receive(127)
        self.assertEqual(preview.display_lines(display)[1:], (replacement.name, "0.75"))
        self.assertIsNone(control.mapped_parameter)
        self.assertEqual(original.value, 0.0)
        self.assertEqual(replacement.value, 0.75)

        self.song.view.selected_track = fixtures.FakeTrack("Empty")
        touch.receive(127)
        self.assertEqual(preview.display_lines(display)[1:], ("Unassigned", ""))
        self.assertIsNone(control.mapped_parameter)


class FixedEncoderTouchTest(TouchPreviewChecks, unittest.TestCase):
    setUp = fixtures.FixedAssignmentsTest.setUp
    target_key = "fixed_assignments"
    encoder_name = "encoder_11"

    def expected_lines(self, parameter):
        return ("Device 4", parameter.name, str(parameter))

    def replace_target(self):
        track = fixtures.FakeTrack("Replacement", devices=tuple(fixtures.FakeDevice(i) for i in range(1, 10)))
        self.song.view.selected_track = track
        return track.devices[3].parameters[3]

    def test_touch_on_mode_device_on_and_unassigned_encoders_is_display_only(self):
        for name, expected in (("encoder_1", "Loopcloud"), ("encoder_2", "Device On"), ("encoder_10", "Unassigned")):
            with self.subTest(control=name):
                self.component.set_shift_pressed(False)
                _, shift, touch, control, display = self.touch_binding(name)
                before = self.selected.devices[0].parameters[0].value
                shift.receive(127)
                touch.receive(127)
                self.assertEqual(preview.display_lines(display)[1], expected)
                self.assertEqual(self.selected.devices[0].parameters[0].value, before)
                self.assertFalse(self.loopcloud.solo)
                self.assertEqual(self.component._loopcloud_metric_submode, fixtures.FIXED_ASSIGNMENTS.LOOPCLOUD_SUBMODE)
                self.assertEqual(control.native_updates, [])


class InstrumentEncoderTouchTest(TouchPreviewChecks, unittest.TestCase):
    setUp = fixtures.InstrumentAssignmentsTest.setUp
    target_key = "instrument_assignments"
    encoder_name = "encoder_23"

    def expected_lines(self, parameter):
        return ("Instrument", parameter.name, str(parameter))

    def replace_target(self):
        device = fixtures.FakeInstrumentDevice("Replacement Instrument")
        self.song.view.selected_track = fixtures.FakeTrack(
            "Replacement", devices=(fixtures.FakeDevice(1), fixtures.FakeDevice(2), device)
        )
        return device.parameters[23]


class TouchRoutingTest(unittest.TestCase):
    def test_all_24_encoders_route_touch_and_release_replaced_listeners(self):
        class Receiver:
            def __init__(self):
                self.previews = []

            def preview_encoder(self, name):
                self.previews.append(name)

        router = fixtures.CONTROL_ROUTER.ControlRouterComponent()
        receiver = Receiver()
        router.set_target_components(fixed_assignments=receiver)
        shift = fixtures.FakeButton(63)
        router.set_shift_button(shift)
        shift.receive(127)
        touches = []
        mappings = fixtures.MAPPINGS.create_mappings(None)["Control_Router"]
        for number in range(1, 25):
            name = "encoder_{}".format(number)
            self.assertEqual(mappings[name + "_touch"], name + "_touch")
            first, replacement = fixtures.FakeButton(), fixtures.FakeButton()
            setter = getattr(router, "set_{}_touch".format(name))
            setter(first)
            setter(replacement)
            setter(replacement)
            self.assertEqual(first.listeners, [])
            self.assertEqual(len(replacement.listeners), 1)
            replacement.receive(127)
            replacement.receive(0)
            touches.append(replacement)
        self.assertEqual(receiver.previews, ["encoder_{}".format(i) for i in range(1, 25)])
        router.disconnect()
        self.assertTrue(all(not button.listeners for button in touches))

    def test_hardware_touch_messages_and_channel_are_distinct_from_value_input(self):
        # Execute the actual MIDI constants/functions without importing Live.
        root = fixtures.PACKAGE_ROOT
        tree = ast.parse((root / "midi.py").read_text())
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        namespace = {"SYSEX_START": 240, "SYSEX_END": 247}
        exec(compile(tree, "midi.py", "exec"), namespace)
        midi = types.SimpleNamespace(**namespace)
        self.assertEqual(midi.make_touch_output_message(), (182, 71, 127))
        self.assertEqual(midi.make_touch_output_message(enabled=False), (182, 71, 0))

        tree = ast.parse((root / "__init__.py").read_text())
        specification = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Specification")
        messages = {"midi": midi}
        for node in specification.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id in ("hello_messages", "goodbye_messages")
                for target in node.targets
            ):
                exec(compile(ast.Module(body=[node], type_ignores=[]), "__init__.py", "exec"), messages)
        self.assertIn((182, 71, 127), messages["hello_messages"])
        self.assertIn((182, 71, 0), messages["goodbye_messages"])

        class RecordingElements:
            def __init__(self):
                self.buttons = {}

            def add_button(self, identifier, name, **kwargs):
                self.buttons[name.lower()] = (identifier, kwargs)

            def add_encoder_matrix(self, *args, **kwargs):
                pass

            add_matrix = add_encoder_matrix
            add_sysex_element = add_encoder_matrix
            add_element = add_encoder_matrix

        tree = ast.parse((root / "elements.py").read_text())
        tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
        namespace = {
            "ElementsBase": RecordingElements, "MapMode": types.SimpleNamespace(LinearBinaryOffset=1),
            "DisplayTargetElement": object, "ColoredEncoderElement": object, "midi": midi,
        }
        exec(compile(tree, "elements.py", "exec"), namespace)
        elements = namespace["Elements"]()
        for number in range(1, 25):
            identifier, options = elements.buttons["encoder_{}_touch".format(number)]
            self.assertEqual(identifier, 76 + number)
            self.assertEqual(options["channel"], 14)
            self.assertFalse(options.get("is_private", False))


if __name__ == "__main__":
    unittest.main()
