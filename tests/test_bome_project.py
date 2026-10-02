"""Keep the external Bome project compatible with the Remote Script protocol."""

import configparser
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import test_mixing
from Launch_Control_XL_3_Mixing import midi_keyboard


class BomeProjectTest(unittest.TestCase):
    def setUp(self):
        self.project = configparser.ConfigParser(interpolation=None)
        self.project.optionxform = str
        self.project.read(Path(__file__).resolve().parents[1] / "bome/LCXL3 Preset Navigation.bmtp")
        self.preset = self.project["Preset.0"]

    def action(self, name, index):
        return ET.fromstring(self.preset[f"{name}{index}"][4:])

    def test_key_events_match_channel_cc_and_discrete_values(self):
        for index, value, key in ((4, midi_keyboard.UP_VALUE, 38), (5, midi_keyboard.DOWN_VALUE, 40)):
            incoming = self.action("Incoming", index).find("Simple")
            self.assertEqual(int(incoming.find("Channel").get("num")), midi_keyboard.CHANNEL)
            self.assertEqual(int(incoming.find("Value1").get("num"), 0), midi_keyboard.NAVIGATION_CC)
            self.assertEqual(int(incoming.find("Value2").get("num"), 0), value)
            outgoing = self.action("Outgoing", index)
            self.assertEqual(outgoing.findtext("Type"), "Physical")
            events = list(outgoing.find("Keys"))
            self.assertEqual([int(e.get("VK")) for e in events], [key, key])
            self.assertIsNone(events[0].get("Release"))
            self.assertEqual(events[1].get("Release"), "Y")
            self.assertNotIn("Repeat", self.preset[f"Outgoing{index}"])
            self.assertIn("if(ga!=1)noexecute", self.preset[f"Options{index}"])
            self.assertNotIn("Dlay", self.preset[f"Options{index}"])

    def test_focus_query_and_state_notifications_match_script(self):
        self.assertEqual(self.preset["Incoming0"], "EnDi02")
        self.assertTrue(self.preset["Options0"].endswith("ga=0"))
        app = "Ableton Live 12 Suite.app"
        self.assertEqual(self.preset["Incoming1"], f"AcApA{len(app):04X}{app}")
        self.assertEqual(self.preset["Incoming2"], f"AcApD{len(app):04X}{app}")
        self.assertTrue(self.preset["Options1"].endswith("ga=1"))
        self.assertTrue(self.preset["Options2"].endswith("ga=0"))
        for index, value in ((0, 0), (1, 1), (2, 0)):
            outgoing = self.action("Outgoing", index).find("Simple")
            self.assertEqual(int(outgoing.find("Value1").get("num"), 0), midi_keyboard.FOCUS_CC)
            self.assertEqual(int(outgoing.find("Value2").get("num"), 0), value)
        query = self.action("Incoming", 3).find("Simple")
        self.assertEqual(int(query.find("Value2").get("num"), 0), midi_keyboard.FOCUS_QUERY_VALUE)
        self.assertEqual(self.action("Outgoing", 3).find("Simple/Value2").get("var"), "ga")

    def test_swallow_remains_active_even_when_key_rules_skip(self):
        self.assertEqual(self.preset["Active"], "1")
        self.assertEqual(self.preset["PresetSwitchIgnore"], "1")
        self.assertEqual(self.preset["Options6"], "Actv01Stop00OutO01")
        self.assertEqual(self.preset["Outgoing6"], "None")
        incoming = self.action("Incoming", 6).find("Simple")
        self.assertEqual(int(incoming.find("Value1").get("num"), 0), midi_keyboard.NAVIGATION_CC)
        self.assertEqual(incoming.find("Value2").get("Type"), "SetVar")

    def test_router_uses_bidirectional_virtual_port_one_without_a_loop(self):
        routes = self.project["MIDI.routes"]
        self.assertEqual(dict(routes), {
            "In0": "LCXL3 1 DAW Out", "Out0": "Bome Virtual Port 1",
            "In1": "Bome Virtual Port 1", "Out1": "LCXL3 1 DAW In",
        })
        self.assertEqual(self.preset["DefaultInPorts"], "MIDA00010013Bome Virtual Port 1")
        self.assertEqual(self.preset["DefaultOutPorts"], "MIDA00010013Bome Virtual Port 1")


if __name__ == "__main__":
    unittest.main()
