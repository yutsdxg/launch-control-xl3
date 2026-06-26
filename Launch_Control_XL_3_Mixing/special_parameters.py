SATURN_2_DEVICE_NAME = "saturn 2"
SATURN_BAND_1_STYLE_PARAMETER_NAME = "band 1 style"
SATURN_ALLOWED_BAND_1_STYLES = ("Warm Tube", "Warm Tape", "Warm Transformer")
SATURN_BAND_1_STYLE_FALLBACK_ITEM_COUNT = 28
SATURN_ALLOWED_BAND_1_STYLE_FALLBACK_INDEXES = (2, 6, 22)
SMALL_DISCRETE_PARAMETER_MAX_ITEM_COUNT = 5
REDUCED_SENSITIVITY_INPUT_THRESHOLD = 2
ADPTR_METRIC_AB_DEVICE_NAME = "adptr metricab"
ADPTR_METRIC_AB_SMALL_DISCRETE_COUNTS = {
    "selected cue": 4,
    "ab switch": 2,
}


def _normalized_text(value):
    try:
        return " ".join(str(value).strip().lower().split())
    except (RuntimeError, TypeError, ValueError):
        return ""


def _parameter_device(parameter):
    parent = getattr(parameter, "canonical_parent", None)
    for _ in range(6):
        if parent is None:
            return None
        if any(hasattr(parent, attr) for attr in ("parameters", "class_name", "class_display_name")):
            return parent
        try:
            parent = getattr(parent, "canonical_parent", None)
        except RuntimeError:
            return None
    return None


def _object_attr_text(obj, attr):
    if obj is None:
        return ""
    try:
        return str(getattr(obj, attr, ""))
    except RuntimeError:
        return ""


def _is_saturn_2_device(device):
    if device is None:
        return False
    for attr in ("name", "class_display_name", "class_name"):
        name = _normalized_text(_object_attr_text(device, attr))
        compact_name = name.replace(" ", "")
        if SATURN_2_DEVICE_NAME in name or "saturn2" in compact_name:
            return True
    return False


def _is_adptr_metric_ab_device(device):
    if device is None:
        return False
    for attr in ("name", "class_display_name", "class_name"):
        name = _normalized_text(_object_attr_text(device, attr))
        if name == ADPTR_METRIC_AB_DEVICE_NAME:
            return True
    return False


def _is_saturn_band_1_style_parameter(parameter):
    try:
        parameter_name = _normalized_text(parameter.name)
    except (AttributeError, RuntimeError):
        return False
    return (
        parameter_name == SATURN_BAND_1_STYLE_PARAMETER_NAME
        and _is_saturn_2_device(_parameter_device(parameter))
    )


def _value_items(parameter):
    try:
        value_items = getattr(parameter, "value_items", None)
    except RuntimeError:
        return ()
    if not value_items:
        return ()
    try:
        return tuple(value_items)
    except (RuntimeError, TypeError):
        return ()


def _saturn_allowed_style_indexes(parameter):
    items = _value_items(parameter)
    if len(items) < 2:
        return ()
    item_index_by_name = {_normalized_text(item): index for index, item in enumerate(items)}
    indexes = []
    for style in SATURN_ALLOWED_BAND_1_STYLES:
        index = item_index_by_name.get(_normalized_text(style))
        if index is None:
            return ()
        indexes.append(index)
    return tuple(indexes)


def _saturn_style_mapping(parameter):
    items = _value_items(parameter)
    indexes = _saturn_allowed_style_indexes(parameter)
    if len(items) >= 2 and len(indexes) == len(SATURN_ALLOWED_BAND_1_STYLES):
        return len(items), indexes
    if not items and _is_saturn_band_1_style_parameter(parameter):
        return SATURN_BAND_1_STYLE_FALLBACK_ITEM_COUNT, SATURN_ALLOWED_BAND_1_STYLE_FALLBACK_INDEXES
    return len(items), indexes


def _parameter_bounds(parameter):
    try:
        minimum = float(parameter.min)
        maximum = float(parameter.max)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return (minimum, maximum) if maximum > minimum else None


def _is_int_like(value):
    try:
        return float(value).is_integer()
    except (TypeError, ValueError):
        return False


def _small_discrete_item_count(parameter):
    items = _value_items(parameter)
    if 2 <= len(items) <= SMALL_DISCRETE_PARAMETER_MAX_ITEM_COUNT:
        return len(items)
    try:
        is_quantized = bool(getattr(parameter, "is_quantized", False))
    except RuntimeError:
        is_quantized = False
    if not is_quantized:
        return _fallback_small_discrete_item_count(parameter)
    bounds = _parameter_bounds(parameter)
    if bounds is None:
        return _fallback_small_discrete_item_count(parameter)
    minimum, maximum = bounds
    if not _is_int_like(minimum) or not _is_int_like(maximum):
        return _fallback_small_discrete_item_count(parameter)
    count = int(round(maximum - minimum)) + 1
    if 2 <= count <= SMALL_DISCRETE_PARAMETER_MAX_ITEM_COUNT:
        return count
    return _fallback_small_discrete_item_count(parameter)


def _fallback_small_discrete_item_count(parameter):
    if not _is_adptr_metric_ab_device(_parameter_device(parameter)):
        return None
    try:
        parameter_name = _normalized_text(parameter.name)
    except (AttributeError, RuntimeError):
        return None
    return ADPTR_METRIC_AB_SMALL_DISCRETE_COUNTS.get(parameter_name)


def _is_small_discrete_parameter(parameter):
    return _small_discrete_item_count(parameter) is not None


def _parameter_index(parameter, item_count):
    if item_count < 2:
        return None
    try:
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    bounds = _parameter_bounds(parameter)
    if bounds is None:
        index = int(round(current))
        return min(max(index, 0), item_count - 1)
    minimum, maximum = bounds
    normalized = (current - minimum) / (maximum - minimum)
    return int(round(min(max(normalized, 0.0), 1.0) * (item_count - 1)))


def _parameter_value_for_index(parameter, index, item_count):
    bounds = _parameter_bounds(parameter)
    if bounds is None:
        return float(index)
    minimum, maximum = bounds
    return minimum + (float(index) / float(item_count - 1)) * (maximum - minimum)


def _directional_allowed_index(current_index, allowed_indexes, direction):
    sorted_indexes = tuple(sorted(allowed_indexes))
    if direction > 0:
        for index in sorted_indexes:
            if index > current_index:
                return index
        return sorted_indexes[-1]
    for index in reversed(sorted_indexes):
        if index < current_index:
            return index
    return sorted_indexes[0]


def _set_parameter_value(parameter, target_value):
    try:
        current = float(parameter.value)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        current = None
    if current is not None and abs(current - target_value) <= 1e-9:
        return
    try:
        parameter.value = target_value
    except (RuntimeError, ValueError, TypeError):
        pass


def _parameter_value(parameter):
    try:
        return getattr(parameter, "value")
    except (AttributeError, RuntimeError):
        return None


def _parameter_min(parameter):
    try:
        return getattr(parameter, "min")
    except (AttributeError, RuntimeError):
        return None


def _parameter_max(parameter):
    try:
        return getattr(parameter, "max")
    except (AttributeError, RuntimeError):
        return None


def is_special_parameter_candidate(parameter):
    if parameter is None:
        return False
    device = _parameter_device(parameter)
    try:
        parameter_name = _normalized_text(parameter.name)
    except (AttributeError, RuntimeError):
        parameter_name = ""
    return (
        parameter_name == SATURN_BAND_1_STYLE_PARAMETER_NAME
        or _is_saturn_2_device(device)
        or _is_small_discrete_parameter(parameter)
    )


def is_handled_special_parameter(parameter):
    return _is_saturn_band_1_style_parameter(parameter) or _is_small_discrete_parameter(parameter)


def special_parameter_step_threshold(parameter):
    if _is_saturn_band_1_style_parameter(parameter):
        return REDUCED_SENSITIVITY_INPUT_THRESHOLD
    item_count = _small_discrete_item_count(parameter)
    if item_count is not None and item_count >= 3:
        return REDUCED_SENSITIVITY_INPUT_THRESHOLD
    return 1


def parameter_debug_info(parameter):
    device = _parameter_device(parameter)
    items = _value_items(parameter)
    return {
        "parameter_name": _object_attr_text(parameter, "name"),
        "device_name": _object_attr_text(device, "name"),
        "device_class_name": _object_attr_text(device, "class_name"),
        "device_class_display_name": _object_attr_text(device, "class_display_name"),
        "value": _parameter_value(parameter),
        "min": _parameter_min(parameter),
        "max": _parameter_max(parameter),
        "value_items_count": len(items),
        "value_items": items,
        "allowed_indexes": _saturn_style_mapping(parameter)[1],
        "small_discrete_item_count": _small_discrete_item_count(parameter),
        "matched": _is_saturn_band_1_style_parameter(parameter),
    }


def _handle_saturn_band_1_style_input(parameter, value):
    if not _is_saturn_band_1_style_parameter(parameter):
        return False
    item_count, allowed_indexes = _saturn_style_mapping(parameter)
    if item_count < 2 or len(allowed_indexes) != len(SATURN_ALLOWED_BAND_1_STYLES):
        return False
    try:
        midi_value = int(value)
    except (TypeError, ValueError):
        return False
    if midi_value == 64:
        return True
    direction = 1 if midi_value > 64 else -1
    current_index = _parameter_index(parameter, item_count)
    if current_index is None:
        return True
    target_index = _directional_allowed_index(current_index, allowed_indexes, direction)
    _set_parameter_value(parameter, _parameter_value_for_index(parameter, target_index, item_count))
    return True


def _handle_small_discrete_parameter_input(parameter, value):
    item_count = _small_discrete_item_count(parameter)
    if item_count is None:
        return False
    try:
        midi_value = int(value)
    except (TypeError, ValueError):
        return False
    if midi_value == 64:
        return True
    direction = 1 if midi_value > 64 else -1
    current_index = _parameter_index(parameter, item_count)
    if current_index is None:
        return True
    target_index = min(max(current_index + direction, 0), item_count - 1)
    _set_parameter_value(parameter, _parameter_value_for_index(parameter, target_index, item_count))
    return True


def handle_special_parameter_input(parameter, value):
    return _handle_saturn_band_1_style_input(parameter, value) or _handle_small_discrete_parameter_input(
        parameter,
        value,
    )
