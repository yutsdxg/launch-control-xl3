"""Bounded controller calculations; this module never writes Live parameters."""

from math import ceil, floor, isfinite


ERRORS = (AttributeError, RuntimeError, TypeError, ValueError, OverflowError)
TAKEOVER_MODES = ("value_scaling", "pickup", "none")
PICKUP_TOLERANCE = 1.0 / 127.0


def _minimum(value):
    if type(value) not in (int, float):
        return None
    return float(value) if 0.0 <= value <= 1.0 and isfinite(value) else None


def is_bounded(entry):
    if not isinstance(entry, dict):
        return False
    minimum = _minimum(entry.get("min", 0.0))
    return minimum is not None and minimum > 0.0


def _profile(parameter, minimum):
    minimum = _minimum(minimum)
    if parameter is None or minimum is None:
        return None
    try:
        native_min, native_max = float(parameter.min), float(parameter.max)
        width = native_max - native_min
        if (not all(isfinite(value) for value in (native_min, native_max, width))
                or width <= 0.0):
            return None
        lower = native_min + width * minimum
        step = None
        if getattr(parameter, "is_quantized", False):
            try:
                items = tuple(parameter.value_items or ())
            except ERRORS:
                items = ()
            step = width / (len(items) - 1) if len(items) > 1 else 1.0
            if not isfinite(step) or step <= 0.0:
                return None
            # Subtract a small tolerance only when rounding a discrete index.
            index = ceil((lower - native_min) / step - 1e-10)
            lower = max(native_min, min(native_max, native_min + index * step))
        if lower >= native_max:
            return None
        return native_min, native_max, lower, step
    except ERRORS:
        return None


def effective_bounds(parameter, entry=None):
    """Return real parameter units after a normalized lower bound is applied."""
    if entry is not None and not isinstance(entry, dict):
        return None
    profile = _profile(parameter, (entry or {}).get("min", 0.0))
    return (profile[2], profile[1]) if profile is not None else None


class ParameterRangeControl:
    """Scale absolute/relative CCs into a parameter's configured upper range.

    A returned target must be acknowledged with applied(actual_value), including
    a quantized no-op. This preserves fractional scaling progress while still
    detecting external changes or an unexpected value accepted by Live.
    """

    def __init__(self, parameter, relative, minimum=0.0, takeover="value_scaling"):
        self.parameter = parameter
        self.relative = bool(relative)
        self.minimum = minimum
        self.takeover = takeover
        self.reset()

    def reset(self):
        self._profile = None
        self._previous_input = None
        self._virtual = None
        self._known_actual = None
        self._pending_target = None
        self._picked_up = False

    def _normalize(self, value):
        _, upper, lower, _ = self._profile
        return max(0.0, min(1.0, (value - lower) / (upper - lower)))

    def _tolerance(self):
        native_min, native_max, _, _ = self._profile
        # Live can round a successful write to float32. A restricted range must
        # not shrink the tolerance below that native parameter's precision.
        magnitude = max(abs(native_min), abs(native_max))
        return max(1e-12, (native_max - native_min) * 1e-7, magnitude * 2.0 ** -24)

    def _close(self, left, right):
        return left is not None and right is not None and abs(left - right) <= self._tolerance()

    def _rearm(self, actual):
        self._previous_input = None
        self._virtual = self._normalize(actual)
        self._known_actual = actual
        self._pending_target = None
        self._picked_up = False

    def _target(self, actual):
        native_min, upper, lower, step = self._profile
        actual = max(lower, min(upper, actual))
        if step is not None:
            index = floor((actual - native_min) / step + 0.5)
            actual = native_min + index * step
        target = max(lower, min(upper, actual))
        self._pending_target = target
        return target

    def input_target(self, value):
        if type(value) is not int or not 0 <= value <= 127 or (self.relative and value == 64):
            return None
        if self.takeover not in TAKEOVER_MODES:
            return None
        profile = _profile(self.parameter, self.minimum)
        if profile is None:
            self.reset()
            return None
        try:
            actual = float(self.parameter.value)
            if not isfinite(actual):
                self.reset()
                return None
        except ERRORS:
            self.reset()
            return None
        if profile != self._profile:
            self._profile = profile
            self._rearm(actual)
        elif self._pending_target is not None or not self._close(actual, self._known_actual):
            # An unacknowledged proposal is discarded rather than replayed.
            self._rearm(actual)
        _, upper, lower, step = profile
        if self.relative:
            base = max(lower, min(upper, actual))
            amount = step if step is not None else (upper - lower) / 127.0
            return self._target(base + (value - 64) * amount)
        position = value / 127.0
        if self.takeover == "none":
            self._previous_input = position
            self._virtual = position
            return self._target(lower + (upper - lower) * position)
        if actual < lower - self._tolerance() or actual > upper + self._tolerance():
            # Enforce the floor on an input, never at bind/reset time. Further
            # motion starts scaling/pickup from this physical position.
            self._previous_input = position
            self._virtual = self._normalize(actual)
            return self._target(max(lower, min(upper, actual)))
        previous = self._previous_input
        self._previous_input = position
        if self.takeover == "pickup":
            current = self._normalize(actual)
            if not self._picked_up:
                near = abs(position - current) <= PICKUP_TOLERANCE + 1e-12
                crossed = previous is not None and (previous - current) * (position - current) <= 0.0
                self._picked_up = near or crossed
                if not self._picked_up:
                    return None
            self._virtual = position
            return self._target(lower + (upper - lower) * position)
        if previous is None:
            return None
        delta = position - previous
        if delta > 0.0 and previous < 1.0:
            self._virtual += delta * (1.0 - self._virtual) / (1.0 - previous)
        elif delta < 0.0 and previous > 0.0:
            self._virtual += delta * self._virtual / previous
        else:
            return None
        self._virtual = max(0.0, min(1.0, self._virtual))
        return self._target(lower + (upper - lower) * self._virtual)

    def applied(self, actual_value):
        """Acknowledge a successful/no-op write without losing virtual motion."""
        try:
            actual = float(actual_value)
            if not isfinite(actual) or self._profile is None:
                self.reset()
                return
        except ERRORS:
            self.reset()
            return
        if self._pending_target is not None:
            if self._close(actual, self._pending_target):
                self._known_actual = actual
                self._pending_target = None
            else:
                self._rearm(actual)
        elif not self._close(actual, self._known_actual):
            self._rearm(actual)
        else:
            self._pending_target = None
