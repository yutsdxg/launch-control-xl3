import Live
from ableton.v3.base import task
from ableton.v3.control_surface import ControlSurface, ControlSurfaceSpecification, create_skin
from ableton.v3.control_surface.capabilities import AUTO_LOAD_KEY, CONTROLLER_ID_KEY, PORTS_KEY, SCRIPT, SYNC, controller_id, inport, outport
from ableton.v3.live import action
from Launchkey_MK4.cue_point import CuePointComponent
from Launchkey_MK4.encoder_touch import EncoderTouchComponent
from Launchkey_MK4.zoom import ZoomComponent
import logging
from . import midi
from .colored_encoder import (
    _global_rule_options_for_parameter,
    _resolve_device_mode_switch_rules,
    _resolve_mode_count,
    _rule_options_for_parameter,
    _step_parameter_by_mode_count,
)
from .device import DeviceComponent
from .device_toggle import DeviceToggleComponent
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
DYNAMIC_ASSIGNMENT_SLOT_START = 5
DYNAMIC_ASSIGNMENT_SLOT_COUNT = 3
MIDI_VALUE_RANGE = 128
FADER_SELECTION_VALUE_BUCKETS = ((0, 31), (32, 63), (64, 95), (96, 127))
FADER_TRACK_SELECTION_MAP = {
    4: ("group", 1, 4, 1),
    5: ("group", 1, 8, 5),
    6: ("group", 2, 4, 1),
    7: ("group", 2, 8, 5),
    8: ("group", 2, 12, 9),
}
ARRANGEMENT_FOLLOW_FADER_INDEXES = (3, 4, 5, 6, 7)
ARRANGEMENT_VIEW_NAME = "Arranger"
SESSION_VIEW_NAME = "Session"
LOGGER = logging.getLogger(__name__)
DEBUG_MODE_PARAMS = ("l division", "r division")

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
    # Touch output can interfere with manual MIDI mapping (0/127 toggle values).
    hello_messages = (midi.make_connection_message(),)
    goodbye_messages = (midi.make_connection_message(connect=False),)
    display_specification = display_specification
    component_map = {
        'Cue_Point': CuePointComponent,
        'Device': DeviceComponent,
        'Device_Toggle': DeviceToggleComponent,
        'Encoder_Touch': EncoderTouchComponent,
        'Mixer': MixerComponent,
        'Session_Navigation': SessionNavigationComponent,
        'Transport': TransportComponent,
        'Zoom': ZoomComponent,
    }


class Launch_Control_XL_3(ControlSurface):
    def __init__(self, *a, **k):
        self._should_delay_flushing_display_messages = False
        self._dynamic_assignment_encoders = ()
        self._dynamic_assignment_slot_states = []
        self._dynamic_assignment_value_listeners = []
        self._mode_switch_encoders = ()
        self._mode_switch_value_listeners = []
        self._last_touched_parameter_task = None
        self._selection_target = None
        self._selection_target_kind = None
        self._selection_target_signature = None
        self._assignment_candidate_target = None
        self._assignment_candidate_kind = None
        self._assignment_candidate_signature = None
        self._fader_track_selection_controls = ()
        self._fader_track_selection_listeners = ()
        super().__init__(*a, **k)
        self._setup_dynamic_parameter_assignment()
        self._setup_mode_switch_parameter_override()
        self._setup_fader_track_selection()

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
            self.component_map["Encoder_Modes"].selected_mode = "daw_control"
            self.component_map["Daw_Mixer_Button_Modes"].selected_mode = "device_toggle"
            try:
                self.elements.daw_mixer_mode_button.send_value(0)
            except RuntimeError:
                pass
            self._update_assignment_candidate()

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

    def _setup_dynamic_parameter_assignment(self):
        lower_encoders = getattr(self.elements, "lower_encoders_raw", ())
        if len(lower_encoders) < 8:
            return
        start = DYNAMIC_ASSIGNMENT_SLOT_START
        end = start + DYNAMIC_ASSIGNMENT_SLOT_COUNT
        self._dynamic_assignment_encoders = tuple(lower_encoders[start:end])
        if len(self._dynamic_assignment_encoders) != DYNAMIC_ASSIGNMENT_SLOT_COUNT:
            self._dynamic_assignment_encoders = ()
            return
        self._dynamic_assignment_slot_states = [
            {"kind": None, "target": None, "signature": None} for _ in self._dynamic_assignment_encoders
        ]
        self._dynamic_assignment_value_listeners = []
        for slot_index, encoder in enumerate(self._dynamic_assignment_encoders):
            listener = self._make_dynamic_encoder_value_listener(slot_index)
            self._dynamic_assignment_value_listeners.append(listener)
            encoder.add_value_listener(listener)
        self._last_touched_parameter_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_assignment_candidate),
                    task.delay(LAST_TOUCHED_PARAMETER_POLL_INTERVAL),
                )
            )
        )

    def _setup_mode_switch_parameter_override(self):
        upper_encoders = tuple(getattr(self.elements, "upper_encoders_raw", ()))
        lower_encoders = tuple(getattr(self.elements, "lower_encoders_raw", ()))
        # Device parameter encoders: upper 16 + lower 1-5
        target_encoders = upper_encoders + lower_encoders[:5]
        if not target_encoders:
            return
        self._mode_switch_encoders = target_encoders
        self._mode_switch_value_listeners = []
        for encoder in self._mode_switch_encoders:
            listener = self._make_mode_switch_value_listener(encoder)
            self._mode_switch_value_listeners.append(listener)
            encoder.add_value_listener(listener)

    def _make_mode_switch_value_listener(self, encoder):
        def _listener(value, encoder=encoder):
            self._on_mode_switch_encoder_value(encoder, value)

        return _listener

    def _on_mode_switch_encoder_value(self, encoder, value):
        if value == 64:
            return
        try:
            mapped = encoder.is_mapped_to_parameter()
        except Exception:
            mapped = False
        if not mapped:
            return
        parameter = getattr(encoder, "mapped_object", None)
        if parameter is None:
            return
        parameter_name = getattr(parameter, "name", "")
        normalized_name = " ".join(str(parameter_name).strip().lower().split())
        debug_target = normalized_name in DEBUG_MODE_PARAMS
        parameter_rules = _resolve_device_mode_switch_rules(parameter)
        options = None
        if parameter_rules is not None:
            options = _rule_options_for_parameter(parameter_rules, parameter_name)
        if options is None:
            options = _global_rule_options_for_parameter(parameter_name)
        if options is None:
            if debug_target:
                LOGGER.info("LCXL3 mode-switch listener skip: no rule parameter=%s value=%s", parameter_name, value)
            return
        direction = 1 if value > 64 else -1
        mode_count = _resolve_mode_count(parameter, options)
        if not _step_parameter_by_mode_count(parameter, direction, mode_count):
            if debug_target:
                LOGGER.info(
                    "LCXL3 mode-switch listener skip: step failed parameter=%s mode_count=%s value=%s",
                    parameter_name,
                    mode_count,
                    value,
                )
            return
        try:
            LOGGER.info(
                "LCXL3 mode-switch listener override: parameter=%s mode_count=%s value=%s direction=%s",
                parameter_name,
                mode_count,
                value,
                direction,
            )
        except Exception:
            pass

    def _make_dynamic_encoder_value_listener(self, slot_index):
        def _listener(value, slot_index=slot_index):
            self._on_dynamic_encoder_value(slot_index, value)

        return _listener

    def _setup_fader_track_selection(self):
        faders = tuple(getattr(self.elements, "faders_raw", ()))
        if not faders:
            return
        controls = []
        listeners = []
        for fader_number, mapping_spec in FADER_TRACK_SELECTION_MAP.items():
            fader_index = fader_number - 1
            if fader_index >= len(faders):
                continue
            control = faders[fader_index]
            listener = self._make_fader_track_selection_listener(fader_index, mapping_spec)
            control.add_value_listener(listener)
            controls.append(control)
            listeners.append(listener)
        self._fader_track_selection_controls = tuple(controls)
        self._fader_track_selection_listeners = tuple(listeners)

    def _make_fader_track_selection_listener(self, fader_index, mapping_spec):
        def _listener(value, fader_index=fader_index, mapping_spec=mapping_spec):
            self._on_fader_track_selection_value(value, fader_index, mapping_spec)

        return _listener

    def _on_fader_track_selection_value(self, value, fader_index, mapping_spec):
        if not self._is_daw_control_mode_active():
            return
        bucket_index = self._fader_value_to_quarter_bucket(value)
        if bucket_index is None:
            return
        target = self._resolve_track_selection_target(mapping_spec, bucket_index)
        if target is None:
            return
        try:
            selected_track = self.song.view.selected_track
        except RuntimeError:
            selected_track = None
        try:
            if selected_track == target:
                return
        except RuntimeError:
            pass
        try:
            action.select(target)
        except RuntimeError:
            pass
        else:
            self._follow_arrangement_to_selected_track(selected_track, target, fader_index)

    def _is_daw_control_mode_active(self):
        try:
            encoder_modes = self.component_map.get("Encoder_Modes")
        except RuntimeError:
            encoder_modes = None
        if encoder_modes is None:
            return False
        try:
            return encoder_modes.selected_mode == "daw_control"
        except RuntimeError:
            return False

    def _fader_value_to_quarter_bucket(self, value):
        normalized_value = min(max(int(value), 0), MIDI_VALUE_RANGE - 1)
        for bucket_index, (bucket_start, bucket_end) in enumerate(FADER_SELECTION_VALUE_BUCKETS):
            if bucket_start <= normalized_value <= bucket_end:
                return bucket_index
        return None

    def _follow_arrangement_to_selected_track(self, previous_track, target_track, fader_index):
        if fader_index not in ARRANGEMENT_FOLLOW_FADER_INDEXES:
            return
        if not self._is_arrangement_view_active():
            return
        try:
            # Selection APIだけではArrangerが追従しないケースがあるため再設定を試す。
            self.song.view.selected_track = target_track
        except RuntimeError:
            pass
        try:
            # Arrangerにキーボードフォーカスを与えると追従するケースがある。
            self.application.view.focus_view(ARRANGEMENT_VIEW_NAME)
        except RuntimeError:
            pass
        previous_index = self._visible_track_index(previous_track)
        target_index = self._visible_track_index(target_track)
        if previous_index is None or target_index is None:
            try:
                LOGGER.info(
                    "LCXL3 arrangement follow skipped: prev_idx=%s target_idx=%s",
                    previous_index,
                    target_index,
                )
            except Exception:
                pass
            return
        delta = target_index - previous_index
        if delta == 0:
            return
        direction = (
            Live.Application.Application.View.NavDirection.down
            if delta > 0
            else Live.Application.Application.View.NavDirection.up
        )
        try:
            app_view = self.application.view
            for _ in range(abs(delta)):
                app_view.scroll_view(direction, ARRANGEMENT_VIEW_NAME, False)
        except RuntimeError:
            try:
                LOGGER.info("LCXL3 arrangement follow scroll failed: delta=%s", delta)
            except Exception:
                pass
        self._force_arrangement_reveal(target_track)

    def _is_arrangement_view_active(self):
        try:
            app_view = self.application.view
        except RuntimeError:
            return False
        try:
            if app_view.is_view_visible(ARRANGEMENT_VIEW_NAME):
                return True
        except RuntimeError:
            pass
        try:
            return app_view.focused_document_view == ARRANGEMENT_VIEW_NAME
        except RuntimeError:
            return False

    def _visible_track_index(self, track):
        if track is None:
            return None
        try:
            visible_tracks = tuple(self.song.visible_tracks)
        except RuntimeError:
            return None
        for index, visible_track in enumerate(visible_tracks):
            try:
                if visible_track == track:
                    return index
            except RuntimeError:
                continue
        return None

    def _force_arrangement_reveal(self, target_track):
        try:
            app_view = self.application.view
            app_view.show_view(SESSION_VIEW_NAME)
            self.song.view.selected_track = target_track
            app_view.show_view(ARRANGEMENT_VIEW_NAME)
            app_view.focus_view(ARRANGEMENT_VIEW_NAME)
        except RuntimeError:
            pass

    def _resolve_track_selection_target(self, mapping_spec, bucket_index):
        if not mapping_spec or len(mapping_spec) != 4:
            return None
        target_kind, group_ordinal, start_ordinal, end_ordinal = mapping_spec
        if target_kind != "group":
            return None
        targets = self._get_group_child_targets(group_ordinal)
        if not targets:
            return None
        step = 1 if end_ordinal >= start_ordinal else -1
        max_bucket_index = abs(end_ordinal - start_ordinal)
        effective_bucket_index = min(max(bucket_index, 0), max_bucket_index)
        target_ordinal = start_ordinal + (effective_bucket_index * step)
        target_index = target_ordinal - 1
        if target_index < 0 or target_index >= len(targets):
            return None
        return targets[target_index]

    def _get_group_child_targets(self, group_ordinal):
        if group_ordinal < 1:
            return ()
        try:
            tracks = tuple(self.song.tracks)
        except RuntimeError:
            return ()
        groups = []
        for track in tracks:
            try:
                if getattr(track, "is_foldable", False):
                    groups.append(track)
            except RuntimeError:
                continue
        if len(groups) < group_ordinal:
            return ()
        selected_group = groups[group_ordinal - 1]
        children = []
        for track in tracks:
            try:
                if getattr(track, "is_grouped", False) and getattr(track, "group_track", None) == selected_group:
                    children.append(track)
            except RuntimeError:
                continue
        return tuple(children)

    def _update_assignment_candidate(self):
        if not self._dynamic_assignment_encoders:
            return
        target_kind, target = self._resolve_assignment_target()
        target_signature = self._target_signature(target_kind, target)
        if target_signature != self._selection_target_signature:
            self._selection_target_kind = target_kind
            self._selection_target = target
            self._selection_target_signature = target_signature
            self._assignment_candidate_kind = target_kind
            self._assignment_candidate_target = target
            self._assignment_candidate_signature = target_signature

    def _on_dynamic_encoder_value(self, slot_index, value):
        if value == 64:
            return
        self._update_assignment_candidate()
        self._apply_assignment_candidate_to_slot(slot_index)
        slot_state = self._dynamic_assignment_slot_states[slot_index]
        if slot_state["kind"] == "clip_gain" and slot_state["target"] is not None:
            self._adjust_clip_gain(slot_state["target"], value - 64)

    def _apply_assignment_candidate_to_slot(self, slot_index):
        target = self._assignment_candidate_target
        target_kind = self._assignment_candidate_kind
        target_signature = self._assignment_candidate_signature
        if target is None:
            return
        current_slot = self._dynamic_assignment_slot_states[slot_index]
        if self._is_same_target(
            target_kind,
            target,
            target_signature,
            current_slot["kind"],
            current_slot["target"],
            current_slot["signature"],
        ):
            self._clear_assignment_candidate()
            return
        for other_index, slot in enumerate(self._dynamic_assignment_slot_states):
            if other_index == slot_index:
                continue
            if self._is_same_target(
                target_kind,
                target,
                target_signature,
                slot["kind"],
                slot["target"],
                slot["signature"],
            ):
                self._clear_slot_assignment(other_index)
                break
        if self._set_slot_assignment(slot_index, target_kind, target, target_signature):
            self._clear_assignment_candidate()

    def _set_slot_assignment(self, slot_index, target_kind, target, target_signature):
        encoder = self._dynamic_assignment_encoders[slot_index]
        if target_kind == "parameter":
            if not getattr(target, "is_enabled", False):
                return False
            try:
                encoder.connect_to(target)
            except RuntimeError:
                return False
        elif target_kind == "clip_gain":
            try:
                encoder.release_parameter()
            except RuntimeError:
                return False
        else:
            return False
        self._dynamic_assignment_slot_states[slot_index]["kind"] = target_kind
        self._dynamic_assignment_slot_states[slot_index]["target"] = target
        self._dynamic_assignment_slot_states[slot_index]["signature"] = target_signature
        return True

    def _clear_slot_assignment(self, slot_index):
        if slot_index < 0 or slot_index >= len(self._dynamic_assignment_encoders):
            return
        encoder = self._dynamic_assignment_encoders[slot_index]
        try:
            encoder.release_parameter()
        except RuntimeError:
            pass
        self._dynamic_assignment_slot_states[slot_index]["kind"] = None
        self._dynamic_assignment_slot_states[slot_index]["target"] = None
        self._dynamic_assignment_slot_states[slot_index]["signature"] = None

    def _get_selected_parameter(self):
        try:
            return self.song.view.selected_parameter
        except RuntimeError:
            return None

    def _resolve_assignment_target(self):
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

    def _adjust_clip_gain(self, clip, delta):
        try:
            new_gain = min(max(clip.gain + delta * RELATIVE_ENCODER_DELTA_SCALE, 0.0), 1.0)
            clip.gain = new_gain
        except RuntimeError:
            return

    def _clear_assignment_candidate(self):
        self._assignment_candidate_kind = None
        self._assignment_candidate_target = None
        self._assignment_candidate_signature = None

    def _target_signature(self, target_kind, target):
        if target is None or target_kind is None:
            return None
        if target_kind == "parameter":
            return self._parameter_signature(target)
        if target_kind == "clip_gain":
            return self._clip_signature(target)
        return (target_kind, repr(target))

    def _parameter_signature(self, parameter):
        parameter_name = self._safe_attr(parameter, "name")
        parent = getattr(parameter, "canonical_parent", None)
        parent_name = self._safe_attr(parent, "name")
        parent_class = self._safe_attr(parent, "class_name")
        parameter_index = None
        if parent is not None:
            try:
                parameters = tuple(parent.parameters)
                for index, item in enumerate(parameters):
                    if item == parameter:
                        parameter_index = index
                        break
            except RuntimeError:
                pass
            except AttributeError:
                pass
        track = self._selected_track()
        track_name = self._safe_attr(track, "name")
        track_index = self._selected_track_index(track)
        return (
            "parameter",
            track_index,
            track_name,
            parent_class,
            parent_name,
            parameter_name,
            parameter_index,
        )

    def _clip_signature(self, clip):
        clip_name = self._safe_attr(clip, "name")
        return ("clip_gain", clip_name)

    def _safe_attr(self, obj, attribute, fallback=None):
        if obj is None:
            return fallback
        try:
            return getattr(obj, attribute)
        except RuntimeError:
            return fallback
        except AttributeError:
            return fallback

    def _selected_track(self):
        try:
            return self.song.view.selected_track
        except RuntimeError:
            return None

    def _selected_track_index(self, track):
        if track is None:
            return None
        try:
            tracks = tuple(self.song.tracks)
            returns = tuple(self.song.return_tracks)
            all_tracks = tracks + returns + (self.song.master_track,)
        except RuntimeError:
            return None
        for index, item in enumerate(all_tracks):
            try:
                if item == track:
                    return index
            except RuntimeError:
                continue
        return None

    def _is_same_target(
        self,
        left_kind,
        left_target,
        left_signature,
        right_kind,
        right_target,
        right_signature,
    ):
        if left_kind != right_kind:
            return False
        if left_signature is not None and right_signature is not None:
            return left_signature == right_signature
        return left_target is right_target

    def disconnect(self):
        for control, listener in zip(
            self._fader_track_selection_controls,
            self._fader_track_selection_listeners,
        ):
            try:
                control.remove_value_listener(listener)
            except RuntimeError:
                pass
        self._fader_track_selection_controls = ()
        self._fader_track_selection_listeners = ()
        for encoder, listener in zip(self._mode_switch_encoders, self._mode_switch_value_listeners):
            try:
                encoder.remove_value_listener(listener)
            except RuntimeError:
                pass
        self._mode_switch_value_listeners = []
        for encoder, listener in zip(
            self._dynamic_assignment_encoders,
            self._dynamic_assignment_value_listeners,
        ):
            try:
                encoder.remove_value_listener(listener)
            except RuntimeError:
                pass
        self._dynamic_assignment_value_listeners = []
        super().disconnect()
