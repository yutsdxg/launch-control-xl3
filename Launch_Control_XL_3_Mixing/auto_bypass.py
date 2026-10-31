"""Endpoint-based Device On actions, independent of device or parameter names."""

from math import isfinite

from ableton.v3.live import liveobj_valid

from .parameter_ranges import effective_bounds

ENDPOINT_TOLERANCE = 1e-6


def _validated_bounds(parameter, bounds):
    if not liveobj_valid(parameter):
        return None
    native = effective_bounds(parameter)
    if native is None:
        return None
    if bounds is None:
        return native
    try:
        if isinstance(bounds, (str, bytes)):
            return None
        minimum, maximum = bounds
        if isinstance(minimum, bool) or isinstance(maximum, bool):
            return None
        minimum, maximum = float(minimum), float(maximum)
        if (not all(isfinite(v) for v in (minimum, maximum))
                or not native[0] <= minimum < maximum <= native[1]):
            return None
        return minimum, maximum
    except (TypeError, ValueError, OverflowError):
        return None


def normalized_value(parameter, value=None, bounds=None):
    resolved = _validated_bounds(parameter, bounds)
    if resolved is None:
        return None
    try:
        minimum, maximum = resolved
        current = float(parameter.value if value is None else value)
        if not isfinite(current):
            return None
        return max(0.0, min(1.0, (current - minimum) / (maximum - minimum)))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return None


def should_bypass(parameter, off_at, value=None, bounds=None):
    normalized = normalized_value(parameter, value, bounds=bounds)
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


def input_target(parameter, value, relative, bounds=None):
    """Preview a wake-up input; faders use this only to detect leaving the endpoint."""
    resolved = _validated_bounds(parameter, bounds)
    if resolved is None:
        return None
    try:
        minimum, maximum = resolved
        current = float(parameter.value)
        if not isfinite(current):
            return None
        if relative:
            delta = value - 64
            step = (maximum - minimum) / 127.0
            if getattr(parameter, "is_quantized", False):
                items = tuple(getattr(parameter, "value_items", ()) or ())
                native_minimum, native_maximum = effective_bounds(parameter)
                step = (native_maximum - native_minimum) / (len(items) - 1) if len(items) > 1 else 1.0
            target = current + delta * step
        else:
            target = minimum + value * (maximum - minimum) / 127.0
        return max(minimum, min(maximum, target))
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError):
        return None
