"""Endpoint-based Device On actions, independent of device or parameter names."""

from math import isfinite

from ableton.v3.live import liveobj_valid

ENDPOINT_TOLERANCE = 1e-6


def normalized_value(parameter, value=None):
    if not liveobj_valid(parameter):
        return None
    try:
        minimum, maximum = float(parameter.min), float(parameter.max)
        current = float(parameter.value if value is None else value)
        if not all(isfinite(v) for v in (minimum, maximum, current)) or maximum <= minimum:
            return None
        return max(0.0, min(1.0, (current - minimum) / (maximum - minimum)))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return None


def should_bypass(parameter, off_at, value=None):
    normalized = normalized_value(parameter, value)
    if normalized is None:
        return None
    return (normalized <= ENDPOINT_TOLERANCE if off_at == "min"
            else normalized >= 1.0 - ENDPOINT_TOLERANCE)


def device_is_off(parameter):
    normalized = normalized_value(parameter)
    return normalized is not None and normalized <= 0.5


def set_device_enabled(parameter, enabled):
    normalized = normalized_value(parameter)
    if normalized is None:
        return False
    try:
        if not getattr(parameter, "is_enabled", True):
            return False
        target = parameter.max if enabled else parameter.min
        if abs(normalized - float(enabled)) > ENDPOINT_TOLERANCE:
            parameter.value = target
        return True
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False


def input_target(parameter, value, relative):
    """Preview a wake-up input; faders use this only to detect leaving the endpoint."""
    if normalized_value(parameter) is None:
        return None
    try:
        minimum, maximum, current = float(parameter.min), float(parameter.max), float(parameter.value)
        if relative:
            delta = value - 64
            step = (maximum - minimum) / 127.0
            if getattr(parameter, "is_quantized", False):
                items = tuple(getattr(parameter, "value_items", ()) or ())
                step = (maximum - minimum) / (len(items) - 1) if len(items) > 1 else 1.0
            target = current + delta * step
        else:
            target = minimum + value * (maximum - minimum) / 127.0
        return max(minimum, min(maximum, target))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
