"""Regressions for MIDI bursts sharing an output with display updates."""

import ast
import types
import unittest
from pathlib import Path


class BaseSurface:
    def __init__(self):
        self.sent = []
        self.send_options = []
        self._midi_message_list = []
        self._should_delay_flushing_display_messages = True
        self._tasks = types.SimpleNamespace(add=self.delayed.append)

    def _send_midi(self, message, optimized=True):
        self.send_options.append(optimized)
        self._midi_message_list.append((len(self._midi_message_list), message))
        return True

    def _do_send_midi(self, message):
        self.sent.append(message)

    def _flush_midi_messages(self):
        for _, message in self._midi_message_list:
            self._do_send_midi(message)
        self._midi_message_list[:] = []


ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / "Launch_Control_XL_3_Mixing/__init__.py").read_text())
CLASS = next(node for node in TREE.body if isinstance(node, ast.ClassDef) and node.name == "Launch_Control_XL_3_Mixing")
METHODS = [node for node in CLASS.body if isinstance(node, ast.FunctionDef) and node.name in ("send_keyboard_midi", "_flush_midi_messages")]
HEADER = (0xF0, 0, 32, 41, 2, 21)
NAMESPACE = {
    "ControlSurface": BaseSurface,
    "midi": types.SimpleNamespace(SYSEX_HEADER=HEADER),
    "SYSEX_FLUSH_THRESHOLD": 10,
    "SYSEX_DISPLAY_ID_LENGTH": 9,
    "task": types.SimpleNamespace(
        sequence=lambda *parts: parts,
        delay=lambda seconds: seconds,
        run=lambda callback, *args: lambda: callback(*args),
    ),
}
ISOLATED_CLASS = ast.ClassDef(name=CLASS.name, bases=CLASS.bases, keywords=[], body=METHODS, decorator_list=[])
exec(compile(ast.fix_missing_locations(ast.Module(body=[ISOLATED_CLASS], type_ignores=[])), str(ROOT / "Launch_Control_XL_3_Mixing/__init__.py"), "exec"), NAMESPACE)
Surface = NAMESPACE[CLASS.name]


class KeyboardMidiFlushTest(unittest.TestCase):
    def setUp(self):
        # Run the actual surface methods with a recording framework adapter.
        self.surface = Surface.__new__(Surface)
        self.surface.delayed = []
        BaseSurface.__init__(self.surface)

    def test_every_navigation_event_disables_framework_optimization(self):
        for _ in range(20):
            self.assertTrue(self.surface.send_keyboard_midi((0xBF, 119, 1)))
        self.surface._flush_midi_messages()
        self.assertEqual(self.surface.send_options, [False] * 20)
        self.assertEqual(self.surface.sent, [(0xBF, 119, 1)] * 20)
        self.assertEqual(self.surface.delayed, [])

    def test_display_flood_preserves_duplicate_ccs_and_their_order(self):
        expected = [(0xBF, 119, value) for value in (0, 1, 1, 2, 2, 1)]
        messages = []
        for index in range(12):
            messages.append(HEADER + (6, 13, 0, 65 + index, 0xF7))
            if index < len(expected):
                messages.append(expected[index])
        self.surface._midi_message_list = list(enumerate(messages))
        self.surface._flush_midi_messages()
        self.assertEqual(self.surface.sent, expected)
        self.assertEqual(len(self.surface.delayed), 1)
        self.surface.delayed[0][1]()
        self.assertEqual(self.surface.sent[-1], HEADER + (6, 13, 0, 76, 0xF7))

    def test_rgb_and_connection_sysex_remain_immediate_during_display_flood(self):
        immediate = [HEADER + (2, 127, 0xF7), HEADER + (1, 83, 36, 0, 0, 31, 0xF7), HEADER + (2, 0, 0xF7)]
        displays = [HEADER + (6, 13 + i, 0, 65, 0xF7) for i in range(12)]
        self.surface._midi_message_list = list(enumerate(displays + immediate))
        self.surface._flush_midi_messages()
        self.assertEqual(self.surface.sent, immediate)
        self.assertEqual(len(self.surface.delayed), 12)


if __name__ == "__main__":
    unittest.main()
