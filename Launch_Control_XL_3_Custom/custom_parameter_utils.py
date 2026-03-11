import re

DEVICE_ON_PARAMETER_NAME = "Device On"
CUSTOM_DEVICE_ALIASES = {
    "instrumentvector": "wavetable",
    "wavetable": "instrumentvector",
    "instrumentmeld": "meld",
    "meld": "instrumentmeld",
    "hybrid": "reverb",
    "reverb": "hybrid",
}


def normalize_name(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def compact_name(value):
    return re.sub(r"[^a-z0-9]+", "", normalize_name(value))


def normalize_device_key(value):
    normalized = normalize_name(value)
    if not normalized:
        return normalized
    parts = normalized.split(" ")
    while parts and parts[-1].isdigit():
        parts.pop()
    return " ".join(parts)


def is_skip_slot(value):
    return value is None or str(value).strip().upper() == "SKIP"


def extract_custom_entry_name_and_options(entry):
    if is_skip_slot(entry):
        return None, None
    if isinstance(entry, dict):
        for parameter_name, options in entry.items():
            if parameter_name is None:
                continue
            return str(parameter_name), options
        return None, None
    return str(entry), None


def build_device_order_index(raw_mapping):
    result = {}
    for key, order in raw_mapping.items():
        normalized = normalize_device_key(key)
        if not normalized:
            continue
        result[normalized] = tuple(order)
        alias = CUSTOM_DEVICE_ALIASES.get(normalized)
        if alias:
            result[alias] = tuple(order)
    return result


def build_mode_switch_rules_index(raw_mapping):
    indexed = {}
    for device_name, custom_order in (raw_mapping or {}).items():
        parameter_rules = {}
        for entry in custom_order:
            parameter_name, options = extract_custom_entry_name_and_options(entry)
            mode_switch_options = _mode_switch_options(options)
            if parameter_name is None or mode_switch_options is None:
                continue
            parameter_rules[str(parameter_name)] = mode_switch_options
        if not parameter_rules:
            continue
        normalized = normalize_device_key(device_name)
        if not normalized:
            continue
        indexed[normalized] = parameter_rules
        alias = CUSTOM_DEVICE_ALIASES.get(normalized)
        if alias:
            indexed[alias] = parameter_rules
    return indexed


def build_global_parameter_rule_index(raw_mapping):
    indexed = {}
    for _, custom_order in (raw_mapping or {}).items():
        for entry in custom_order:
            parameter_name, options = extract_custom_entry_name_and_options(entry)
            mode_switch_options = _mode_switch_options(options)
            if parameter_name is None or mode_switch_options is None:
                continue
            key = compact_name(parameter_name)
            if key and key not in indexed:
                indexed[key] = mode_switch_options
    return indexed


def resolve_entry_occurrence(options):
    if not isinstance(options, dict):
        return None
    occurrence = options.get("occurrence")
    if occurrence is None:
        return None
    try:
        occurrence = int(occurrence)
    except (TypeError, ValueError):
        return None
    return occurrence if occurrence >= 1 else None


def format_requested_entry(requested_name, options):
    occurrence = resolve_entry_occurrence(options)
    if occurrence is None:
        return requested_name
    return "{} (occurrence={})".format(requested_name, occurrence)


def order_named_items(
    items,
    custom_order,
    append_rest=False,
    get_name=None,
    is_valid_item=None,
    keep_missing_slots=True,
):
    get_name = get_name or _default_get_name
    is_valid_item = is_valid_item or _default_is_valid_item
    used_item_ids = set()
    ordered = []
    missing_requested_names = []

    for entry in custom_order:
        if is_skip_slot(entry):
            ordered.append(None)
            continue

        requested_name, options = extract_custom_entry_name_and_options(entry)
        if not requested_name:
            if keep_missing_slots:
                ordered.append(None)
            continue

        matched = find_named_item(
            items,
            requested_name,
            used_item_ids=used_item_ids,
            occurrence=resolve_entry_occurrence(options),
            get_name=get_name,
            is_valid_item=is_valid_item,
        )
        if matched is None:
            missing_requested_names.append(format_requested_entry(requested_name, options))
            if keep_missing_slots:
                ordered.append(None)
            continue

        ordered.append(matched)
        used_item_ids.add(id(matched))

    if append_rest:
        for item in items:
            if not is_valid_item(item):
                continue
            if id(item) in used_item_ids:
                continue
            ordered.append(item)
            used_item_ids.add(id(item))

    return tuple(ordered), tuple(missing_requested_names)


def find_named_item(
    items,
    requested_name,
    used_item_ids=None,
    occurrence=None,
    get_name=None,
    is_valid_item=None,
):
    if not requested_name:
        return None
    used_item_ids = used_item_ids or set()
    get_name = get_name or _default_get_name
    is_valid_item = is_valid_item or _default_is_valid_item
    matched_candidates = _matched_candidates(items, requested_name, get_name, is_valid_item)
    if not matched_candidates:
        return None

    if occurrence is not None:
        candidate_index = occurrence - 1
        if candidate_index < 0 or candidate_index >= len(matched_candidates):
            return None
        candidate = matched_candidates[candidate_index]
        return None if id(candidate) in used_item_ids else candidate

    for candidate in matched_candidates:
        if id(candidate) not in used_item_ids:
            return candidate
    return None


def _matched_candidates(items, requested_name, get_name, is_valid_item):
    normalized_requested = normalize_name(requested_name)
    compact_requested = compact_name(requested_name)
    matches = ([], [], [], [])

    for item in items:
        if not is_valid_item(item):
            continue
        item_name = get_name(item)
        if item_name == requested_name:
            matches[0].append(item)
            continue
        normalized_item_name = normalize_name(item_name)
        if normalized_item_name == normalized_requested:
            matches[1].append(item)
            continue
        compact_item_name = compact_name(item_name)
        if compact_item_name == compact_requested:
            matches[2].append(item)
            continue
        if compact_requested and (
            compact_requested in compact_item_name or compact_item_name in compact_requested
        ):
            matches[3].append(item)

    for tier in matches:
        if tier:
            return tier
    return ()


def _mode_switch_options(options):
    if not isinstance(options, dict):
        return None
    if "mode_count" not in options:
        return None
    return options


def _default_get_name(item):
    if item is None:
        return ""
    return getattr(item, "name", "") or ""


def _default_is_valid_item(item):
    return item is not None and bool(_default_get_name(item))
