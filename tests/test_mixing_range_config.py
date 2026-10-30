"""Normalized range limits validate independently and preserve full-range entries."""

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

    def test_max_and_both_limits_accept_device_and_mixer_targets(self):
        for control in ("fader_3", "encoder_11"):
            for target in ({"device": 6, "parameter": "Drive"},
                           {"mixer": "volume"}, {"mixer": "pan"},
                           {"mixer": "send", "send": 2}, {"mixer": "cue_volume"}):
                for limits in ({"max": 0.001}, {"max": 0.5}, {"max": 1},
                               {"min": 0, "max": 1.0}, {"min": 0.5, "max": 5 / 6}):
                    with self.subTest(control=control, target=target, limits=limits):
                        entry = dict(target, **limits)
                        self.assertEqual(validate_assignments({control: entry})[control], entry)

    def test_full_range_does_not_add_defaults_or_change_existing_options(self):
        for extra in ({}, {"min": 0}, {"max": 1}, {"min": 0.0, "max": 1.0}):
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

    def test_invalid_max_is_rejected_without_disabling_other_controls(self):
        for maximum in (-1, -0.1, 0, 0.0, 1.001, 2, True, False, None, "0.5", [], {},
                        float("nan"), float("inf"), -float("inf"), 10 ** 400):
            with self.subTest(maximum=maximum), self.assertLogs(level="WARNING"):
                result = validate_assignments({
                    "fader_3": {"device": 6, "parameter": "Drive", "max": maximum},
                    "encoder_8": {"mixer": "cue_volume"},
                })
            self.assertIsNone(result["fader_3"])
            self.assertEqual(result["encoder_8"], {"mixer": "cue_volume"})

    def test_min_must_be_less_than_max_for_both_target_types(self):
        for target in ({"device": 6, "parameter": "Drive"}, {"mixer": "volume"}):
            for minimum, maximum in ((0.5, 0.5), (0.75, 0.25), (0.999, 0.001)):
                with self.subTest(target=target, minimum=minimum, maximum=maximum):
                    with self.assertLogs(level="WARNING"):
                        entry = dict(target, min=minimum, max=maximum)
                        self.assertIsNone(validate_assignments({"fader_3": entry})["fader_3"])

    def test_takeover_accepts_supported_names_for_all_bounded_fader_forms(self):
        for mode in ("value_scaling", "pickup", "none"):
            for target in ({"device": 6, "parameter": "Drive"}, {"mixer": "volume"}):
                for limits in ({"min": 0.5}, {"max": 0.75}, {"min": 0.5, "max": 0.75}):
                    with self.subTest(mode=mode, target=target, limits=limits):
                        entry = dict(target, takeover=mode, **limits)
                        self.assertEqual(validate_assignments({"fader_3": entry})["fader_3"], entry)

    def test_takeover_is_rejected_for_encoders_or_full_range(self):
        cases = (
            ("encoder_3", {"min": 0.5, "takeover": "pickup"}),
            ("encoder_3", {"max": 0.5, "takeover": "pickup"}),
            ("encoder_3", {"min": 0.25, "max": 0.75, "takeover": "none"}),
            ("fader_3", {"takeover": "pickup"}),
            ("fader_3", {"min": 0, "takeover": "none"}),
            ("fader_3", {"max": 1, "takeover": "none"}),
            ("fader_3", {"min": 0, "max": 1, "takeover": "none"}),
            ("fader_3", {"min": 0.5, "takeover": "scaling"}),
            ("fader_3", {"min": 0.5, "takeover": None}),
            ("fader_3", {"min": 0.5, "takeover": True}),
            ("fader_3", {"min": 0.5, "takeover": ["pickup"]}),
        )
        for control, options in cases:
            with self.subTest(control=control, options=options), self.assertLogs(level="WARNING"):
                entry = {"device": 6, "parameter": "Drive", **options}
                self.assertIsNone(validate_assignments({control: entry})[control])

    def test_bounded_ranges_reject_directional_endpoints_but_full_range_preserves_legacy(self):
        for target in ({"device": 6, "parameter": "Device On"}, {"mixer": "pan"}):
            for limits in ({"min": 0.5}, {"max": 0.75}, {"min": 0.25, "max": 0.75}):
                with self.subTest(target=target, limits=limits):
                    with self.assertLogs(level="WARNING"):
                        entry = dict(target, directional_on_off=True, **limits)
                        self.assertIsNone(validate_assignments({"encoder_3": entry})["encoder_3"])
                    bounded = dict(target, directional_on_off=False, **limits)
                    self.assertEqual(validate_assignments({"encoder_3": bounded})["encoder_3"], bounded)
            for limits in ({}, {"min": 0}, {"max": 1}, {"min": 0, "max": 1}):
                with self.subTest(target=target, limits=limits):
                    legacy = dict(target, directional_on_off=True, **limits)
                    self.assertEqual(validate_assignments({"encoder_3": legacy})["encoder_3"], legacy)

    def test_limits_do_not_relax_other_configuration_rules(self):
        cases = (
            {"device": 0, "parameter": "Drive", "min": 0.5},
            {"device": 6, "parameter": "", "min": 0.5},
            {"device": 6, "parameter": "Drive", "min": 0.5, "maximum": 1},
            {"mixer": "send", "min": 0.5},
            {"device": 6, "parameter": "Device On", "min": 0.5,
             "auto_bypass": {"off_at": "min"}},
        )
        for entry in cases:
            with self.subTest(entry=entry), self.assertLogs(level="WARNING"):
                self.assertIsNone(validate_assignments({"fader_3": entry})["fader_3"])


if __name__ == "__main__":
    unittest.main()
