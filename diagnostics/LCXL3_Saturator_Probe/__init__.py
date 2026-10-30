"""Optional observer for native Drive changes and forwarded controller input.

Load with both MIDI ports set to None alongside Launch_Control_XL_3_Mixing.
This surface only reads existing targets and installs/removes value listeners.
It never maps a control, sets a parameter, sends MIDI, or injects MIDI input.
"""

import json
import logging
import time

from ableton.v2.base import task
from ableton.v2.control_surface import ControlSurface


LOGGER = logging.getLogger(__name__)
PREFIX = "LCXL3_SATURATOR_PROBE "
PROBE_INTERVAL = 0.1


def create_instance(c_instance):
    return SaturatorInputProbe(c_instance=c_instance)


def _read(subject, name):
    try:
        return getattr(subject, name)
    except (AttributeError, RuntimeError) as error:
        return {"error": repr(error)}


def _describe_parameter(parameter, index=None):
    if parameter is None:
        return None
    result = {"index": index, "object": repr(parameter)}
    for name in ("name", "original_name", "min", "max", "value",
                 "is_enabled", "is_quantized", "automation_state", "state"):
        result[name] = _read(parameter, name)
    try:
        result["value_items"] = list(parameter.value_items)
    except (AttributeError, RuntimeError, TypeError) as error:
        result["value_items"] = {"error": repr(error)}
    try:
        result["display"] = str(parameter)
    except (RuntimeError, TypeError) as error:
        result["display"] = {"error": repr(error)}
    return result


class _ValueListener:
    def __init__(self, subject, callback):
        self.subject = subject
        self.callback = callback
        self.connected = False
        self.error = None
        try:
            subject.add_value_listener(callback)
            self.connected = True
        except (AttributeError, RuntimeError) as error:
            self.error = repr(error)

    def disconnect(self):
        if self.connected:
            try:
                self.subject.remove_value_listener(self.callback)
            except (AttributeError, RuntimeError):
                pass
            self.connected = False


class _DriveBinding:
    def __init__(self, probe, component, owner, drive, controls):
        self.probe = probe
        self.component = component
        self.owner = owner
        self.drive = drive
        self.controls = tuple(controls)
        self.last_drive_value = _read(drive, "value")
        self.closed = False
        self.listeners = [_ValueListener(drive, self._on_drive_value)]
        for name, control, entry in self.controls:
            self.listeners.append(_ValueListener(
                control, self._control_callback(name, entry)))
        self.probe._emit("bind", **self.snapshot(), listeners=[{
            "connected": listener.connected, "error": listener.error,
        } for listener in self.listeners])
        self._log_parameters()

    def matches(self, component, owner, drive, controls):
        return (self.component is component and self.owner == owner
                and self.drive == drive and self.controls == tuple(controls))

    def _control_callback(self, name, entry):
        def callback(value, *unused):
            if not self.closed:
                self.probe._event_count += 1
                self.probe._emit("control_input", control=name, midi_value=value,
                                 assignment=dict(entry), **self.snapshot())
        return callback

    def _on_drive_value(self, *unused):
        if self.closed:
            return
        previous = self.last_drive_value
        self.last_drive_value = _read(self.drive, "value")
        self.probe._event_count += 1
        self.probe._emit("drive_value", previous=previous,
                         current=self.last_drive_value, **self.snapshot())

    def snapshot(self):
        output = None
        try:
            number = self.controls[0][2]["device"]
            output = self.component._resolver.resolve({
                "device": number, "parameter": "Output"})
        except (AttributeError, RuntimeError, IndexError, KeyError):
            pass
        track = _read(self.component._resolver, "track")
        return {
            "component": repr(self.component),
            "active": _read(self.component, "_active"),
            "shift": _read(self.component, "_shift_pressed"),
            "locked": _read(self.component, "_locked"),
            "track": {"object": repr(track), "name": _read(track, "name")},
            "owner": {"object": repr(self.owner),
                      "name": _read(self.owner, "name"),
                      "class_name": _read(self.owner, "class_name")},
            "controls": [name for name, _, _ in self.controls],
            "drive": _describe_parameter(self.drive),
            "output": _describe_parameter(output),
        }

    def _log_parameters(self):
        try:
            parameters = tuple(self.owner.parameters)
        except (AttributeError, RuntimeError) as error:
            self.probe._emit("parameters_error", owner=repr(self.owner), error=repr(error))
            return
        for index, parameter in enumerate(parameters):
            self.probe._emit("parameter", owner=repr(self.owner),
                             parameter=_describe_parameter(parameter, index))

    def disconnect(self):
        if self.closed:
            return
        self.closed = True
        for listener in self.listeners:
            listener.disconnect()
        self.listeners = []
        self.probe._emit("unbind", owner=repr(self.owner),
                         controls=[name for name, _, _ in self.controls])


class SaturatorInputProbe(ControlSurface):
    @staticmethod
    def log_message(message):
        LOGGER.info(message)

    def __init__(self, *args, **kwargs):
        self._probe_started = time.monotonic()
        self._sequence = 0
        self._probe_tick = 0
        self._event_count = 0
        self._probe_scripts = ()
        self._bindings = []
        self._closed = False
        self._last_status = None
        super().__init__(*args, **kwargs)
        self._emit("start", interval_seconds=PROBE_INTERVAL,
                   purpose="observe only; MIDI ports must both be None")
        self._tasks.add(task.loop(task.sequence(
            task.delay(PROBE_INTERVAL), task.run(self._tick))))

    def _emit(self, event, **fields):
        self._sequence += 1
        record = {"seq": self._sequence,
                  "t_ms": round((time.monotonic() - self._probe_started) * 1000.0, 6),
                  "probe_tick": self._probe_tick, "event": event}
        record.update(fields)
        self.log_message(PREFIX + json.dumps(record, ensure_ascii=False, default=repr))

    def connect_script_instances(self, instanciated_scripts):
        super().connect_script_instances(instanciated_scripts)
        self._probe_scripts = tuple(script for script in instanciated_scripts if script is not self)
        self._refresh_bindings()

    def _target_groups(self):
        groups = []
        for script in self._probe_scripts:
            try:
                # ComponentMap.get can instantiate lazy components. Inspect only
                # the underlying v3 dict, without invoking that factory path.
                component_map = script.component_map
                if not isinstance(component_map, dict):
                    continue
                component = dict.get(component_map, "Fixed_Assignments")
                if component is None or type(component).__name__ != "ConfiguredMixingAssignmentsComponent":
                    continue
                assignments = component._assignments
                resolver = component._resolver
                controls = component._controls
                for name, entry in assignments.items():
                    if not entry or entry.get("parameter") != "Drive" or "device" not in entry:
                        continue
                    control = controls.get(name)
                    drive = resolver.resolve(entry)
                    owner = resolver.owner(entry)
                    if control is None or drive is None or owner is None:
                        continue
                    group = next((candidate for candidate in groups
                                  if candidate[0] is component and candidate[1] == owner
                                  and candidate[2] == drive), None)
                    if group is None:
                        group = [component, owner, drive, []]
                        groups.append(group)
                    group[3].append((name, control, dict(entry)))
            except (AttributeError, KeyError, RuntimeError):
                continue
        return groups

    def _refresh_bindings(self):
        groups = self._target_groups()
        retained = []
        for group in groups:
            binding = next((candidate for candidate in self._bindings
                            if candidate.matches(*group)), None)
            if binding is not None:
                retained.append(binding)
        for binding in self._bindings:
            if binding not in retained:
                binding.disconnect()
        self._bindings = retained
        for group in groups:
            if not any(binding.matches(*group) for binding in self._bindings):
                self._bindings.append(_DriveBinding(self, *group))
        status = "observing" if self._bindings else "waiting_for_configured_drive_assignment"
        if status != self._last_status:
            self._last_status = status
            self._emit("status", status=status, drive_targets=len(self._bindings))

    def _tick(self):
        if self._closed:
            return
        self._probe_tick += 1
        if self._event_count:
            count, self._event_count = self._event_count, 0
            self._emit("task_boundary", input_and_value_events=count,
                       targets=[binding.snapshot() for binding in self._bindings])
        self._refresh_bindings()

    def disconnect(self):
        self._closed = True
        for binding in self._bindings:
            binding.disconnect()
        self._bindings = []
        self._probe_scripts = ()
        self._emit("stop")
        super().disconnect()
