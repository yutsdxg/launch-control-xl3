import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Launch_Control_XL_3_Mixing" / "parameter_steps.py"
SPEC = importlib.util.spec_from_file_location("parameter_steps_under_test", MODULE_PATH)
STEPS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STEPS)

TRANSPOSE = {"step_size": 12, "display_min": -24, "display_max": 24}
OCTAVE = {"step_size": 1, "display_min": -2, "display_max": 2}


class ReadOnlyParameter:
    def __init__(self, minimum=0.0, maximum=1.0, items=(), formatter=None):
        self.min, self.max = minimum, maximum
        self.value_items = items
        if formatter is not None:
            self.str_for_value = formatter

    @property
    def value(self):
        raise AssertionError("Resolving steps must not read or write the current value")

    @value.setter
    def value(self, value):
        raise AssertionError("Probing must not change the parameter")


class ParameterStepsTest(unittest.TestCase):
    def assertValues(self, parameter, expected, options=TRANSPOSE):
        actual = STEPS.stepped_parameter_values(parameter, options)
        self.assertEqual(len(actual), len(expected))
        for result, value in zip(actual, expected):
            self.assertAlmostEqual(result, value, places=6)

    def test_numeric_items_keep_only_octaves_in_raw_index_order(self):
        items = tuple("{:+d} semitones".format(value) for value in range(24, -25, -1))
        parameter = ReadOnlyParameter(items=items, formatter=lambda value: "unavailable")
        self.assertValues(parameter, (0, 0.25, 0.5, 0.75, 1))

    def test_numeric_octave_items_support_non_normalized_raw_bounds(self):
        parameter = ReadOnlyParameter(-2, 2, ("+2 oct", "+1 oct", "0 oct", "−1 oct", "−2 oct"))
        self.assertValues(parameter, (-2, -1, 0, 1, 2), OCTAVE)

    def test_reversed_nonlinear_display_is_resolved_without_writes(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} st".format(24 - 48 * value * value))
        self.assertValues(parameter, (0, 0.5, 0.5 ** 0.5, 0.75 ** 0.5, 1))

    def test_actual_display_range_takes_precedence_over_fallback(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} semitones".format(-36 + 72 * value))
        self.assertValues(parameter, tuple(value / 6.0 for value in range(7)))

    def test_discrete_display_has_exact_candidate_labels(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} octaves".format(round(2 - 4 * value)))
        values = STEPS.stepped_parameter_values(parameter, OCTAVE)
        self.assertEqual(tuple(parameter.str_for_value(value) for value in values),
                         ("2 octaves", "1 octaves", "0 octaves", "-1 octaves", "-2 octaves"))

    def test_display_bounds_exclude_non_octave_endpoints(self):
        parameter = ReadOnlyParameter(formatter=lambda value: str(-20 + 40 * value))
        self.assertValues(parameter, (0.2, 0.5, 0.8))

    def test_no_api_uses_configured_range_and_raw_bounds(self):
        self.assertValues(ReadOnlyParameter(-24, 24), (-24, -12, 0, 12, 24))

    def test_normalized_and_percentage_labels_use_fallback(self):
        for formatter in (lambda value: str(value), lambda value: "{}%".format(value * 100)):
            with self.subTest(formatter=formatter):
                self.assertValues(ReadOnlyParameter(formatter=formatter), (0, 0.25, 0.5, 0.75, 1))

    def test_normalized_items_do_not_mask_the_musical_display(self):
        parameter = ReadOnlyParameter(items=("0", "0.5", "1"),
                                      formatter=lambda value: str(-24 + 48 * value))
        self.assertValues(parameter, (0, 0.25, 0.5, 0.75, 1))

    def test_formatter_failure_uses_fallback(self):
        def broken_formatter(value):
            raise RuntimeError("Display unavailable")
        self.assertValues(ReadOnlyParameter(formatter=broken_formatter), (0, 0.25, 0.5, 0.75, 1))

    def test_missing_target_label_uses_fallback(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "-24" if value < 0.5 else "24")
        self.assertValues(parameter, (0, 0.25, 0.5, 0.75, 1))

    def test_invalid_ranges_return_no_candidates(self):
        for minimum, maximum in ((0, 0), (2, -2), (float("nan"), 1)):
            with self.subTest(bounds=(minimum, maximum)):
                self.assertEqual(STEPS.stepped_parameter_values(ReadOnlyParameter(minimum, maximum), TRANSPOSE), ())
        for options in ({}, dict(TRANSPOSE, step_size=0), dict(TRANSPOSE, display_min=25)):
            with self.subTest(options=options):
                self.assertEqual(STEPS.stepped_parameter_values(ReadOnlyParameter(), options), ())

    def test_current_pitch_uses_same_discrete_label_for_comparison(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} oct".format(round(2 - 4 * value)))
        candidates = STEPS.stepped_parameter_values(parameter, OCTAVE)
        self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.30), 0.25)
        self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.70), 0.75)

    def test_current_pitch_matches_small_display_conversion_error(self):
        parameter = ReadOnlyParameter(formatter=lambda value: str(24 - 48 * value * value))
        candidates = STEPS.stepped_parameter_values(parameter, TRANSPOSE)
        self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.5 ** 0.5), candidates[2])

    def test_current_pitch_between_octave_candidates_remains_unsnapped(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} st".format(round(24 - 48 * value)))
        candidates = STEPS.stepped_parameter_values(parameter, TRANSPOSE)
        self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.30), 0.30)

    def test_current_pitch_uses_numeric_items_without_a_formatter(self):
        parameter = ReadOnlyParameter(items=("+2 oct", "+1 oct", "0 oct", "-1 oct", "-2 oct"))
        candidates = STEPS.stepped_parameter_values(parameter, OCTAVE)
        self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.30), 0.25)

    def test_same_label_matches_choose_nearest_raw_candidate(self):
        parameter = ReadOnlyParameter(formatter=lambda value: "{} oct".format(round(2 - 4 * value)))
        self.assertEqual(STEPS.current_stepped_value(parameter, (0.20, 0.25, 0.31), 0.30), 0.31)

    def test_current_pitch_without_musical_labels_remains_unsnapped(self):
        for formatter in (None, lambda value: str(value), lambda value: "{}%".format(value * 100)):
            with self.subTest(formatter=formatter):
                parameter = ReadOnlyParameter(formatter=formatter)
                candidates = STEPS.stepped_parameter_values(parameter, OCTAVE)
                self.assertEqual(STEPS.current_stepped_value(parameter, candidates, 0.30), 0.30)


if __name__ == "__main__":
    unittest.main()
