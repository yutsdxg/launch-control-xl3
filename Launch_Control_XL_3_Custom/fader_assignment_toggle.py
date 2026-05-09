from ableton.v3.control_surface import Component
from ableton.v3.live import liveobj_valid
from .colors import Rgb

ASSIGNMENT_CUE = 0
ASSIGNMENT_LOOPCLOUD = 1
DEFAULT_ASSIGNMENT = ASSIGNMENT_LOOPCLOUD
LOOPCLOUD_TRACK_NAME = "Loopcloud"
ASSIGNMENT_1_LED_VALUE = Rgb.WHITE_DIM.midi_value
ASSIGNMENT_2_LED_VALUE = Rgb.YELLOW.midi_value


class FaderAssignmentToggleComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._fader = None
        self._toggle_button = None
        self._toggle_button_slot = None
        self._assignment = DEFAULT_ASSIGNMENT
        self._last_led_value = None

    def set_fader(self, fader):
        if self._fader is not None and self._fader is not fader:
            self._release_fader()
        self._fader = fader
        self._apply_assignment()

    def set_toggle_button(self, button):
        if self._toggle_button_slot is not None:
            self._toggle_button_slot.disconnect()
            self._toggle_button_slot = None
        self._toggle_button = button
        self._last_led_value = None
        if button is not None:
            self._toggle_button_slot = self.register_slot(button, self._on_toggle_button_value, "value")
        self._update_led(force=True)

    def refresh_led_feedback(self):
        self._last_led_value = None
        self._update_led(force=True)

    def _on_toggle_button_value(self, value):
        if value > 0:
            self._assignment = ASSIGNMENT_LOOPCLOUD if self._assignment == ASSIGNMENT_CUE else ASSIGNMENT_CUE
            self._apply_assignment()
        self._update_led(force=True)

    def _apply_assignment(self):
        if self._fader is None:
            return
        self._release_fader()
        parameter = self._target_parameter()
        if not liveobj_valid(parameter):
            return
        if not getattr(parameter, "is_enabled", True):
            return
        try:
            self._fader.connect_to(parameter)
        except RuntimeError:
            return

    def _release_fader(self):
        if self._fader is None:
            return
        try:
            self._fader.release_parameter()
        except RuntimeError:
            pass

    def _target_parameter(self):
        if self._assignment == ASSIGNMENT_LOOPCLOUD:
            return self._loopcloud_track_volume_parameter()
        return self._cue_volume_parameter()

    def _cue_volume_parameter(self):
        try:
            master_track = self.song.master_track
            mixer_device = master_track.mixer_device
            return mixer_device.cue_volume
        except (AttributeError, RuntimeError):
            return None

    def _loopcloud_track_volume_parameter(self):
        try:
            tracks = tuple(self.song.tracks)
        except (AttributeError, RuntimeError):
            tracks = ()
        for track in tracks:
            try:
                if track.name == LOOPCLOUD_TRACK_NAME:
                    return self._track_volume_parameter(track)
            except RuntimeError:
                continue
        if tracks:
            return self._track_volume_parameter(tracks[0])
        return None

    def _track_volume_parameter(self, track):
        try:
            return track.mixer_device.volume
        except (AttributeError, RuntimeError):
            return None

    def _update_led(self, force=False):
        button = self._toggle_button
        if button is None:
            return
        led_value = self._led_value()
        if not force and self._last_led_value == led_value:
            return
        try:
            button.send_value(led_value)
            self._last_led_value = led_value
        except RuntimeError:
            return

    def _led_value(self):
        return ASSIGNMENT_2_LED_VALUE if self._assignment == ASSIGNMENT_LOOPCLOUD else ASSIGNMENT_1_LED_VALUE
