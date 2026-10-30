"""Configured lower limits are normalized and leave legacy entries unchanged."""

import unittest

import test_mixing  # Install the same minimal Live stubs as the other tests.

from Launch_Control_XL_3_Mixing.mixing_targets import validate_assignments


class MixingRangeConfigurationTest(unittest.TestCase):
    def test_min_accepts_normalized_device_and_mixer_limits_on_both_control_types(self):
        for control in ("fader_3", "encoder_11"):
            for target in ({"device": 6, "parameter": "Drive"},
                           {"mixer": "volume"}, {"mixer": "pan"},
                           {"mixer": "send", "send": 2}, {"mixer": "cue_volume"}):
                for minimum in (0, 0.0, 0.5, 0.999):
                    with self.subTest(control=control, target=target, minimum=minimum):
                        entry = dict(target, min=minimum)
                        self.assertEqual(validate_assignments({control: entry})[control], entry)

    def test_missing_min_and_zero_min_do_not_add_takeover_or_change_existing_options(self):
        for extra in ({}, {"min": 0}):
            entry = {"device": 6, "parameter": "Drive", "occurrence": 1,
                     "auto_bypass": {"off_at": "min"}, **extra}
            result = validate_assignments({"fader_3": entry})["fader_3"]
            self.assertEqual(result, entry)
            self.assertNotIn("takeover", result)
            self.assertIsNot(result, entry)
            self.assertIsNot(result["auto_bypass"], entry["auto_bypass"])

    def test_invalid_min_is_rejected_without_disabling_other_controls(self):
        for minimum in (-0.1, 1, 1.0, 2, True, False, None, "0.5", [], {},
                        float("nan"), float("inf"), -float("inf"), 10 ** 400):
            with self.subTest(minimum=minimum), self.assertLogs(level="WARNING"):
                result = validate_assignments({
                    "fader_3": {"device": 6, "parameter": "Drive", "min": minimum},
                    "encoder_8": {"mixer": "cue_volume"},
                })
            self.assertIsNone(result["fader_3"])
            self.assertEqual(result["encoder_8"], {"mixer": "cue_volume"})

    def test_takeover_accepts_only_supported_names_for_positive_min_faders(self):
        for mode in ("value_scaling", "pickup", "none"):
            for target in ({"device": 6, "parameter": "Drive"}, {"mixer": "volume"}):
                with self.subTest(mode=mode, target=target):
                    entry = dict(target, min=0.5, takeover=mode)
                    self.assertEqual(validate_assignments({"fader_3": entry})["fader_3"], entry)

    def test_takeover_is_rejected_for_encoders_or_missing_positive_min(self):
        cases = (
            ("encoder_3", {"min": 0.5, "takeover": "pickup"}),
            ("fader_3", {"takeover": "pickup"}),
            ("fader_3", {"min": 0, "takeover": "none"}),
            ("fader_3", {"min": 0.5, "takeover": "scaling"}),
            ("fader_3", {"min": 0.5, "takeover": None}),
            ("fader_3", {"min": 0.5, "takeover": True}),
            ("fader_3", {"min": 0.5, "takeover": ["pickup"]}),
        )
        for control, options in cases:
            with self.subTest(control=control, options=options), self.assertLogs(level="WARNING"):
                entry = {"device": 6, "parameter": "Drive", **options}
                self.assertIsNone(validate_assignments({control: entry})[control])

    def test_positive_min_rejects_directional_endpoints_but_zero_preserves_legacy(self):
        for target in ({"device": 6, "parameter": "Device On"}, {"mixer": "pan"}):
            with self.subTest(target=target), self.assertLogs(level="WARNING"):
                entry = dict(target, min=0.5, directional_on_off=True)
                self.assertIsNone(validate_assignments({"encoder_3": entry})["encoder_3"])
            legacy = dict(target, min=0, directional_on_off=True)
            self.assertEqual(validate_assignments({"encoder_3": legacy})["encoder_3"], legacy)
            bounded = dict(target, min=0.5, directional_on_off=False)
            self.assertEqual(validate_assignments({"encoder_3": bounded})["encoder_3"], bounded)

    def test_min_does_not_relax_other_configuration_rules(self):
        cases = (
            {"device": 0, "parameter": "Drive", "min": 0.5},
            {"device": 6, "parameter": "", "min": 0.5},
            {"device": 6, "parameter": "Drive", "min": 0.5, "max": 1},
            {"mixer": "send", "min": 0.5},
            {"device": 6, "parameter": "Device On", "min": 0.5,
             "auto_bypass": {"off_at": "min"}},
        )
        for entry in cases:
            with self.subTest(entry=entry), self.assertLogs(level="WARNING"):
                self.assertIsNone(validate_assignments({"fader_3": entry})["fader_3"])


if __name__ == "__main__":
    unittest.main()
