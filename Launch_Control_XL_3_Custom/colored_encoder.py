from Live.Device import Device
from Live.MixerDevice import MixerDevice
from ableton.v2.control_surface import LiveObjectDecorator
from ableton.v3.control_surface.elements import EncoderElement
from ableton.v3.control_surface.midi import CC_STATUS, SYSEX_END
from .colors import Rgb
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER
from .custom_parameter_value_rules import (
    CUSTOM_DEVICE_PARAMETER_VALUE_RULES,
    CUSTOM_GLOBAL_PARAMETER_VALUE_RULES,
)
from .custom_parameter_utils import (
    build_device_value_rule_index,
    build_global_parameter_rule_index,
    build_global_value_rule_index,
    build_mode_switch_rules_index,
    compact_name,
    normalize_device_key,
    normalize_name,
)
import logging
import math

RGB_SYSEX_PREFIX = (240, 0, 32, 41, 2, 21, 1, 83)
ENCODER_LED_BRIGHTNESS_SCALE = 0.5
MONOTONE_MIN_RGB = (6, 6, 6)
MONOTONE_CENTER_RGB = (44, 44, 44)
MONOTONE_MAX_RGB = (96, 96, 96)
MONOTONE_MIN_VALUE = 0
MONOTONE_CENTER_VALUE = 64
MONOTONE_MAX_VALUE = 127
DEVICE_VALUE_COLOR_BINS = (
    (72, 18, 112),   # low: purple
    (64, 24, 112),   # indigo (more purple, less green)
    (8, 84, 127),    # blue (deeper blue/cyan split from indigo)
    (10, 112, 38),   # green
    (52, 127, 4),    # yellow-green (lime)
    (127, 127, 0),   # yellow (clear pure yellow)
    (127, 72, 0),    # orange (clear amber/orange)
    (112, 18, 14),   # high: red
)
DEVICE_VALUE_COLOR_BIN_COUNT = 8
SIMPLE_COLOR_TO_RGB = {
    0: (0, 0, 0),
    1: (48, 48, 48),      # WHITE_HALF
    2: (64, 10, 10),      # DARK_RED
    3: (127, 127, 127),   # WHITE
    5: (127, 12, 12),     # RED
    7: (127, 42, 42),     # RED_HALF
    17: (88, 127, 10),    # YELLOW_GREEN
    21: (12, 127, 24),    # GREEN
    27: (36, 127, 52),    # GREEN_HALF
    39: (8, 112, 104),    # TURQUOISE
    41: (14, 54, 127),    # BLUE
    43: (44, 84, 127),    # BLUE_HALF
    47: (10, 34, 96),     # DARK_BLUE
    53: (84, 18, 120),    # PURPLE
    83: (104, 64, 14),    # ORANGE_HALF
    92: (48, 98, 127),    # LIGHT_BLUE
    96: (127, 56, 8),     # ORANGE
    97: (127, 116, 8),    # YELLOW
    103: (16, 16, 16),    # WHITE_DIM / DARK_GREEN(shared value)
}
MODE_SWITCH_RULES_INDEX = build_mode_switch_rules_index(CUSTOM_DEVICE_PARAMETER_ORDER)


GLOBAL_MODE_SWITCH_RULES = build_global_parameter_rule_index(CUSTOM_DEVICE_PARAMETER_ORDER)
VALUE_RULES_INDEX = build_device_value_rule_index(CUSTOM_DEVICE_PARAMETER_VALUE_RULES)
GLOBAL_VALUE_RULES = build_global_value_rule_index(CUSTOM_GLOBAL_PARAMETER_VALUE_RULES)
LOGGER = logging.getLogger(__name__)
DEBUG_MODE_SWITCH_TARGETS = ("l division", "r division")


def _normalize_parameter_value(parameter):
    parameter_range = parameter.max - parameter.min
    if parameter_range <= 0:
        return 0.0
    normalized = (parameter.value - parameter.min) / parameter_range
    return min(max(normalized, 0.0), 1.0)


def _is_device_parameter(parameter):
    return isinstance(parameter.canonical_parent, (Device, LiveObjectDecorator))


def _clamp_led_channel(value):
    return max(0, min(127, int(round(value))))


def _scale_led_rgb(rgb):
    scaled = []
    for channel in rgb:
        clamped = _clamp_led_channel(channel)
        dimmed = _clamp_led_channel(clamped * ENCODER_LED_BRIGHTNESS_SCALE)
        # Keep very dark colors visible after dimming.
        if clamped > 0 and dimmed == 0:
            dimmed = 1
        scaled.append(dimmed)
    return tuple(scaled)


def _rgb_for_simple_color(color):
    midi_value = getattr(color, "midi_value", None)
    if midi_value is None:
        return None
    rgb = SIMPLE_COLOR_TO_RGB.get(midi_value)
    if rgb is None:
        return None
    return _scale_led_rgb(rgb)


def get_monotone_rgb_for_normalized_value(normalized):
    value_7bit = _clamp_led_channel(normalized * 127.0)
    if value_7bit == MONOTONE_MIN_VALUE:
        base = MONOTONE_MIN_RGB
    elif value_7bit == MONOTONE_CENTER_VALUE:
        base = MONOTONE_CENTER_RGB
    elif value_7bit == MONOTONE_MAX_VALUE:
        base = MONOTONE_MAX_RGB
    else:
        return None
    return _scale_led_rgb(base)


def get_monotone_rgb_for_parameter(parameter):
    try:
        normalized = _normalize_parameter_value(parameter)
    except Exception:
        normalized = None
    if normalized is None:
        return None
    return get_monotone_rgb_for_normalized_value(normalized)


def get_rgb_for_device_parameter_value(parameter):
    normalized = _normalize_parameter_value(parameter)
    bin_index = min(int(normalized * DEVICE_VALUE_COLOR_BIN_COUNT), DEVICE_VALUE_COLOR_BIN_COUNT - 1)
    return _scale_led_rgb(DEVICE_VALUE_COLOR_BINS[bin_index])


def get_color_for_parameter(parameter):
    if _is_device_parameter(parameter):
        return Rgb.WHITE
    parent = parameter.canonical_parent
    if isinstance(parent, MixerDevice):
        return Rgb.LIGHT_BLUE if parameter.name == 'Track Volume' else Rgb.TURQUOISE
    if "Loop" in parameter.name:
        return Rgb.YELLOW
    if "Vertical" in parameter.name:
        return Rgb.TURQUOISE
    if "Tempo" in parameter.name:
        return Rgb.ORANGE
    return Rgb.WHITE


def get_color_for_pan_value(value):
    if 'R' in value:
        return Rgb.ORANGE
    if "L" in value:
        return Rgb.DARK_BLUE
    return Rgb.WHITE_HALF


def _resolve_device_mode_switch_rules(parameter):
    return _resolve_device_rules(parameter, MODE_SWITCH_RULES_INDEX)


def _resolve_device_value_rules(parameter):
    return _resolve_device_rules(parameter, VALUE_RULES_INDEX)


def _resolve_device_rules(parameter, rules_index):
    parent = getattr(parameter, "canonical_parent", None)
    if parent is None:
        return None
    # Some Live wrappers keep the actual device multiple levels above.
    hops = 0
    while hops < 6 and not hasattr(parent, "class_name") and hasattr(parent, "canonical_parent"):
        next_parent = getattr(parent, "canonical_parent", None)
        if next_parent is None or next_parent is parent:
            break
        parent = next_parent
        hops += 1
    keys = (
        getattr(parent, "name", ""),
        getattr(parent, "class_name", ""),
        getattr(parent, "class_display_name", ""),
    )
    for key in keys:
        normalized = normalize_device_key(key)
        if not normalized:
            continue
        if normalized in rules_index:
            return rules_index[normalized]
    return None


def _rule_options_for_parameter(parameter_rules, parameter_name):
    if not parameter_rules or not parameter_name:
        return None
    if not isinstance(parameter_rules, dict):
        return None
    if parameter_name in parameter_rules:
        return parameter_rules[parameter_name]
    normalized_requested = normalize_name(parameter_name)
    compact_requested = compact_name(parameter_name)
    for key, options in parameter_rules.items():
        if not isinstance(key, str):
            continue
        if normalize_name(key) == normalized_requested:
            return options
        compact_key = compact_name(key)
        if compact_key == compact_requested:
            return options
        if compact_requested and (compact_requested in compact_key or compact_key in compact_requested):
            return options
    return None


def _value_rule_options_for_parameter(parameter_rules, parameter_name):
    if not parameter_rules or not parameter_name:
        return None
    if not isinstance(parameter_rules, dict):
        return None
    return parameter_rules.get(normalize_name(parameter_name))


def _global_rule_options_for_parameter(parameter_name):
    if not parameter_name:
        return None
    key = compact_name(parameter_name)
    if not key:
        return None
    return GLOBAL_MODE_SWITCH_RULES.get(key)


def _global_value_rule_options_for_parameter(parameter_name):
    if not parameter_name:
        return None
    return GLOBAL_VALUE_RULES.get(normalize_name(parameter_name))


def _resolve_parameter_value_rule(parameter):
    parameter_name = getattr(parameter, "name", "")
    parameter_rules = _resolve_device_value_rules(parameter)
    options = None
    if parameter_rules is not None:
        options = _value_rule_options_for_parameter(parameter_rules, parameter_name)
    if options is None:
        options = _global_value_rule_options_for_parameter(parameter_name)
    return options


def _is_debug_mode_switch_target(parameter_name):
    normalized = normalize_name(parameter_name)
    return normalized in DEBUG_MODE_SWITCH_TARGETS


def _is_int_like(value):
    try:
        return float(value).is_integer()
    except (TypeError, ValueError):
        return False


def _derived_mode_count(parameter):
    value_items = getattr(parameter, "value_items", None)
    if value_items:
        try:
            count = len(tuple(value_items))
            if count >= 2:
                return count
        except (RuntimeError, TypeError):
            pass
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
    except (AttributeError, TypeError, ValueError):
        return None
    if maximum <= minimum:
        return None
    if _is_int_like(minimum) and _is_int_like(maximum):
        count = int(round(maximum - minimum)) + 1
        if 2 <= count <= 4096:
            return count
    return None


def _resolve_mode_count(parameter, options):
    if options in (None, {}, "auto"):
        return _derived_mode_count(parameter)
    if isinstance(options, dict):
        mode_count = options.get("mode_count")
        if mode_count in (None, "auto"):
            return _derived_mode_count(parameter)
        try:
            mode_count = int(mode_count)
        except (TypeError, ValueError):
            return None
        return mode_count if mode_count >= 2 else None
    return _derived_mode_count(parameter)


def _float_option(options, name, default=None):
    if not isinstance(options, dict):
        return default
    value = options.get(name, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int_option(options, name, default=None):
    value = _float_option(options, name, default)
    if value is None:
        return default
    try:
        return int(round(value))
    except (TypeError, ValueError):
        return default


def _encoder_input_unit(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return 0
    if value == 64:
        return 0
    return 1 if value > 64 else -1


def _consume_value_rule_input(accumulators, key, value, options):
    input_unit = _encoder_input_unit(value)
    if input_unit == 0:
        return 0
    threshold = max(1, _int_option(options, "input_threshold", 1))
    if threshold <= 1:
        accumulators[key] = 0
        return input_unit

    previous = accumulators.get(key, 0)
    if previous and (previous > 0) != (input_unit > 0):
        previous = 0
    accumulated = previous + input_unit
    if abs(accumulated) < threshold:
        accumulators[key] = accumulated
        return 0

    direction = 1 if accumulated > 0 else -1
    remainder = accumulated - (direction * threshold)
    if abs(remainder) >= threshold:
        remainder = direction * (threshold - 1)
    accumulators[key] = remainder
    return direction


def _handle_parameter_value_rule_input(parameter, value, options, accumulators, accumulator_key):
    if isinstance(options, dict) and options.get("input_mode") == "cc_bins":
        return _handle_value_rule_cc_bin_input(parameter, value, options, accumulators, accumulator_key)
    direction = _consume_value_rule_input(accumulators, accumulator_key, value, options)
    if direction == 0:
        return _snap_parameter_to_value_rule_grid(parameter, options), 0
    return _step_parameter_by_value_rule(parameter, direction, options), direction


def _handle_value_rule_cc_bin_input(parameter, value, options, accumulators, accumulator_key):
    input_unit = _encoder_input_unit(value)
    if input_unit == 0:
        return False, 0
    resolution = max(2, _int_option(options, "input_resolution", 128))
    context = _value_rule_display_context(parameter, options)
    if context is None:
        return False, 0

    step_size, center, minimum, maximum, current, display_minimum, display_maximum = context
    min_index = int(math.ceil((display_minimum - center) / step_size))
    max_index = int(math.floor((display_maximum - center) / step_size))
    if min_index > max_index:
        return False, 0
    bin_count = max_index - min_index + 1
    if bin_count < 2:
        return False, 0

    display_current = _parameter_value_to_display_value(
        minimum,
        maximum,
        current,
        display_minimum,
        display_maximum,
    )
    current_bin = _nearest_display_bin(display_current, step_size, center, min_index, max_index)
    if current_bin is None:
        return False, 0

    state = accumulators.get(accumulator_key)
    if not isinstance(state, dict) or state.get("bin_count") != bin_count or state.get("resolution") != resolution:
        state = _cc_bin_state_for_bin(current_bin, bin_count, resolution)
    elif state.get("bin") != current_bin:
        state = _cc_bin_state_for_bin(current_bin, bin_count, resolution)

    previous_bin = state["bin"]
    virtual_value = min(max(state["virtual"] + input_unit, 0), resolution - 1)
    target_bin = min(int((virtual_value * bin_count) / resolution), bin_count - 1)
    state = {"virtual": virtual_value, "bin": target_bin, "bin_count": bin_count, "resolution": resolution}
    accumulators[accumulator_key] = state

    display_target = center + ((min_index + target_bin) * step_size)
    target_value = _display_value_to_parameter_value(
        minimum,
        maximum,
        display_target,
        display_minimum,
        display_maximum,
    )
    handled = _set_parameter_value_if_changed(parameter, current, target_value)
    applied_direction = 0
    if target_bin > previous_bin:
        applied_direction = 1
    elif target_bin < previous_bin:
        applied_direction = -1
    return handled, applied_direction


def _value_rule_display_context(parameter, options):
    step_size = _float_option(options, "step_size")
    center = _float_option(options, "center", 0.0)
    if step_size is None or step_size <= 0:
        return None
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    if maximum < minimum:
        return None
    display_minimum = _float_option(options, "display_min", minimum)
    display_maximum = _float_option(options, "display_max", maximum)
    if display_maximum < display_minimum:
        return None
    return step_size, center, minimum, maximum, current, display_minimum, display_maximum


def _cc_bin_state_for_bin(bin_index, bin_count, resolution):
    virtual = int(round(((float(bin_index) + 0.5) * float(resolution) / float(bin_count)) - 0.5))
    return {
        "virtual": min(max(virtual, 0), resolution - 1),
        "bin": bin_index,
        "bin_count": bin_count,
        "resolution": resolution,
    }


def _nearest_display_bin(display_value, step_size, center, min_index, max_index):
    normalized = (display_value - center) / step_size
    target_index = min(max(int(round(normalized)), min_index), max_index)
    return target_index - min_index


def _parameter_value_to_display_value(minimum, maximum, current, display_minimum, display_maximum):
    parameter_range = maximum - minimum
    display_range = display_maximum - display_minimum
    if parameter_range <= 0 or display_range <= 0:
        return current
    normalized = (current - minimum) / parameter_range
    return display_minimum + (normalized * display_range)


def _display_value_to_parameter_value(minimum, maximum, display_value, display_minimum, display_maximum):
    parameter_range = maximum - minimum
    display_range = display_maximum - display_minimum
    if parameter_range <= 0 or display_range <= 0:
        return display_value
    normalized = (display_value - display_minimum) / display_range
    return minimum + (normalized * parameter_range)


def _step_parameter_by_value_rule(parameter, direction, options):
    step_size = _float_option(options, "step_size")
    center = _float_option(options, "center", 0.0)
    if step_size is None or step_size <= 0:
        return False
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False
    if maximum < minimum:
        return False

    display_minimum = _float_option(options, "display_min")
    display_maximum = _float_option(options, "display_max")
    if display_minimum is not None and display_maximum is not None:
        return _step_parameter_by_display_value_rule(
            parameter,
            direction,
            step_size,
            center,
            minimum,
            maximum,
            current,
            display_minimum,
            display_maximum,
        )

    return _step_parameter_by_native_value_rule(parameter, direction, step_size, center, minimum, maximum, current)


def _snap_parameter_to_value_rule_grid(parameter, options):
    step_size = _float_option(options, "step_size")
    center = _float_option(options, "center", 0.0)
    if step_size is None or step_size <= 0:
        return False
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return False
    if maximum < minimum:
        return False

    display_minimum = _float_option(options, "display_min")
    display_maximum = _float_option(options, "display_max")
    if display_minimum is not None and display_maximum is not None:
        return _snap_parameter_to_display_value_grid(
            parameter,
            step_size,
            center,
            minimum,
            maximum,
            current,
            display_minimum,
            display_maximum,
        )

    target_value = _nearest_stepped_value(current, step_size, center, minimum, maximum)
    if target_value is None:
        return False
    return _set_parameter_value_if_changed(parameter, current, target_value)


def _snap_parameter_to_display_value_grid(
    parameter,
    step_size,
    center,
    minimum,
    maximum,
    current,
    display_minimum,
    display_maximum,
):
    parameter_range = maximum - minimum
    display_range = display_maximum - display_minimum
    if parameter_range <= 0 or display_range <= 0:
        return False
    normalized = (current - minimum) / parameter_range
    display_current = display_minimum + (normalized * display_range)
    display_target = _nearest_stepped_value(
        display_current,
        step_size,
        center,
        display_minimum,
        display_maximum,
    )
    if display_target is None:
        return False
    target_normalized = (display_target - display_minimum) / display_range
    target_value = minimum + (target_normalized * parameter_range)
    return _set_parameter_value_if_changed(parameter, current, target_value)


def _step_parameter_by_native_value_rule(parameter, direction, step_size, center, minimum, maximum, current):
    target_value = _stepped_value_for_direction(current, direction, step_size, center, minimum, maximum)
    if target_value is None:
        return False
    return _set_parameter_value_if_changed(parameter, current, target_value)


def _step_parameter_by_display_value_rule(
    parameter,
    direction,
    step_size,
    center,
    minimum,
    maximum,
    current,
    display_minimum,
    display_maximum,
):
    parameter_range = maximum - minimum
    display_range = display_maximum - display_minimum
    if parameter_range <= 0 or display_range <= 0:
        return False
    normalized = (current - minimum) / parameter_range
    display_current = display_minimum + (normalized * display_range)
    display_target = _stepped_value_for_direction(
        display_current,
        direction,
        step_size,
        center,
        display_minimum,
        display_maximum,
    )
    if display_target is None:
        return False
    target_normalized = (display_target - display_minimum) / display_range
    target_value = minimum + (target_normalized * parameter_range)
    return _set_parameter_value_if_changed(parameter, current, target_value)


def _stepped_value_for_direction(current, direction, step_size, center, minimum, maximum):
    nearest_value = _nearest_stepped_value(current, step_size, center, minimum, maximum)
    if nearest_value is None:
        return None
    min_index = int(math.ceil((minimum - center) / step_size))
    max_index = int(math.floor((maximum - center) / step_size))

    normalized = (current - center) / step_size
    epsilon = 1e-9
    nearest_index = int(round(normalized))
    is_on_step = abs(normalized - nearest_index) <= epsilon
    if direction > 0:
        target_index = nearest_index + 1 if is_on_step else int(math.floor(normalized)) + 1
    else:
        target_index = nearest_index - 1 if is_on_step else int(math.ceil(normalized)) - 1
    target_index = min(max(target_index, min_index), max_index)
    target_value = center + (target_index * step_size)

    if direction > 0 and target_value < current - epsilon:
        return current
    if direction < 0 and target_value > current + epsilon:
        return current
    return target_value


def _nearest_stepped_value(current, step_size, center, minimum, maximum):
    min_index = int(math.ceil((minimum - center) / step_size))
    max_index = int(math.floor((maximum - center) / step_size))
    if min_index > max_index:
        return None
    normalized = (current - center) / step_size
    target_index = min(max(int(round(normalized)), min_index), max_index)
    return center + (target_index * step_size)


def _set_parameter_value_if_changed(parameter, current, target_value):
    epsilon = 1e-9
    if abs(target_value - current) <= epsilon:
        return True
    try:
        parameter.value = target_value
    except (RuntimeError, ValueError, TypeError):
        return False
    return True


def _step_parameter_by_mode_count(parameter, direction, mode_count):
    value_items = getattr(parameter, "value_items", None)
    if value_items:
        try:
            item_count = len(tuple(value_items))
            minimum = float(parameter.min)
            maximum = float(parameter.max)
            current = float(parameter.value)
        except (RuntimeError, TypeError, ValueError, AttributeError):
            item_count = 0
        if item_count >= 2 and maximum > minimum:
            source_steps = item_count - 1
            source_norm = (current - minimum) / (maximum - minimum)
            source_index = int(round(min(max(source_norm, 0.0), 1.0) * source_steps))
            if mode_count is None or mode_count < 2:
                target_source_index = min(max(source_index + direction, 0), source_steps)
            else:
                virtual_steps = mode_count - 1
                virtual_index = int(round((float(source_index) / float(source_steps)) * virtual_steps))
                target_virtual_index = min(max(virtual_index + direction, 0), virtual_steps)
                target_source_index = int(round((float(target_virtual_index) / float(virtual_steps)) * source_steps))
            if target_source_index == source_index:
                return True
            target_value = minimum + (float(target_source_index) / float(source_steps)) * (maximum - minimum)
            try:
                parameter.value = target_value
            except (RuntimeError, ValueError, TypeError):
                return False
            return True

    try:
        is_quantized = bool(getattr(parameter, "is_quantized", False))
    except RuntimeError:
        is_quantized = False
    # mode_count 明示時は量子化パラメータでも指定モード数を優先する。
    if is_quantized and (mode_count is None or mode_count < 2):
        try:
            current = int(round(float(parameter.value)))
            minimum = int(round(float(parameter.min)))
            maximum = int(round(float(parameter.max)))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False
        if maximum < minimum:
            return False
        target = min(max(current + direction, minimum), maximum)
        if target == current:
            return True
        try:
            parameter.value = float(target)
        except (RuntimeError, ValueError, TypeError):
            return False
        return True
    if mode_count is None or mode_count < 2:
        return False
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
        current = float(parameter.value)
    except (AttributeError, TypeError, ValueError):
        return False
    parameter_range = maximum - minimum
    if parameter_range <= 0:
        return False
    step_count = mode_count - 1
    normalized = (current - minimum) / parameter_range
    current_index = int(round(normalized * step_count))
    target_index = min(max(current_index + direction, 0), step_count)
    if target_index == current_index:
        return True
    target_value = minimum + (float(target_index) / float(step_count)) * parameter_range
    try:
        parameter.value = target_value
    except (RuntimeError, ValueError):
        return False
    return True


class ColoredEncoderElement(EncoderElement):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._led_color_cc = self.message_identifier() - 64
        self._is_assigned_to_pan = False
        self._value_rule_input_accumulators = {}

    def reset(self):
        self._send_led_color(Rgb.OFF)

    def _update_parameter_listeners(self):
        self._is_assigned_to_pan = False
        self._value_rule_input_accumulators = {}
        if self.is_mapped_to_parameter():
            self._is_assigned_to_pan = self.mapped_object.name == "Track Panning"
            self._send_led_for_parameter()
        else:
            self._send_led_color(Rgb.OFF)
        super()._update_parameter_listeners()

    def _send_led_color(self, color):
        # Prefer RGB sysex for encoder LEDs so dimming is consistent across color paths.
        rgb = _rgb_for_simple_color(color)
        if rgb is not None:
            self._send_led_rgb(rgb)
            return
        message = (CC_STATUS, self._led_color_cc, color.midi_value)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _send_led_rgb(self, rgb):
        r, g, b = rgb
        message = RGB_SYSEX_PREFIX + (self._led_color_cc, r, g, b, SYSEX_END)
        if message != self._last_sent_message:
            self.send_midi(message)
            self._last_sent_message = message

    def _parameter_value_changed(self):
        if not self.is_mapped_to_parameter():
            return
        self._send_led_for_parameter()

    def _send_led_for_parameter(self):
        parameter = self.mapped_object
        monotone_rgb = get_monotone_rgb_for_parameter(parameter)
        if monotone_rgb is not None:
            self._send_led_rgb(monotone_rgb)
            return
        if self._is_assigned_to_pan:
            self._send_led_color(get_color_for_pan_value(self.parameter_value))
            return
        if _is_device_parameter(parameter):
            self._send_led_rgb(get_rgb_for_device_parameter_value(parameter))
            return
        self._send_led_color(get_color_for_parameter(parameter))

    def _handle_mode_switch_override(self, value):
        if value == 64 or not self.is_mapped_to_parameter():
            return False
        parameter = self.mapped_object
        parameter_name = getattr(parameter, "name", "")
        debug_target = _is_debug_mode_switch_target(parameter_name)
        parameter_rules = _resolve_device_mode_switch_rules(parameter)
        options = None
        if parameter_rules is not None:
            options = _rule_options_for_parameter(parameter_rules, parameter_name)
        if options is None:
            options = _global_rule_options_for_parameter(parameter_name)
        direction = 1 if value > 64 else -1
        value_rule_options = _resolve_parameter_value_rule(parameter)
        if value_rule_options is not None:
            handled, applied_direction = _handle_parameter_value_rule_input(
                parameter,
                value,
                value_rule_options,
                self._value_rule_input_accumulators,
                (id(parameter), parameter_name),
            )
            if not handled:
                return False
            if applied_direction:
                try:
                    LOGGER.info(
                        "LCXL3 value-rule override: parameter=%s options=%s value=%s direction=%s",
                        parameter_name,
                        value_rule_options,
                        value,
                        applied_direction,
                    )
                except Exception:
                    pass
                self._parameter_value_changed()
            return True
        if options is None:
            if debug_target:
                LOGGER.info("LCXL3 mode-switch skip: no rule matched parameter=%s", parameter_name)
            return False
        mode_count = _resolve_mode_count(parameter, options)
        if not _step_parameter_by_mode_count(parameter, direction, mode_count):
            if debug_target:
                LOGGER.info(
                    "LCXL3 mode-switch skip: step failed parameter=%s mode_count=%s value=%s",
                    parameter_name,
                    mode_count,
                    value,
                )
            return False
        try:
            LOGGER.info(
                "LCXL3 mode-switch override: parameter=%s mode_count=%s value=%s direction=%s",
                parameter_name,
                mode_count,
                value,
                direction,
            )
        except Exception:
            pass
        self._parameter_value_changed()
        return True

    def receive_value(self, value):
        if self._handle_mode_switch_override(value):
            return
        super().receive_value(value)

    def notify_value(self, value):
        if self._handle_mode_switch_override(value):
            return
        super().notify_value(value)
