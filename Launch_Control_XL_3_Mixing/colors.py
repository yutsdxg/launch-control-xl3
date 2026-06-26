from ableton.v3.base import memoize
from ableton.v3.control_surface import STANDARD_COLOR_PALETTE, STANDARD_FALLBACK_COLOR_TABLE
from ableton.v3.control_surface.elements import ColorPart, ComplexColor, SimpleColor
from ableton.v3.live import liveobj_color_to_value_from_palette, liveobj_valid

BLINK_CHANNEL = 1
TRACK_ON_BRIGHTNESS = 0.25
TRACK_MUTED_BRIGHTNESS = 0.03
ENCODER_MIN_BRIGHTNESS = 0.03
ENCODER_CENTER_BRIGHTNESS = 0.175
ENCODER_MAX_BRIGHTNESS = 0.38
ENCODER_PARAMETER_BRIGHTNESS = 0.25
DEVICE_TOGGLE_ENCODER_ON_BRIGHTNESS = 0.25
DEVICE_TOGGLE_ENCODER_OFF_BRIGHTNESS = 0.03
SUBMODE_ENCODER_BRIGHTNESS = DEVICE_TOGGLE_ENCODER_ON_BRIGHTNESS
MODE_ACTIVE_BRIGHTNESS = TRACK_ON_BRIGHTNESS
MODE_INACTIVE_BRIGHTNESS = TRACK_MUTED_BRIGHTNESS
INSTRUMENT_BUTTON_ON_BRIGHTNESS = TRACK_ON_BRIGHTNESS
INSTRUMENT_BUTTON_OFF_BRIGHTNESS = TRACK_MUTED_BRIGHTNESS
MIDI_RGB_MAX = 127
LIVE_RGB_MAX = 255


class Palette:
    OFF = (0, 0, 0)
    WHITE = (127, 127, 127)
    WHITE_HALF = (48, 48, 48)
    WHITE_DIM = (16, 16, 16)
    RED = (127, 12, 12)
    RED_HALF = (127, 42, 42)
    DARK_RED = (64, 10, 10)
    GREEN = (12, 127, 24)
    GREEN_HALF = (36, 127, 52)
    YELLOW = (127, 116, 8)
    DARK_YELLOW = (8, 7, 1)
    BLUE = (14, 54, 127)
    BLUE_HALF = (44, 84, 127)
    DARK_BLUE = (10, 34, 96)
    IDLE_BLUE = (2, 8, 24)
    ORANGE = (127, 56, 8)
    TURQUOISE = (8, 112, 104)
    LIGHT_BLUE = (48, 98, 127)
    PURPLE = (84, 18, 120)

    ENCODER_MIN = WHITE
    ENCODER_CENTER = WHITE
    ENCODER_MAX = WHITE
    ENCODER_DEVICE_VALUE_BINS = (
        (72, 18, 112),
        (64, 24, 112),
        (8, 84, 127),
        (10, 112, 38),
        (52, 127, 4),
        (127, 127, 0),
        (127, 72, 0),
        (112, 18, 14),
    )


class Theme:
    OFF = Palette.OFF
    DEVICE_ON = Palette.YELLOW
    DEVICE_OFF = Palette.DARK_YELLOW
    DEVICE_TOGGLE_ENCODER_COLORS = {
        2: Palette.YELLOW,
        3: Palette.YELLOW,
        4: Palette.GREEN,
        5: Palette.GREEN,
        6: Palette.RED,
        7: Palette.GREEN,
    }
    SOLO_ON = Palette.BLUE
    SOLO_MODIFIER_IDLE = Palette.IDLE_BLUE
    MUTE_MODIFIER_ON = Palette.YELLOW
    MUTE_MODIFIER_IDLE = Palette.DARK_YELLOW
    TRACK_FALLBACK = Palette.WHITE_HALF
    ENCODER_TRACK_VOLUME = Palette.LIGHT_BLUE
    ENCODER_MIXER_PARAMETER = Palette.TURQUOISE
    ENCODER_PAN_LEFT = Palette.DARK_BLUE
    ENCODER_PAN_CENTER = Palette.WHITE_HALF
    ENCODER_PAN_RIGHT = Palette.ORANGE
    ENCODER_MIN = Palette.ENCODER_MIN
    ENCODER_CENTER = Palette.ENCODER_CENTER
    ENCODER_MAX = Palette.ENCODER_MAX
    ENCODER_DEVICE_VALUE_BINS = Palette.ENCODER_DEVICE_VALUE_BINS


@memoize
def make_simple_color(value):
    return SimpleColor(value)


def make_color_for_liveobj(obj):
    color = make_simple_color(
        liveobj_color_to_value_from_palette(
            obj,
            palette=STANDARD_COLOR_PALETTE,
            fallback_table=STANDARD_FALLBACK_COLOR_TABLE,
        )
    )
    if liveobj_valid(obj) and not color.midi_value:
        return Rgb.WHITE_HALF
    return color


def make_animated_color(value, animation_channel):
    return ComplexColor((ColorPart(value), ColorPart(0, animation_channel)))


class Rgb:
    OFF = SimpleColor(0)
    WHITE = SimpleColor(3)
    WHITE_HALF = SimpleColor(1)
    WHITE_DIM = SimpleColor(103)
    GREEN = SimpleColor(21)
    GREEN_HALF = SimpleColor(27)
    RED = SimpleColor(5)
    RED_HALF = SimpleColor(7)
    RED_BLINK = make_animated_color(5, BLINK_CHANNEL)
    BLUE = SimpleColor(41)
    BLUE_HALF = SimpleColor(43)
    ORANGE = SimpleColor(96)
    YELLOW = SimpleColor(97)
    DARK_YELLOW = SimpleColor(15)
    DARK_BLUE = SimpleColor(47)
    LIGHT_BLUE = SimpleColor(92)
    TURQUOISE = SimpleColor(39)
    PURPLE = SimpleColor(53)


def clamp_rgb_channel(value):
    return max(0, min(MIDI_RGB_MAX, int(round(value))))


def scale_rgb(rgb, factor, keep_visible=True):
    scaled = []
    for channel in rgb:
        original = clamp_rgb_channel(channel)
        value = clamp_rgb_channel(original * factor)
        if keep_visible and original > 0 and value == 0:
            value = 1
        scaled.append(value)
    return tuple(scaled)


def dim_track_rgb(rgb):
    return scale_rgb(rgb, TRACK_MUTED_BRIGHTNESS)


def active_track_rgb(rgb):
    return scale_rgb(rgb, TRACK_ON_BRIGHTNESS)


def track_rgb(track):
    try:
        live_color = int(track.color)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return Theme.TRACK_FALLBACK
    rgb_255 = (
        (live_color >> 16) & LIVE_RGB_MAX,
        (live_color >> 8) & LIVE_RGB_MAX,
        live_color & LIVE_RGB_MAX,
    )
    rgb = tuple(clamp_rgb_channel(channel * MIDI_RGB_MAX / LIVE_RGB_MAX) for channel in rgb_255)
    return rgb if any(rgb) else Theme.TRACK_FALLBACK


def normalized_parameter_value(parameter):
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    parameter_range = maximum - minimum
    if parameter_range <= 0:
        return 0.0
    return min(max((current - minimum) / parameter_range, 0.0), 1.0)


def encoder_rgb_for_parameter(parameter, is_device_parameter=False):
    normalized = normalized_parameter_value(parameter)
    if normalized is None:
        return Theme.OFF
    value_7bit = clamp_rgb_channel(normalized * MIDI_RGB_MAX)
    if value_7bit == 0:
        return scale_rgb(Theme.ENCODER_MIN, ENCODER_MIN_BRIGHTNESS)
    if value_7bit == 64:
        return scale_rgb(Theme.ENCODER_CENTER, ENCODER_CENTER_BRIGHTNESS)
    if value_7bit == MIDI_RGB_MAX:
        return scale_rgb(Theme.ENCODER_MAX, ENCODER_MAX_BRIGHTNESS)
    if is_device_parameter:
        bins = Theme.ENCODER_DEVICE_VALUE_BINS
        index = min(int(normalized * len(bins)), len(bins) - 1)
        return scale_rgb(bins[index], ENCODER_PARAMETER_BRIGHTNESS)
    try:
        parameter_name = parameter.name
    except (AttributeError, RuntimeError):
        parameter_name = ""
    base = Theme.ENCODER_TRACK_VOLUME if parameter_name == "Track Volume" else Theme.ENCODER_MIXER_PARAMETER
    return scale_rgb(base, ENCODER_PARAMETER_BRIGHTNESS)


def device_toggle_encoder_rgb(encoder_number, is_on):
    if is_on is None:
        return Theme.OFF
    base = Theme.DEVICE_TOGGLE_ENCODER_COLORS.get(encoder_number, Theme.DEVICE_ON)
    brightness = DEVICE_TOGGLE_ENCODER_ON_BRIGHTNESS if is_on else DEVICE_TOGGLE_ENCODER_OFF_BRIGHTNESS
    return scale_rgb(base, brightness)


def loopcloud_metric_submode_rgb(is_metric_ab):
    base = Palette.ORANGE if is_metric_ab else Palette.YELLOW
    return scale_rgb(base, SUBMODE_ENCODER_BRIGHTNESS)


def mode_button_rgb(is_active):
    brightness = MODE_ACTIVE_BRIGHTNESS if is_active else MODE_INACTIVE_BRIGHTNESS
    return scale_rgb(Palette.WHITE, brightness)


def instrument_button_rgb(is_on):
    if is_on is None:
        return Theme.OFF
    brightness = INSTRUMENT_BUTTON_ON_BRIGHTNESS if is_on else INSTRUMENT_BUTTON_OFF_BRIGHTNESS
    return scale_rgb(Palette.WHITE, brightness)


def encoder_pan_rgb(parameter_value):
    if "R" in parameter_value:
        return scale_rgb(Theme.ENCODER_PAN_RIGHT, ENCODER_PARAMETER_BRIGHTNESS)
    if "L" in parameter_value:
        return scale_rgb(Theme.ENCODER_PAN_LEFT, ENCODER_PARAMETER_BRIGHTNESS)
    return scale_rgb(Theme.ENCODER_PAN_CENTER, ENCODER_CENTER_BRIGHTNESS)
