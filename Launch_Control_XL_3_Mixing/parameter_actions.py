"""Bind fixed companion values without probing parameter display strings."""

from ableton.v3.live import liveobj_valid

from .custom_parameter_utils import extract_custom_entry_name_and_options, normalize_name


def bind_left_turn_actions(parameters, order, get_name):
    """Resolve exact names once when the effective encoder assignments change."""
    bindings = {}
    for index, entry in enumerate((order or ())[:24]):
        _, options = extract_custom_entry_name_and_options(entry)
        action = options.get("on_left") if isinstance(options, dict) else None
        if not isinstance(action, dict):
            continue
        try:
            normalized = float(action["normalized_value"])
            occurrence = int(action.get("occurrence", 1))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        name = normalize_name(action.get("parameter"))
        if not name or not 0.0 <= normalized <= 1.0 or occurrence < 1:
            continue
        # A missing companion must never bind a similarly named parameter.
        matches = tuple(parameter for parameter in parameters
                        if liveobj_valid(parameter) and normalize_name(get_name(parameter)) == name)
        if occurrence <= len(matches):
            bindings["encoder_{}".format(index + 1)] = (matches[occurrence - 1], normalized)
    return bindings


def apply_left_turn_action(binding):
    if binding is None:
        return
    parameter, normalized = binding
    if not liveobj_valid(parameter):
        return
    try:
        if not getattr(parameter, "is_enabled", True):
            return
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
        if maximum <= minimum:
            return
        target = minimum + (maximum - minimum) * normalized
        # Compare in normalized units, allowing float32 readback rounding.
        if abs(target - current) / (maximum - minimum) > 1e-7:
            parameter.value = target
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        pass
