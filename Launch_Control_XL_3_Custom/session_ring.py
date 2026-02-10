import math
from ableton.v3.control_surface.components import SessionRingComponent as SessionRingComponentBase

class SessionRingComponent(SessionRingComponentBase):
    def __init__(self, *a, **k):
        self._is_controlling_returns = False
        super().__init__(*a, **k)

    @property
    def can_control_returns(self):
        return bool(self.song.return_tracks)

    @property
    def is_controlling_returns(self):
        return self._is_controlling_returns

    @is_controlling_returns.setter
    def is_controlling_returns(self, control_returns):
        control_returns = self.can_control_returns and control_returns
        if control_returns != self._is_controlling_returns:
            self._is_controlling_returns = control_returns
            self._update_tracks_to_use()

    def _update_tracks_to_use(self):
        self._tracks_to_use = (
            lambda: self.song.return_tracks
            if self._is_controlling_returns
            else self.song.visible_tracks
        )
        self._update_track_list()
        if self._is_controlling_returns:
            self.track_offset = 0
            return
        last_bank_index = math.ceil(len(self.tracks_to_use()) / self.num_tracks) - 1
        self.track_offset = last_bank_index * self.num_tracks

    def _update_track_list(self):
        if self._is_controlling_returns and not self.can_control_returns:
            self.is_controlling_returns = False
            return
        super()._update_track_list()
