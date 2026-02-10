from ableton.v3.control_surface.components import MixerComponent as MixerComponentBase
from ableton.v3.control_surface.components import SendIndexControlComponent as SendIndexControlComponentBase

SEND_RANGE_SINGLE_FORMAT = "{}\n-"
SEND_RANGE_PAIR_FORMAT = "{}\n{}"
NOTIFICATION_SENDS_FORMAT = "Sends\n{}"


class SendIndexControlComponent(SendIndexControlComponentBase):
    
    def _get_send_range_string(self):
        send_index = self.send_index
        num_sends = self.num_sends
        first_send_name = self._song.return_tracks[send_index].name
        if send_index == num_sends - 1:
            return SEND_RANGE_SINGLE_FORMAT.format(first_send_name)
        return SEND_RANGE_PAIR_FORMAT.format(
            first_send_name,
            self._song.return_tracks[send_index + 1].name,
        )

    
    def _notify_send_range(self, _):
        self.notify(
            self.notifications.generic,
            NOTIFICATION_SENDS_FORMAT.format(self._get_send_range_string()),
        )



class MixerComponent(MixerComponentBase):
    def __init__(self, *a, **k):
        super().__init__(*a, send_index_control_component_type=SendIndexControlComponent, **k)
