from enum import IntEnum
from functools import partial

try:
    from ableton.v3.control_surface.display import Text
except ImportError:
    Text = None


DISPLAY_WIDTH = 16


class Config(IntEnum):
    two_line = 97
    three_line = 98


def display_field(text):
    text = "" if text is None else str(text)
    if Text is None:
        return tuple(ord(char) for char in text[:DISPLAY_WIDTH])
    display_text = partial(Text, max_width=DISPLAY_WIDTH, justification=Text.Justification.NONE)
    return display_text(text).as_ascii()


def send_display(command, lines, show_immediately=False, trigger=False):
    if command is None:
        return False
    try:
        command.send_data(
            Config.three_line,
            tuple(display_field(line) for line in lines[:3]),
            show_immediately,
            trigger,
        )
    except (AttributeError, RuntimeError):
        return False
    return True
