from Live.Device import Device
from Live.MixerDevice import MixerDevice
from ableton.v2.control_surface import LiveObjectDecorator
from ableton.v3.control_surface.elements import EncoderElement
from ableton.v3.control_surface.midi import CC_STATUS, SYSEX_END
from .colors import Rgb
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER
import re
import logging

RGB_SYSEX_PREFIX = (240, 0, 32, 41, 2, 21, 1, 83)
DEVICE_VALUE_COLOR_BINS = (
    (72, 18, 112),   # low: purple
    (40, 44, 112),   # indigo
    (20, 70, 112),   # blue
    (10, 112, 38),   # green
    (72, 112, 12),   # yellow-green
    (112, 98, 10),   # yellow
    (112, 56, 10),   # orange
    (112, 18, 14),   # high: red
)
DEVICE_VALUE_COLOR_BIN_COUNT = 8
CUSTOM_DEVICE_ALIASES = {
    "instrumentvector": "wavetable",
    "wavetable": "instrumentvector",
    "hybrid": "reverb",
    "reverb": "hybrid",
}


def _normalize_name(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _compact_name(value):
    return re.sub(r"[^a-z0-9]+", "", _normalize_name(value))


def _normalize_device_key(value):
    normalized = _normalize_name(value)
    if not normalized:
        return normalized
    parts = normalized.split(" ")
    while parts and parts[-1].isdigit():
        parts.pop()
    return " ".join(parts)


def _build_mode_switch_rules_index(raw_mapping):
    indexed = {}
    for device_name, custom_order in (raw_mapping or {}).items():
        parameter_rules = {}
        for entry in custom_order:
            if not isinstance(entry, dict):
                continue
            for parameter_name, options in entry.items():
                if parameter_name is None:
                    continue
                parameter_rules[str(parameter_name)] = options
        if not parameter_rules:
            continue
        normalized = _normalize_device_key(device_name)
        if not normalized:
            continue
        indexed[normalized] = parameter_rules
        alias = CUSTOM_DEVICE_ALIASES.get(normalized)
        if alias:
            indexed[alias] = parameter_rules
    return indexed


MODE_SWITCH_RULES_INDEX = _build_mode_switch_rules_index(CUSTOM_DEVICE_PARAMETER_ORDER)


def _build_global_parameter_rule_index(raw_mapping):
    indexed = {}
    for _, custom_order in (raw_mapping or {}).items():
        for entry in custom_order:
            if not isinstance(entry, dict):
                continue
            for parameter_name, options in entry.items():
                if parameter_name is None:
                    continue
                key = _compact_name(parameter_name)
                if key and key not in indexed:
                    indexed[key] = options
    return indexed


GLOBAL_MODE_SWITCH_RULES = _build_global_parameter_rule_index(CUSTOM_DEVICE_PARAMETER_ORDER)
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


def get_rgb_for_device_parameter_value(parameter):
    normalized = _normalize_parameter_value(parameter)
    bin_index = min(int(normalized * DEVICE_VALUE_COLOR_BIN_COUNT), DEVICE_VALUE_COLOR_BIN_COUNT - 1)
    return DEVICE_VALUE_COLOR_BINS[bin_index]


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
    normalized_keys = []
    for key in keys:
        normalized = _normalize_device_key(key)
        if not normalized:
            continue
        normalized_keys.append(normalized)
        if normalized in MODE_SWITCH_RULES_INDEX:
            return MODE_SWITCH_RULES_INDEX[normalized]
    for device_key in normalized_keys:
        for custom_key, rules in MODE_SWITCH_RULES_INDEX.items():
            if custom_key in device_key or device_key in custom_key:
                return rules
    return None


def _rule_options_for_parameter(parameter_rules, parameter_name):
    if not parameter_rules or not parameter_name:
        return None
    if not isinstance(parameter_rules, dict):
        return None
    if parameter_name in parameter_rules:
        return parameter_rules[parameter_name]
    normalized_requested = _normalize_name(parameter_name)
    compact_requested = _compact_name(parameter_name)
    for key, options in parameter_rules.items():
        if not isinstance(key, str):
            continue
        if _normalize_name(key) == normalized_requested:
            return options
        compact_key = _compact_name(key)
        if compact_key == compact_requested:
            return options
        if compact_requested and (compact_requested in compact_key or compact_key in compact_requested):
            return options
    return None


def _global_rule_options_for_parameter(parameter_name):
    if not parameter_name:
        return None
    key = _compact_name(parameter_name)
    if not key:
        return None
    return GLOBAL_MODE_SWITCH_RULES.get(key)


def _is_debug_mode_switch_target(parameter_name):
    normalized = _normalize_name(parameter_name)
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

    def reset(self):
        self._send_led_color(Rgb.OFF)

    def _update_parameter_listeners(self):
        self._is_assigned_to_pan = False
        if self.is_mapped_to_parameter():
            self._is_assigned_to_pan = self.mapped_object.name == "Track Panning"
            if _is_device_parameter(self.mapped_object):
                self._send_led_rgb(get_rgb_for_device_parameter_value(self.mapped_object))
            else:
                self._send_led_color(get_color_for_parameter(self.mapped_object))
        else:
            self._send_led_color(Rgb.OFF)
        super()._update_parameter_listeners()

    def _send_led_color(self, color):
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
        if self._is_assigned_to_pan:
            self._send_led_color(get_color_for_pan_value(self.parameter_value))
            return
        if _is_device_parameter(self.mapped_object):
            self._send_led_rgb(get_rgb_for_device_parameter_value(self.mapped_object))
            return
        self._send_led_color(get_color_for_parameter(self.mapped_object))

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
        if options is None:
            if debug_target:
                LOGGER.info("LCXL3 mode-switch skip: no rule matched parameter=%s", parameter_name)
            return False
        mode_count = _resolve_mode_count(parameter, options)
        direction = 1 if value > 64 else -1
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
