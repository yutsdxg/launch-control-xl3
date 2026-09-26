"""Resolve musical steps without changing a parameter to inspect its display."""

import math
import re


_NUMBER = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(?:semi(?:tone)?s?|st|oct(?:ave)?s?)?\s*$",
    re.IGNORECASE,
)
_ERRORS = (AttributeError, RuntimeError, TypeError, ValueError, OverflowError)


def _number(text):
    match = _NUMBER.match(str(text).replace("\u2212", "-"))
    value = float(match.group(1)) if match else None
    return value if value is not None and math.isfinite(value) else None


def _grid(lower, upper, step):
    return tuple(index * step for index in range(
        int(math.ceil(lower / step)), int(math.floor(upper / step)) + 1
    ))


def _musical_range(first, last):
    # Some plug-ins only expose the normalized raw value as their display.
    return first != last and (min(first, last), max(first, last)) != (0.0, 1.0)


def _item_numbers(parameter):
    try:
        numbers = tuple(_number(item) for item in getattr(parameter, "value_items", ()))
    except _ERRORS:
        return ()
    if len(numbers) < 2 or None in numbers or not _musical_range(numbers[0], numbers[-1]):
        return ()
    return numbers


def _item_values(parameter, minimum, maximum, step):
    numbers = _item_numbers(parameter)
    return tuple(minimum + index * (maximum - minimum) / (len(numbers) - 1)
                 for index, number in enumerate(numbers)
                 if abs(number / step - round(number / step)) < 1e-7)


def _raw_for_display(format_value, target, minimum, maximum, first, last):
    if target == first:
        return minimum
    if target == last:
        return maximum
    increasing = last > first
    for _ in range(32):
        midpoint = (minimum + maximum) / 2.0
        displayed = _number(format_value(midpoint))
        if displayed is None:
            return None
        if abs(displayed - target) < 1e-7:
            return midpoint
        if (displayed < target) == increasing:
            minimum = midpoint
        else:
            maximum = midpoint
    return None


def _formatted_values(parameter, minimum, maximum, step):
    format_value = parameter.str_for_value
    first, last = _number(format_value(minimum)), _number(format_value(maximum))
    if first is None or last is None or not _musical_range(first, last):
        return ()
    values = tuple(_raw_for_display(format_value, target, minimum, maximum, first, last)
                   for target in _grid(min(first, last), max(first, last), step))
    return tuple(sorted(values)) if None not in values else ()


def stepped_parameter_values(parameter, options):
    """Return raw values in ascending order; direction is the caller's concern."""
    try:
        minimum, maximum = float(parameter.min), float(parameter.max)
        step = float(options["step_size"])
        display_min, display_max = float(options["display_min"]), float(options["display_max"])
        if not all(math.isfinite(value) for value in (minimum, maximum, step, display_min, display_max)):
            return ()
        if maximum <= minimum or step <= 0 or display_max <= display_min:
            return ()
    except _ERRORS + (KeyError,):
        return ()

    for resolve in (_item_values, _formatted_values):
        try:
            values = resolve(parameter, minimum, maximum, step)
            if values:
                return values
        except _ERRORS:
            pass

    return tuple(minimum + (value - display_min) * (maximum - minimum) / (display_max - display_min)
                 for value in _grid(display_min, display_max, step))


def current_stepped_value(parameter, candidates, current):
    """Use the candidate with the same pitch for comparisons, without writing it."""
    try:
        minimum, maximum = float(parameter.min), float(parameter.max)
        if maximum <= minimum:
            return current
        numbers = _item_numbers(parameter)
        if numbers:
            def display_number(raw):
                index = int(round((raw - minimum) * (len(numbers) - 1) / (maximum - minimum)))
                return numbers[min(max(index, 0), len(numbers) - 1)]
        else:
            def display_number(raw):
                return _number(parameter.str_for_value(raw))
            first, last = display_number(minimum), display_number(maximum)
            if first is None or last is None or not _musical_range(first, last):
                return current
        displayed = display_number(current)
        if displayed is None:
            return current
        matches = []
        for candidate in candidates:
            label = display_number(candidate)
            if label is not None and abs(label - displayed) < 1e-7:
                matches.append(candidate)
        return min(matches, key=lambda candidate: abs(candidate - current)) if matches else current
    except _ERRORS:
        return current
