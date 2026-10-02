"""Resolve conditional assignments without probing parameter display values."""

from ableton.v3.live import liveobj_valid

from .custom_parameter_utils import normalize_name


def _control_index(name):
    for prefix, count, offset in (("encoder_", 24, 0), ("fader_", 8, 24), ("button_", 16, 32)):
        if isinstance(name, str) and name.startswith(prefix):
            try:
                number = int(name[len(prefix):])
            except ValueError:
                return None
            return offset + number - 1 if 1 <= number <= count else None
    return None


def bind_overrides(parameters, rules, get_name):
    """Resolve condition references once when the target device is selected."""
    bindings = []
    for rule in rules or ():
        if not isinstance(rule, dict):
            continue
        when = rule.get("when")
        assignments = rule.get("assignments")
        if not isinstance(when, dict) or not isinstance(assignments, dict):
            continue
        try:
            expected = float(when["normalized_value"])
            occurrence = int(when.get("occurrence", 1))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        name = normalize_name(when.get("parameter"))
        if not name or not 0.0 <= expected <= 1.0 or occurrence < 1:
            continue
        # A missing Model must not accidentally match ShapeModel or another name.
        matches = tuple(parameter for parameter in parameters
                        if liveobj_valid(parameter) and normalize_name(get_name(parameter)) == name)
        parameter = matches[occurrence - 1] if occurrence <= len(matches) else None
        entries = tuple((_control_index(control), entry) for control, entry in assignments.items()
                        if _control_index(control) is not None)
        bindings.append((parameter, expected, entries))
    return tuple(bindings)


def matching_overrides(bindings):
    """Read only the selectors' current values; never enumerate or format values."""
    matching = []
    values = []
    unread = object()
    for index, (parameter, expected, _) in enumerate(bindings):
        if not liveobj_valid(parameter):
            continue
        # Several rules can share a selector; read that Live object only once.
        normalized = next((value for candidate, value in values if candidate == parameter), unread)
        if normalized is unread:
            normalized = None
            try:
                minimum = float(parameter.min)
                maximum = float(parameter.max)
                current = float(parameter.value)
                if (getattr(parameter, "is_enabled", True)
                        and maximum > minimum and minimum <= current <= maximum):
                    normalized = (current - minimum) / (maximum - minimum)
            except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
                pass
            values.append((parameter, normalized))
        if normalized is not None and abs(normalized - expected) <= 1e-6:
            matching.append(index)
    return tuple(matching)


def apply_overrides(base_order, bindings, matching):
    if base_order is None:
        return None
    order = list(base_order)
    for index in matching:
        for slot, entry in bindings[index][2]:
            if slot >= len(order):
                order.extend([None] * (slot + 1 - len(order)))
            order[slot] = entry
    return tuple(order)
