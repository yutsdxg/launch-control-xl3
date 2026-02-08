from dataclasses import dataclass
from enum import IntEnum
from functools import partial
from typing import Optional, Tuple

from ableton.v3.base import flatten
from ableton.v3.control_surface.display import DefaultNotifications, DisplaySpecification, Text, view
from ableton.v3.live import display_name, find_parent_track, liveobj_name, liveobj_valid

DisplayText = partial(Text, max_width=16, justification=Text.Justification.NONE)


class ControlType(IntEnum):
    faders = 0
    upper_encoders = 1
    lower_encoders = 2


class Config(IntEnum):
    two_line = 97
    three_line = 98


@dataclass
class TargetContent:
    config: Optional[Config] = Config.two_line
    lines: Optional[Tuple[str, ...]] = ()
    trigger: Optional[bool] = False


@dataclass
class DisplayContent:
    static: Optional[TargetContent] = None
    temp: Optional[TargetContent] = None
    encoders: Tuple[Optional[Tuple[TargetContent, TargetContent]], ...] = ()
    upper_encoders: Tuple[Optional[Tuple[TargetContent, TargetContent]], ...] = ()
    lower_encoders: Tuple[Optional[Tuple[TargetContent, TargetContent]], ...] = ()
    faders: Tuple[Optional[Tuple[TargetContent, TargetContent]], ...] = ()

    @classmethod
    def with_parameters(cls, state, released_encoder_index=None, **k):
        def parameter_header(element, control_type):
            if (
                control_type == ControlType.faders
                or state.encoder_modes.selected_mode == "daw_mixer"
            ) and liveobj_valid(element.mapped_object.canonical_parent):
                return liveobj_name(find_parent_track(element.mapped_object))
            if control_type == ControlType.lower_encoders:
                return "Transport"
            return liveobj_name(state.target_track.target_track)

        def parameter_content(elements, control_type):
            encoder_offset = 16 if control_type == ControlType.lower_encoders else 0
            return tuple(
                TargetContent(
                    config=Config.three_line,
                    lines=(
                        (
                            parameter_header(element, control_type),
                            display_name(element.mapped_object),
                            str(element.mapped_object),
                        )
                        if liveobj_valid(element.mapped_object)
                        else ("-", "-", "-")
                    ),
                    trigger=(
                        control_type != ControlType.faders
                        and i + encoder_offset == released_encoder_index
                    ),
                )
                for i, element in enumerate(elements)
            )

        return cls(
            upper_encoders=parameter_content(
                list(flatten(state.elements.upper_encoders)),
                ControlType.upper_encoders,
            ),
            lower_encoders=parameter_content(
                state.elements.lower_encoders,
                ControlType.lower_encoders,
            ),
            faders=parameter_content(state.elements.faders, ControlType.faders),
            **k
        )


class Notifications(DefaultNotifications):
    generic = DefaultNotifications.DefaultText()
    identify = DefaultNotifications.TransformDefaultText(lambda x: "\n{}".format(x.replace("Connected", "")))

    class Device(DefaultNotifications.Device):
        bank = DefaultNotifications.DefaultText()

    class Modes(DefaultNotifications.Modes):
        select = lambda _, mode_name: "mode:{}".format(mode_name)


def render_mode_notification(mode):
    if mode in ("solo", "arm", "mute", "track_select"):
        return DisplayContent(
            temp=TargetContent(lines=("Button Function", mode.replace("_", " ").title()))
        )
    return None


def render_notification(_, notification_text):
    if notification_text.startswith("mode:"):
        return render_mode_notification(notification_text.replace("mode:", ""))
    if "\n" in notification_text:
        lines = tuple(notification_text.split("\n"))
        return DisplayContent(
            temp=TargetContent(
                config=Config.three_line if len(lines) == 3 else Config.two_line,
                lines=lines,
            )
        )
    return None


def create_root_view() -> view.View[Optional[DisplayContent]]:
    def _main_view(state) -> Optional[DisplayContent]:
        if state.encoder_touch.last_released_index is not None:
            return DisplayContent.with_parameters(
                state,
                state.encoder_touch.last_released_index,
            )
        return DisplayContent.with_parameters(
            state,
            static=TargetContent(
                config=Config.three_line,
                lines=(
                    state.session_navigation.track_range_string,
                    liveobj_name(state.target_track.target_track),
                    liveobj_name(state.device.device) or "-",
                ),
            ),
        )
    main_view = view.View(_main_view)

    return view.CompoundView(
        view.DisconnectedView(),
        view.NotificationView(render_notification, duration=0.1, supports_new_line=True),
        main_view,
    )


def protocol(elements):
    def display(content: DisplayContent):
        if content:
            display_content("static", content.static, True)
            display_content("temp", content.temp, True)
            for i, encoder in enumerate(content.upper_encoders):
                display_content("upper_encoder_{}".format(i), encoder)
            for i, encoder in enumerate(content.lower_encoders):
                display_content("lower_encoder_{}".format(i), encoder)
            for i, fader in enumerate(content.faders):
                display_content("fader_{}".format(i), fader)

    def display_content(name, content: TargetContent, show_immediately=False):
        if content and content.lines:
            command = getattr(elements, "{}_display_command".format(name))
            command.send_data(
                content.config,
                tuple(DisplayText(line).as_ascii() for line in content.lines),
                show_immediately,
                content.trigger,
            )

    return display


display_specification = DisplaySpecification(
    create_root_view=create_root_view,
    protocol=protocol,
    notifications=Notifications,
)
