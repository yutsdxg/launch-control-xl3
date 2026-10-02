"""Bind companion controls without probing parameter display strings."""

from ableton.v3.live import liveobj_valid

from .custom_parameter_utils import extract_custom_entry_name_and_options, normalize_name


def _encoder_options(order):
    for index, entry in enumerate((order or ())[:24]):
        _, options = extract_custom_entry_name_and_options(entry)
        if isinstance(options, dict):
            yield "encoder_{}".format(index + 1), options


def _action_entries(value):
    if isinstance(value, dict):
        return (value,)
    return value if isinstance(value, (tuple, list)) else ()


def _resolve_target(parameters, action, get_name):
    try:
        occurrence = int(action.get("occurrence", 1))
    except (TypeError, ValueError, OverflowError):
        return None
    name = normalize_name(action.get("parameter"))
    if not name or occurrence < 1:
        return None
    # A missing companion must never bind a similarly named parameter.
    matches = tuple(parameter for parameter in parameters
                    if liveobj_valid(parameter) and normalize_name(get_name(parameter)) == name)
    return matches[occurrence - 1] if occurrence <= len(matches) else None


def bind_left_turn_actions(parameters, order, get_name):
    """Resolve exact names once; accept a single action or a list of actions."""
    bindings = {}
    for name, options in _encoder_options(order):
        targets = []
        for action in _action_entries(options.get("on_left")):
            if not isinstance(action, dict):
                continue
            try:
                normalized = float(action["normalized_value"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not 0.0 <= normalized <= 1.0:
                continue
            parameter = _resolve_target(parameters, action, get_name)
            if parameter is not None:
                targets.append((parameter, normalized))
        if targets:
            bindings[name] = tuple(targets)
    return bindings


def bind_relative_targets(parameters, order, get_name):
    """Additional targets use independent current values and continuous steps."""
    bindings = {}
    for name, options in _encoder_options(order):
        targets = []
        for action in _action_entries(options.get("relative_targets")):
            if not isinstance(action, dict):
                continue
            parameter = _resolve_target(parameters, action, get_name)
            if parameter is not None and not any(target == parameter for target, _ in targets):
                # Only direction is shared with the continuous input path;
                # never inherit the primary's discrete steps or input counter.
                targets.append((parameter, {"invert_direction": bool(action.get("invert_direction"))}))
        if targets:
            bindings[name] = tuple(targets)
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
