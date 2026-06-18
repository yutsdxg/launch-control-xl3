from ableton.v3.control_surface.midi import SYSEX_END, SYSEX_START

SYSEX_HEADER = (SYSEX_START, 0, 32, 41, 2, 21)
RGB_LED_COMMAND = (1, 83)
SET_RELATIVE_ENCODER_MODES = ((182, 69, 127), (182, 72, 127), (182, 73, 127))


def make_connection_message(connect=True):
    return SYSEX_HEADER + (2, 127 if connect else 0, SYSEX_END)


def make_rgb_led_message(control_index, rgb):
    return SYSEX_HEADER + RGB_LED_COMMAND + (control_index,) + tuple(rgb) + (SYSEX_END,)
