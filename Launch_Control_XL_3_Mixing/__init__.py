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
from .elements import Elements
from .fixed_assignments import FixedAssignmentsComponent
from .locator_navigation import LocatorNavigationComponent
from .mappings import create_mappings
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
        "Fixed_Assignments": FixedAssignmentsComponent,
        "Locator_Navigation": LocatorNavigationComponent,
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
        self._refresh_led_feedback()

    def _setup_components(self):
        fixed_assignments = self._component("Fixed_Assignments")
        track_buttons = self._component("Track_Buttons")
        if fixed_assignments is not None:
            fixed_assignments.set_midi_sender(self.send_midi)
        if track_buttons is not None:
            track_buttons.set_midi_sender(self.send_midi)

    def _component(self, name):
        try:
            return self.component_map.get(name)
        except RuntimeError:
            return None

    def _refresh_led_feedback(self):
        for name in ("Fixed_Assignments", "Track_Buttons"):
            component = self._component(name)
            if component is not None:
                try:
                    component.refresh_led_feedback()
                except RuntimeError:
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
