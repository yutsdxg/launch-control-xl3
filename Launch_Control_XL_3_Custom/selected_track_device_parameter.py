from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from .custom_parameter_utils import DEVICE_ON_PARAMETER_NAME

TARGET_DEVICE_INDEX = 3
TARGET_PARAMETER_INDEX = 1
ASSIGNMENT_UPDATE_INTERVAL = 0.1


class SelectedTrackDeviceParameterComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._fader = None
        self._connected_parameter = None
        self._assignment_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_assignment),
                    task.delay(ASSIGNMENT_UPDATE_INTERVAL),
                )
            )
        )

    def set_fader(self, fader):
        if self._fader is not fader:
            self._release_fader()
        self._fader = fader
        self._update_assignment()

    def _update_assignment(self):
        parameter = self._target_parameter()
        if parameter is self._connected_parameter and self._parameter_is_enabled(parameter):
            return
        self._release_fader()
        if self._fader is None or not self._parameter_is_enabled(parameter):
            return
        try:
            self._fader.connect_to(parameter)
        except RuntimeError:
            return
        self._connected_parameter = parameter

    def _release_fader(self):
        self._connected_parameter = None
        if self._fader is None:
            return
        try:
            self._fader.release_parameter()
        except RuntimeError:
            pass

    def _target_parameter(self):
        track = self._selected_track()
        if not liveobj_valid(track):
            return None
        try:
            devices = tuple(track.devices)
        except (AttributeError, RuntimeError):
            return None
        if len(devices) <= TARGET_DEVICE_INDEX:
            return None
        device = devices[TARGET_DEVICE_INDEX]
        if not liveobj_valid(device):
            return None
        parameters = self._assignable_parameters(device)
        if len(parameters) <= TARGET_PARAMETER_INDEX:
            return None
        return parameters[TARGET_PARAMETER_INDEX]

    def _selected_track(self):
        try:
            track = self.song.view.selected_track
        except (AttributeError, RuntimeError):
            return None
        return track if liveobj_valid(track) else None

    def _assignable_parameters(self, device):
        try:
            parameters = tuple(device.parameters)
        except (AttributeError, RuntimeError):
            return ()
        assignable = []
        for parameter in parameters:
            if not liveobj_valid(parameter):
                continue
            try:
                if getattr(parameter, "name", "") == DEVICE_ON_PARAMETER_NAME:
                    continue
            except RuntimeError:
                continue
            assignable.append(parameter)
        return tuple(assignable)

    def _parameter_is_enabled(self, parameter):
        if not liveobj_valid(parameter):
            return False
        try:
            return getattr(parameter, "is_enabled", True)
        except RuntimeError:
            return False

    def disconnect(self):
        self._release_fader()
        try:
            super().disconnect()
        except AttributeError:
            pass
