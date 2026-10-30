"""Measured Drive/Output compensation around Live's native control mapping.

The Drive input itself is never written here. The calibrated profile uses Live's
normalized parameter values: Drive -36..36 dB and Output -36..0 dB.
"""

from math import isfinite

from ableton.v3.live import liveobj_valid


# Live 12.4.15: measured against the device-OFF reference, 44.1 kHz,
# pink noise RMS -18 dBFS, Color off, No Clip, Dry/Wet 100%,
# Hi-Quality on, Pre-DC off. Drive 0's positive correction is clamped to 0.
# See diagnostics/SATURATOR_CALIBRATION.md.
ANALOG_CLIP_CURVE = (
    (0.0, 0.0),
    (3.0, -2.990675605074582),
    (6.0, -5.985547524032334),
    (9.0, -8.897638176286074),
    (12.0, -11.471879384789583),
    (15.0, -13.480187475523012),
    (18.0, -14.910258125829028),
    (21.0, -15.87605445941633),
    (24.0, -16.508052892207136),
)
VALUE_TOLERANCE = 1e-6
PARAMETER_NAMES = ("Output", "Type", "Color On", "Post Clip Mode", "Dry/Wet")
ERRORS = (AttributeError, RuntimeError, TypeError, ValueError, OverflowError)


def _validated_curve(curve):
    try:
        points = tuple((float(drive), float(correction)) for drive, correction in curve)
        if (not points or not all(isfinite(value) for point in points for value in point)
                or any(left[0] >= right[0] for left, right in zip(points, points[1:]))):
            return ()
        return points
    except ERRORS:
        return ()


def _correction(drive_db, curve):
    if drive_db <= curve[0][0]:
        return curve[0][1]
    for left, right in zip(curve, curve[1:]):
        if drive_db <= right[0]:
            position = (drive_db - left[0]) / (right[0] - left[0])
            return left[1] + position * (right[1] - left[1])
    return curve[-1][1]


def _unit_value(parameter):
    if not liveobj_valid(parameter):
        return None
    try:
        minimum, maximum, value = float(parameter.min), float(parameter.max), float(parameter.value)
        if (not all(isfinite(number) for number in (minimum, maximum, value))
                or abs(minimum) > VALUE_TOLERANCE or abs(maximum - 1.0) > VALUE_TOLERANCE
                or not -VALUE_TOLERANCE <= value <= 1.0 + VALUE_TOLERANCE):
            return None
        return max(0.0, min(1.0, value))
    except ERRORS:
        return None


def _selected_item(parameter):
    if not liveobj_valid(parameter):
        return None
    try:
        if not parameter.is_quantized:
            return None
        items = tuple(parameter.value_items)
        minimum, maximum, value = float(parameter.min), float(parameter.max), float(parameter.value)
        index = value - minimum
        if (not items or not all(isfinite(number) for number in (minimum, maximum, value))
                or abs(maximum - minimum - (len(items) - 1)) > VALUE_TOLERANCE
                or abs(index - round(index)) > VALUE_TOLERANCE
                or not 0 <= index <= len(items) - 1):
            return None
        return items[int(round(index))]
    except ERRORS:
        return None


def _same(left, right):
    try:
        return len(left) == len(right) and all(a == b for a, b in zip(left, right))
    except ERRORS:
        return False


def _unchanged(left, right):
    return left is not None and right is not None and abs(left - right) <= VALUE_TOLERANCE


class _Listener:
    def __init__(self, parameter, callback):
        self.parameter = parameter
        self.callback = callback
        self.connected = False
        try:
            parameter.add_value_listener(callback)
            self.connected = True
        except ERRORS:
            pass

    def disconnect(self):
        if self.connected:
            try:
                self.parameter.remove_value_listener(self.callback)
            except ERRORS:
                pass
            self.connected = False


class _TargetState:
    def __init__(self, identity, curve, enabled, session=None):
        self.identity = identity
        self.owner, self.drive, self.output, self.type, self.color, self.post_clip, self.wet = identity
        self.curve = curve
        self.enabled = bool(enabled)
        self.closed = False
        self.ready = False
        self.last_drive = None
        self.last_output = None
        self.trim_db = 0.0 if session is None else session[0]
        self.established = False if session is None else session[1]
        self.expected_output = None
        self.input_depth = 0
        self._input_drive = False
        self._input_output = False
        self.listeners = []
        for parameter, callback in (
                (self.drive, self._on_drive), (self.output, self._on_output),
                (self.type, self._on_condition), (self.color, self._on_condition),
                (self.post_clip, self._on_condition), (self.wet, self._on_condition)):
            self.listeners.append(_Listener(parameter, callback))
        # Capture the pre-wake values even when the device is currently off.
        self._anchor()
        self._sync_readiness()

    def matches(self, identity):
        return not self.closed and _same(self.identity, identity)

    def _eligible(self):
        if self.closed or not self.enabled or not self.curve or not liveobj_valid(self.owner):
            return False
        try:
            return bool(
                all(listener.connected for listener in self.listeners)
                and len(self.listeners) == 6
                and self.drive.is_enabled and self.output.is_enabled
                and not self.drive.is_quantized and not self.output.is_quantized
                and self.drive.automation_state == 0 and self.output.automation_state == 0
                and _unit_value(self.drive) is not None and _unit_value(self.output) is not None
                and _selected_item(self.type) == "Analog Clip"
                and _unchanged(_unit_value(self.color), 0.0)
                and _selected_item(self.post_clip) == "No Clip"
                and _unchanged(_unit_value(self.wet), 1.0))
        except ERRORS:
            return False

    def _anchor(self):
        drive, output = _unit_value(self.drive), _unit_value(self.output)
        if drive is None or output is None:
            self._pause()
            return
        # A readiness transition can occur inside auto_bypass's input handling.
        # Keep that input's pre-change snapshot until end_input compares it.
        if not self.input_depth or self.last_drive is None:
            self.last_drive = drive
        if not self.input_depth or self.last_output is None:
            self.last_output = output
        self.expected_output = None

    def _pause(self):
        self.ready = False
        self.expected_output = None

    def _sync_readiness(self):
        eligible = self._eligible()
        if not eligible:
            self._pause()
        elif not self.ready:
            self.ready = True
            self._anchor()
        return self.ready

    def refresh(self, enabled):
        self.enabled = bool(enabled)
        # Do not sample/re-anchor an unchanged target here: refresh can run
        # after Live has changed Drive but before the physical input callback.
        self._sync_readiness()

    def begin_input(self, kind):
        self._sync_readiness()
        if not self.input_depth:
            self._input_drive = False
            self._input_output = False
        self.input_depth += 1
        self._input_drive = self._input_drive or kind == "drive"
        self._input_output = self._input_output or kind == "output"

    def end_input(self):
        if self.input_depth <= 0:
            return
        # Sync while the input context still protects the pre-wake snapshot.
        ready = self._sync_readiness()
        self.input_depth -= 1
        if self.input_depth or not ready:
            return
        drive, output = _unit_value(self.drive), _unit_value(self.output)
        if drive is None or output is None:
            self._pause()
            return
        if self._input_output and not _unchanged(output, self.last_output):
            # An explicitly operated Output control is manual even before the
            # first accepted Drive input. Pickup waiting is not a manual edit.
            self._accept_output(output, drive, explicit=True)
            self.last_drive = drive
            return
        self._accept_output(output, self.last_drive)
        if not self._input_drive:
            self.last_drive = drive
            return
        if _unchanged(drive, self.last_drive):
            return
        # A subsequent Drive notification must not classify this physical
        # change as a mouse edit, including notifications caused by wake-up.
        self.last_drive = drive
        self.established = True
        desired_db = _correction(-36.0 + 72.0 * drive, self.curve) + self.trim_db
        target = max(0.0, min(1.0, (desired_db + 36.0) / 36.0))
        if _unchanged(target, output):
            return
        self.expected_output = target
        self.last_output = target
        try:
            self.output.value = target
            applied = _unit_value(self.output)
            if applied is None:
                self._pause()
            else:
                self.expected_output = applied
                self.last_output = applied
        except ERRORS:
            # Resume from the actual current values on the next refresh/input;
            # never replay a failed compensation write.
            self._pause()

    def _accept_output(self, output, anchor_drive, explicit=False):
        if _unchanged(output, self.expected_output):
            self.expected_output = None
            self.last_output = output
        elif not _unchanged(output, self.last_output):
            self.expected_output = None
            self.last_output = output
            # Saved/restored Output is not a user-selected bypass offset.
            # After compensation starts, independent Output edits remain trim.
            if explicit or self.established:
                self.trim_db = (-36.0 + 36.0 * output
                                - _correction(-36.0 + 72.0 * anchor_drive, self.curve))
                self.established = True

    def _on_drive(self, *unused):
        if self.input_depth or not self._sync_readiness():
            return
        drive = _unit_value(self.drive)
        if drive is not None and not _unchanged(drive, self.last_drive):
            # Mouse Drive edits do not redefine the bypass reference or trim.
            self.last_drive = drive

    def _on_output(self, *unused):
        if self.input_depth or not self._sync_readiness():
            return
        output = _unit_value(self.output)
        drive = _unit_value(self.drive)
        if output is None or drive is None:
            self._pause()
        else:
            self._accept_output(output, drive)

    def _on_condition(self, *unused):
        self._sync_readiness()

    def disconnect(self):
        self.closed = True
        self._pause()
        for listener in self.listeners:
            listener.disconnect()
        self.listeners = []


class SaturatorCompensationManager:
    """Share one compensation state per Drive, regardless of control number."""

    def __init__(self, curve=None):
        self._curve = _validated_curve(ANALOG_CLIP_CURVE if curve is None else curve)
        self._targets = []
        self._controls = {}
        self._inputs = []
        self._sessions = []

    def _prune_sessions(self):
        retained = []
        for identity, trim, established in self._sessions:
            try:
                if all(liveobj_valid(subject) for subject in identity):
                    retained.append((identity, trim, established))
            except ERRORS:
                pass
        self._sessions = retained

    def _remember(self, target):
        self._sessions = [session for session in self._sessions
                          if not _same(session[0], target.identity)]
        try:
            if all(liveobj_valid(subject) for subject in target.identity):
                self._sessions.append((target.identity, target.trim_db, target.established))
        except ERRORS:
            pass

    def _session(self, identity):
        return next(((trim, established) for candidate, trim, established in self._sessions
                     if _same(candidate, identity)), None)

    def refresh(self, resolver, assignments, controls, enabled=True):
        self._prune_sessions()
        identities = []
        candidates = []
        if self._curve:
            for name, entry in assignments.items():
                if (not entry or entry.get("parameter") != "Drive" or "device" not in entry
                        or controls.get(name) is None):
                    continue
                try:
                    identity = (resolver.owner(entry), resolver.resolve(entry)) + tuple(
                        resolver.resolve({"device": entry["device"], "parameter": parameter})
                        for parameter in PARAMETER_NAMES)
                    if not all(liveobj_valid(parameter) for parameter in identity):
                        continue
                    index = next((i for i, item in enumerate(identities) if _same(item, identity)), None)
                    if index is None:
                        index = len(identities)
                        identities.append(identity)
                    candidates.append((name, index, "drive"))
                except ERRORS:
                    continue
            for name, entry in assignments.items():
                if (not entry or entry.get("parameter") != "Output" or "device" not in entry
                        or controls.get(name) is None):
                    continue
                try:
                    owner, output = resolver.owner(entry), resolver.resolve(entry)
                    for index, identity in enumerate(identities):
                        if _same((owner, output), (identity[0], identity[2])):
                            candidates.append((name, index, "output"))
                except ERRORS:
                    continue
        targets = []
        for identity in identities:
            target = next((item for item in self._targets if item.matches(identity)), None)
            targets.append(target)
        for target in self._targets:
            if target not in targets:
                self._remember(target)
                target.disconnect()
        for index, identity in enumerate(identities):
            if targets[index] is None:
                targets[index] = _TargetState(identity, self._curve, enabled,
                                               session=self._session(identity))
            else:
                targets[index].refresh(enabled)
        self._targets = targets
        self._controls = {}
        for name, index, kind in candidates:
            self._controls.setdefault(name, []).append((targets[index], kind))

    def begin_input(self, name):
        bindings = tuple(self._controls.get(name, ()))
        self._inputs.append((name, bindings))
        for target, kind in bindings:
            target.begin_input(kind)

    def end_input(self, name):
        for index in range(len(self._inputs) - 1, -1, -1):
            pending_name, bindings = self._inputs[index]
            if pending_name == name:
                del self._inputs[index]
                for target, _ in reversed(bindings):
                    if not target.closed:
                        target.end_input()
                return

    def suspend(self):
        for target in self._targets:
            self._remember(target)
            target.disconnect()
        self._targets = []
        self._controls = {}
        self._inputs = []
        self._prune_sessions()

    def disconnect(self):
        self.suspend()
        self._sessions = []
