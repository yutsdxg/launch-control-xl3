from Launchkey_MK4.transport import InternalParameterControl
from Launchkey_MK4.transport import TransportComponent as TransportComponentBase
from Launchkey_MK4.transport import register_internal_parameter

class TransportComponent(TransportComponentBase):
    loop_toggle_encoder = InternalParameterControl()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.loop_toggle_encoder.parameter = register_internal_parameter(
            self, "Loop", lambda: "{}".format("On" if self.song.loop else "Off")
        )

    @loop_toggle_encoder.value
    def loop_toggle_encoder(self, value, _):
        toggle_on = value > 0
        if self.song.loop != toggle_on:
            self.song.loop = toggle_on
