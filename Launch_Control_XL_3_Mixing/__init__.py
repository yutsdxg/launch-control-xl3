from ableton.v3.base import task
from ableton.v3.control_surface import ControlSurface, ControlSurfaceSpecification, create_skin
from ableton.v3.control_surface.capabilities import (
    CONTROLLER_ID_KEY,
    PORTS_KEY,
    SCRIPT,
    SYNC,
    controller_id,
    inport,
    outport,
)

from . import midi
from .control_router import ControlRouterComponent
from .elements import Elements
from .fixed_assignments import FixedAssignmentsComponent
from .instrument_assignments import InstrumentAssignmentsComponent
from .locator_navigation import LocatorNavigationComponent
from .mappings import create_mappings
from .mode_manager import MODE_INSTRUMENT, MODE_MIXING, ModeManagerComponent
from .skin import Rgb, Skin
from .track_buttons import TrackButtonsComponent
from .transport import TransportComponent

SYSEX_FLUSH_THRESHOLD = 10
SYSEX_DISPLAY_ID_LENGTH = 9


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
    }


def create_instance(c_instance):
    return Launch_Control_XL_3_Mixing(specification=Specification, c_instance=c_instance)


class Specification(ControlSurfaceSpecification):
    elements_type = Elements
    control_surface_skin = create_skin(skin=Skin, colors=Rgb)
    create_mappings_function = create_mappings
    identity_response_id_bytes = (0, 32, 41, -1, 1, 0, 1)
    hello_messages = (midi.make_connection_message(),)
    goodbye_messages = (midi.make_connection_message(connect=False),)
    component_map = {
        "Control_Router": ControlRouterComponent,
        "Fixed_Assignments": FixedAssignmentsComponent,
        "Instrument_Assignments": InstrumentAssignmentsComponent,
        "Locator_Navigation": LocatorNavigationComponent,
        "Mode_Manager": ModeManagerComponent,
        "Track_Buttons": TrackButtonsComponent,
        "Transport": TransportComponent,
    }


class Launch_Control_XL_3_Mixing(ControlSurface):
    def __init__(self, *a, **k):
        self._should_delay_flushing_display_messages = False
        super().__init__(*a, **k)
        self._setup_components()

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
        for message in midi.SET_RELATIVE_ENCODER_MODES:
            self.send_midi(message)
        self._apply_selected_mode()
        self._refresh_led_feedback()

    def _setup_components(self):
        control_router = self._component("Control_Router")
        fixed_assignments = self._component("Fixed_Assignments")
        instrument_assignments = self._component("Instrument_Assignments")
        mode_manager = self._component("Mode_Manager")
        track_buttons = self._component("Track_Buttons")
        if fixed_assignments is not None:
            fixed_assignments.set_midi_sender(self.send_midi)
        if instrument_assignments is not None:
            instrument_assignments.set_midi_sender(self.send_midi)
        if mode_manager is not None:
            mode_manager.set_midi_sender(self.send_midi)
        if track_buttons is not None:
            track_buttons.set_midi_sender(self.send_midi)
        if control_router is not None:
            control_router.set_target_components(
                fixed_assignments=fixed_assignments,
                instrument_assignments=instrument_assignments,
                track_buttons=track_buttons,
            )
        if mode_manager is not None:
            mode_manager.set_on_mode_changed(self._on_mode_changed)
        else:
            self._apply_mode(MODE_MIXING)

    def _component(self, name):
        try:
            return self.component_map.get(name)
        except RuntimeError:
            return None

    def _refresh_led_feedback(self):
        for name in ("Mode_Manager", "Fixed_Assignments", "Track_Buttons", "Instrument_Assignments"):
            component = self._component(name)
            if component is not None:
                try:
                    component.refresh_led_feedback()
                except RuntimeError:
                    pass

    def _on_mode_changed(self, mode):
        self._apply_mode(mode)
        self._refresh_led_feedback()

    def _apply_selected_mode(self):
        mode_manager = self._component("Mode_Manager")
        mode = MODE_MIXING
        if mode_manager is not None:
            try:
                mode = mode_manager.selected_mode
            except RuntimeError:
                mode = MODE_MIXING
        self._apply_mode(mode)

    def _apply_mode(self, mode):
        mode = MODE_INSTRUMENT if mode == MODE_INSTRUMENT else MODE_MIXING
        if mode == MODE_INSTRUMENT:
            self._set_component_active("Fixed_Assignments", False)
            self._set_component_active("Track_Buttons", False)
            self._set_component_active("Instrument_Assignments", True)
        else:
            self._set_component_active("Instrument_Assignments", False)
            self._set_component_active("Fixed_Assignments", True)
            self._set_component_active("Track_Buttons", True)

    def _set_component_active(self, name, active):
        component = self._component(name)
        if component is None:
            return
        try:
            component.set_active(active)
        except (AttributeError, RuntimeError):
            pass

    def _flush_midi_messages(self):
        if (
            self._should_delay_flushing_display_messages
            and len(self._midi_message_list) > SYSEX_FLUSH_THRESHOLD
        ):
            filtered_messages = {message[:SYSEX_DISPLAY_ID_LENGTH]: message for _, message in self._midi_message_list}
            for index, message in enumerate(filtered_messages.values()):
                self._tasks.add(
                    task.sequence(
                        task.delay(index * 0.01),
                        task.run(self._do_send_midi, message),
                    )
                )
            self._midi_message_list[:] = []
        super()._flush_midi_messages()
