"""Validate Mixing configuration and cache named parameters on the selected track."""

import logging

from ableton.v3.live import liveobj_valid

from .track_resolver import selected_track

LOGGER = logging.getLogger(__name__)
CONTROL_NAMES = tuple("encoder_{}".format(i) for i in range(1, 25)) + tuple(
    "fader_{}".format(i) for i in range(1, 9)
)


def _positive_integer(value):
    return type(value) is int and value >= 1


def validate_assignments(raw):
    """Invalid entries fail independently, rather than disabling all controls."""
    assignments = dict.fromkeys(CONTROL_NAMES)
    if not isinstance(raw, dict):
        LOGGER.warning("LCXL3 Mixing: MIXING_ASSIGNMENTS must be a dictionary")
        return assignments
    for name, entry in raw.items():
        if name not in assignments:
            LOGGER.warning("LCXL3 Mixing: unknown control %r", name)
            continue
        if entry is None:
            continue
        valid = isinstance(entry, dict)
        if valid and "device" in entry:
            valid = (
                set(entry) <= {"device", "parameter", "occurrence", "directional_on_off"}
                and _positive_integer(entry["device"])
                and isinstance(entry.get("parameter"), str)
                and bool(entry["parameter"].strip())
                and _positive_integer(entry.get("occurrence", 1))
            )
        elif valid:
            valid = (
                set(entry) <= {"mixer", "send", "directional_on_off"}
                and entry.get("mixer") in ("volume", "pan", "send", "cue_volume")
                and (_positive_integer(entry.get("send")) if entry.get("mixer") == "send"
                     else "send" not in entry)
            )
        if valid and "directional_on_off" in entry:
            valid = name.startswith("encoder_") and type(entry["directional_on_off"]) is bool
        if valid:
            assignments[name] = dict(entry)
        else:
            LOGGER.warning("LCXL3 Mixing: invalid assignment for %s: %r", name, entry)
    return assignments


class _Listener:
    """Own structural Live listeners separately from the parameter value slots."""

    def __init__(self, subject, event, callback):
        self.subject = subject
        self.event = event
        self.callback = callback
        self.connected = False
        try:
            getattr(subject, "add_{}_listener".format(event))(callback)
            self.connected = True
        except (AttributeError, RuntimeError):
            pass

    def disconnect(self):
        if self.connected:
            try:
                getattr(self.subject, "remove_{}_listener".format(self.event))(self.callback)
            except (AttributeError, RuntimeError):
                pass
            self.connected = False


class _DeviceParameters:
    def __init__(self, device, on_change):
        self.device = device
        self.parameters = ()
        self.named = {}
        self.dirty = True
        self._on_change = on_change
        self.listener = _Listener(device, "parameters", self._invalidate)

    def _invalidate(self, *a):
        self.dirty = True
        self._on_change()

    def refresh(self):
        # Real Live devices notify Configure/list changes. Unsupported subjects
        # fall back to one read per device/update, never one read per control.
        if self.dirty or not self.listener.connected:
            try:
                self.parameters = tuple(self.device.parameters)
            except (AttributeError, RuntimeError):
                self.parameters = ()
            self.dirty = False
        self.named = {}
        for parameter in self.parameters:
            if not liveobj_valid(parameter):
                continue
            try:
                self.named.setdefault(parameter.name, []).append(parameter)
            except (AttributeError, RuntimeError):
                continue

    def disconnect(self):
        self.listener.disconnect()


class MixingTargetResolver:
    def __init__(self, on_change):
        self._on_change = on_change
        self.track = None
        self.master_track = None
        self._view_listener = None
        self._devices_listener = None
        self._device_parameters = {}
        self._devices = ()

    def refresh(self, song, assignments):
        try:
            self.master_track = song.master_track
        except (AttributeError, RuntimeError):
            self.master_track = None
        view = getattr(song, "view", None)
        if self._view_listener is None or self._view_listener.subject != view:
            if self._view_listener is not None:
                self._view_listener.disconnect()
            self._view_listener = _Listener(view, "selected_track", self._on_change)
        track = selected_track(song)
        if track != self.track:
            self._clear_devices()
            if self._devices_listener is not None:
                self._devices_listener.disconnect()
            self.track = track
            self._devices_listener = _Listener(track, "devices", self._on_change)
        try:
            self._devices = tuple(track.devices) if liveobj_valid(track) else ()
        except (AttributeError, RuntimeError):
            self._devices = ()
        numbers = {entry["device"] for entry in assignments.values() if entry and "device" in entry}
        for number in set(self._device_parameters) | numbers:
            device = self.device(number) if number in numbers else None
            cached = self._device_parameters.get(number)
            if cached is not None and cached.device != device:
                cached.disconnect()
                del self._device_parameters[number]
                cached = None
            if liveobj_valid(device):
                if cached is None:
                    cached = _DeviceParameters(device, self._on_change)
                    self._device_parameters[number] = cached
                cached.refresh()

    def device(self, number):
        return self._devices[number - 1] if number <= len(self._devices) else None

    def resolve(self, entry):
        if entry is None:
            return None
        if entry.get("mixer") == "cue_volume":
            try:
                return self.master_track.mixer_device.cue_volume
            except (AttributeError, RuntimeError):
                return None
        if not liveobj_valid(self.track):
            return None
        if "device" in entry:
            cached = self._device_parameters.get(entry["device"])
            matches = cached.named.get(entry["parameter"], ()) if cached is not None else ()
            index = entry.get("occurrence", 1) - 1
            return matches[index] if index < len(matches) else None
        try:
            mixer = self.track.mixer_device
            if entry["mixer"] == "send":
                sends = tuple(mixer.sends)
                index = entry["send"] - 1
                return sends[index] if index < len(sends) else None
            return getattr(mixer, "panning" if entry["mixer"] == "pan" else "volume")
        except (AttributeError, RuntimeError):
            return None

    def owner(self, entry):
        if "device" in entry:
            return self.device(entry["device"])
        return self.master_track if entry["mixer"] == "cue_volume" else self.track

    def _clear_devices(self):
        for cached in self._device_parameters.values():
            cached.disconnect()
        self._device_parameters.clear()

    def disconnect(self):
        self._clear_devices()
        for listener in (self._view_listener, self._devices_listener):
            if listener is not None:
                listener.disconnect()
        self._view_listener = self._devices_listener = None
        self.track = None
        self.master_track = None
        self._devices = ()
