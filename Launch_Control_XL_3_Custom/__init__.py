from ableton.v3.base import task
from ableton.v3.control_surface import ControlSurface, ControlSurfaceSpecification, create_skin
from ableton.v3.control_surface.capabilities import AUTO_LOAD_KEY, CONTROLLER_ID_KEY, PORTS_KEY, SCRIPT, SYNC, controller_id, inport, outport
from Launchkey_MK4.cue_point import CuePointComponent
from Launchkey_MK4.encoder_touch import EncoderTouchComponent
from Launchkey_MK4.zoom import ZoomComponent
from . import midi
from .device import DeviceComponent
from .display import display_specification
from .elements import Elements
from .mappings import create_mappings
from .mixer import MixerComponent
from .session_navigation import SessionNavigationComponent
from .session_ring import SessionRingComponent
from .skin import Rgb, Skin
from .transport import TransportComponent

SYSEX_FLUSH_THRESHOLD = 10
SYSEX_DISPLAY_ID_LENGTH = 9
LAST_TOUCHED_PARAMETER_POLL_INTERVAL = 0.1
RELATIVE_ENCODER_DELTA_SCALE = 1.0 / 127.0

def get_capabilities():
    return {
        CONTROLLER_ID_KEY: controller_id(
            vendor_id=4661,
            product_ids=[328 + i for i in range(8)],
            model_name=["LCXL3 {}".format(i) for i in range(1, 9)],
        ),
        PORTS_KEY: [
            inport(),
            inport(props=[SCRIPT]),
            outport(),
            outport(props=[SYNC, SCRIPT]),
        ],
        AUTO_LOAD_KEY: True,
    }


def create_instance(c_instance):
    return Launch_Control_XL_3(specification=Specification, c_instance=c_instance)


class Specification(ControlSurfaceSpecification):
    elements_type = Elements
    control_surface_skin = create_skin(skin=Skin, colors=Rgb)
    link_session_ring_to_track_selection = True
    session_ring_component_type = SessionRingComponent
    create_mappings_function = create_mappings
    identity_response_id_bytes = (0, 32, 41, -1, 1, 0, 1)
    hello_messages = (midi.make_connection_message(), midi.make_enable_touch_output_message())
    goodbye_messages = (midi.make_connection_message(connect=False),)
    display_specification = display_specification
    component_map = {
        'Cue_Point': CuePointComponent,
        'Device': DeviceComponent,
        'Encoder_Touch': EncoderTouchComponent,
        'Mixer': MixerComponent,
        'Session_Navigation': SessionNavigationComponent,
        'Transport': TransportComponent,
        'Zoom': ZoomComponent,
    }


class Launch_Control_XL_3(ControlSurface):
    def __init__(self, *a, **k):
        self._should_delay_flushing_display_messages = False
        self._last_touched_parameter = None
        self._last_touched_encoder = None
        self._last_touched_parameter_task = None
        self._last_touched_target = None
        self._last_touched_target_kind = None
        super().__init__(*a, **k)
        self._setup_last_touched_parameter_control()

    def port_settings_changed(self):
        self._send_midi(midi.make_connection_message(connect=False))
        super().port_settings_changed()

    def send_midi(self, midi_bytes):
        self._send_midi(midi_bytes)

    def on_identified(self, response_bytes):
        self._should_delay_flushing_display_messages = False
        self._tasks.add(
            task.sequence(
                task.delay(1),
                task.run(lambda: setattr(self, "_should_delay_flushing_display_messages", True)),
            )
        )
        super().on_identified(response_bytes)
        with self.component_guard():
            self.component_map["Encoder_Modes"].selected_mode = "daw_mixer"
            self._update_last_touched_parameter_mapping()

    def _flush_midi_messages(self):
        if (
            self._should_delay_flushing_display_messages
            and len(self._midi_message_list) > SYSEX_FLUSH_THRESHOLD
        ):
            filtered_messages = {m[:SYSEX_DISPLAY_ID_LENGTH]: m for _, m in self._midi_message_list}
            for i, message in enumerate(filtered_messages.values()):
                self._tasks.add(task.sequence(task.delay(i * 0.01), task.run(self._do_send_midi, message)))
            self._midi_message_list[:] = []
        super()._flush_midi_messages()

    def _setup_last_touched_parameter_control(self):
        lower_encoders = getattr(self.elements, "lower_encoders_raw", ())
        if len(lower_encoders) < 8:
            return
        self._last_touched_encoder = lower_encoders[7]
        self._last_touched_encoder.add_value_listener(self._on_last_touched_encoder_value)
        self._last_touched_parameter_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_last_touched_parameter_mapping),
                    task.delay(LAST_TOUCHED_PARAMETER_POLL_INTERVAL),
                )
            )
        )

    def _update_last_touched_parameter_mapping(self):
        if self._last_touched_encoder is None:
            return
        target_kind, target = self._resolve_last_touched_target()
        if target is None:
            if self._last_touched_target_kind == "parameter":
                self._last_touched_encoder.release_parameter()
            self._last_touched_parameter = None
            self._last_touched_target_kind = None
            self._last_touched_target = None
            return
        if target_kind == self._last_touched_target_kind and target == self._last_touched_target:
            return
        if target_kind == "parameter":
            if not getattr(target, "is_enabled", False):
                return
            try:
                self._last_touched_encoder.connect_to(target)
            except RuntimeError:
                return
            self._last_touched_parameter = target
        else:
            self._last_touched_encoder.release_parameter()
            self._last_touched_parameter = None
        self._last_touched_target_kind = target_kind
        self._last_touched_target = target

    def _get_selected_parameter(self):
        try:
            return self.song.view.selected_parameter
        except RuntimeError:
            return None

    def _resolve_last_touched_target(self):
        parameter = self._get_selected_parameter()
        if parameter is not None and getattr(parameter, "is_enabled", False):
            return "parameter", parameter
        clip = self._get_selected_audio_detail_clip()
        if clip is not None:
            return "clip_gain", clip
        return None, None

    def _get_selected_audio_detail_clip(self):
        try:
            if not self.application.view.is_view_visible("Detail/Clip"):
                return None
            clip = self.song.view.detail_clip
        except RuntimeError:
            return None
        if clip is None or not getattr(clip, "is_audio_clip", False):
            return None
        return clip

    def _on_last_touched_encoder_value(self, value):
        if self._last_touched_target_kind != "clip_gain" or self._last_touched_target is None:
            return
        if value == 64:
            return
        delta = value - 64
        clip = self._last_touched_target
        try:
            new_gain = min(max(clip.gain + delta * RELATIVE_ENCODER_DELTA_SCALE, 0.0), 1.0)
            clip.gain = new_gain
        except RuntimeError:
            return
