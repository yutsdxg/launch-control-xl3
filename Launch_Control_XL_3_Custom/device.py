from ableton.v3.control_surface.components import DeviceBankNavigationComponent as DeviceBankNavigationComponentBase
from ableton.v3.control_surface.components import DeviceComponent as DeviceComponentBase
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER, CUSTOM_PARAMETER_APPEND_REST
import re
import logging

DEVICE_ON_PARAMETER_NAME = "Device On"

DEVICE_BANK_SIZE = 21
DEVICE_QUANTIZED_PARAMETER_SENSITIVITY = 0.5
BANK_NAME_JOIN_SEPARATOR = "\n"
BANK_NAME_FALLBACK = "-"
CUSTOM_BANK_NAME_PREFIX = "Custom"
CUSTOM_DEVICE_ALIASES = {
    # Ableton internal class names
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


def _is_skip_slot(value):
    return value is None or str(value).strip().upper() == "SKIP"


def _make_device_order_index(raw_mapping):
    result = {}
    for key, order in raw_mapping.items():
        normalized = _normalize_device_key(key)
        if normalized:
            result[normalized] = tuple(order)
            alias = CUSTOM_DEVICE_ALIASES.get(normalized)
            if alias:
                result[alias] = tuple(order)
    return result


CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = _make_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)
LOGGER = logging.getLogger(__name__)


class _CustomParameterBankingInfo(object):
    def __init__(self, delegate, bank_size):
        self._delegate = delegate
        self._bank_size = bank_size

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def device_bank_count(self, device, *a, **k):
        custom_flat = self._build_custom_flat_parameters(device)
        if custom_flat is None:
            return self._delegate.device_bank_count(device, *a, **k)
        total = len(custom_flat)
        if total <= 0:
            return 1
        return max(1, (total + self._bank_size - 1) // self._bank_size)

    def device_bank_names(self, device, *a, **k):
        custom_count = self.device_bank_count(device, *a, **k)
        custom_flat = self._build_custom_flat_parameters(device)
        if custom_flat is None:
            return self._delegate.device_bank_names(device, *a, **k)
        try:
            base_names = list(self._delegate.device_bank_names(device, *a, **k))
        except Exception:
            base_names = []
        names = []
        for i in range(custom_count):
            if i < len(base_names):
                names.append("{} {}\n{}".format(CUSTOM_BANK_NAME_PREFIX, i + 1, base_names[i]))
            else:
                names.append("{} {}".format(CUSTOM_BANK_NAME_PREFIX, i + 1))
        return tuple(names)

    def device_bank_parameters(self, device, bank_index, *a, **k):
        custom_flat = self._build_custom_flat_parameters(device)
        if custom_flat is None:
            return self._delegate.device_bank_parameters(device, bank_index, *a, **k)
        start = bank_index * self._bank_size
        end = start + self._bank_size
        bank = list(custom_flat[start:end])
        if len(bank) < self._bank_size:
            bank.extend([None] * (self._bank_size - len(bank)))
        return tuple(bank)

    def _build_custom_flat_parameters(self, device):
        custom_order = self._resolve_custom_order(device)
        if custom_order is None:
            return None
        parameters = tuple(getattr(device, "parameters", ()))
        if not parameters:
            return []
        parameter_by_name = self._build_parameter_index(parameters)
        custom_flat = []
        used_parameter_ids = set()
        for parameter_name in custom_order:
            if _is_skip_slot(parameter_name):
                custom_flat.append(None)
                continue
            parameter = self._find_parameter(parameter_by_name, parameter_name)
            custom_flat.append(parameter)
            if parameter is not None:
                used_parameter_ids.add(id(parameter))
        if CUSTOM_PARAMETER_APPEND_REST:
            for parameter in self._get_base_flat_parameters(device):
                if parameter is None:
                    continue
                if id(parameter) in used_parameter_ids:
                    continue
                custom_flat.append(parameter)
                used_parameter_ids.add(id(parameter))
        return custom_flat

    def _resolve_custom_order(self, device):
        name_keys = (
            getattr(device, "name", ""),
            getattr(device, "class_name", ""),
            getattr(device, "class_display_name", ""),
        )
        normalized_keys = []
        for key in name_keys:
            normalized = _normalize_device_key(key)
            if normalized:
                normalized_keys.append(normalized)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
        for device_key in normalized_keys:
            for custom_key, custom_order in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX.items():
                if custom_key in device_key or device_key in custom_key:
                    return custom_order
        return None

    def _build_parameter_index(self, parameters):
        index = {}
        for parameter in parameters:
            if parameter is None:
                continue
            name = getattr(parameter, "name", "")
            if not name or name == DEVICE_ON_PARAMETER_NAME:
                continue
            normalized = _normalize_name(name)
            compact = _compact_name(name)
            if not normalized:
                continue
            if name not in index:
                index[name] = parameter
            if normalized not in index:
                index[normalized] = parameter
            if compact and compact not in index:
                index[compact] = parameter
        return index

    def _find_parameter(self, parameter_by_name, requested_name):
        if requested_name is None:
            return None
        direct = parameter_by_name.get(requested_name)
        if direct is not None:
            return direct
        normalized = _normalize_name(requested_name)
        direct = parameter_by_name.get(normalized)
        if direct is not None:
            return direct
        compact = _compact_name(requested_name)
        direct = parameter_by_name.get(compact)
        if direct is not None:
            return direct
        if compact:
            for key, parameter in parameter_by_name.items():
                if not isinstance(key, str):
                    continue
                if compact in _compact_name(key) or _compact_name(key) in compact:
                    return parameter
        return None

    def _get_base_flat_parameters(self, device):
        base_flat = []
        try:
            base_count = self._delegate.device_bank_count(device)
        except Exception:
            base_count = 0
        if base_count > 0:
            for bank_index in range(base_count):
                try:
                    bank_parameters = self._delegate.device_bank_parameters(device, bank_index)
                except Exception:
                    continue
                for parameter in bank_parameters:
                    if parameter is None:
                        continue
                    name = getattr(parameter, "name", "")
                    if name == DEVICE_ON_PARAMETER_NAME:
                        continue
                    base_flat.append(parameter)
        if base_flat:
            return tuple(base_flat)
        return tuple(
            parameter
            for parameter in getattr(device, "parameters", ())
            if parameter is not None and getattr(parameter, "name", "") != DEVICE_ON_PARAMETER_NAME
        )


class DeviceBankNavigationComponent(DeviceBankNavigationComponentBase):
    
    def _notify_bank_name(self):
        bank_names = self._banking_info.device_bank_names(
            self._bank_provider.device,
            bank_name_join_str=BANK_NAME_JOIN_SEPARATOR,
        )[self._bank_provider.index].split(BANK_NAME_JOIN_SEPARATOR)
        self.notify(
            self.notifications.Device.bank,
            "{}\n{}\n{}".format(
                self._bank_provider.device.name,
                bank_names[0],
                bank_names[1] if len(bank_names) > 1 else BANK_NAME_FALLBACK,
            ),
        )



class DeviceComponent(DeviceComponentBase):
    def __init__(self, *a, **k):
        super().__init__(
            *a,
            bank_size=DEVICE_BANK_SIZE,
            bank_navigation_component_type=DeviceBankNavigationComponent,
            quantized_parameter_sensitivity=DEVICE_QUANTIZED_PARAMETER_SENSITIVITY,
            **k
        )
        self._install_custom_banking_info()

    def _install_custom_banking_info(self):
        wrapped = _CustomParameterBankingInfo(self._banking_info, DEVICE_BANK_SIZE)
        self._banking_info = wrapped

        bank_provider = getattr(self, "_bank_provider", None)
        if bank_provider is not None and hasattr(bank_provider, "_banking_info"):
            bank_provider._banking_info = wrapped

        bank_navigation = getattr(self, "_bank_navigation", None)
        if bank_navigation is not None and hasattr(bank_navigation, "_banking_info"):
            bank_navigation._banking_info = wrapped

    def _resolve_custom_order(self, device):
        if device is None:
            return None
        name_keys = (
            getattr(device, "name", ""),
            getattr(device, "class_name", ""),
            getattr(device, "class_display_name", ""),
        )
        normalized_keys = []
        for key in name_keys:
            normalized = _normalize_device_key(key)
            if normalized:
                normalized_keys.append(normalized)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
        for device_key in normalized_keys:
            for custom_key, custom_order in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX.items():
                if custom_key in device_key or device_key in custom_key:
                    return custom_order
        return None

    def _get_current_device_for_custom_order(self):
        candidate = getattr(self, "device", None)
        if candidate is not None:
            return candidate
        bank_provider = getattr(self, "_bank_provider", None)
        if bank_provider is not None:
            return getattr(bank_provider, "device", None)
        return None

    def _extract_parameter_from_info(self, info):
        if info is None:
            return None
        return getattr(info, "parameter", info)

    def _get_parameter_name(self, parameter):
        if parameter is None:
            return ""
        return getattr(parameter, "name", "") or ""

    def _find_info_for_requested_name(self, infos, requested_name, used_info_ids):
        compact_requested = _compact_name(requested_name)
        normalized_requested = _normalize_name(requested_name)
        for info in infos:
            if info is None:
                continue
            if id(info) in used_info_ids:
                continue
            parameter = self._extract_parameter_from_info(info)
            if parameter is None:
                continue
            parameter_name = self._get_parameter_name(parameter)
            if not parameter_name or parameter_name == DEVICE_ON_PARAMETER_NAME:
                continue
            if parameter_name == requested_name:
                return info
            if _normalize_name(parameter_name) == normalized_requested:
                return info
            compact_parameter_name = _compact_name(parameter_name)
            if compact_parameter_name == compact_requested:
                return info
            if compact_requested and (
                compact_requested in compact_parameter_name
                or compact_parameter_name in compact_requested
            ):
                return info
        return None

    def _apply_custom_order_to_provided_infos(self, infos, custom_order):
        if not infos:
            return infos
        result = []
        used_info_ids = set()
        missing_requested_names = []
        for requested_name in custom_order:
            if _is_skip_slot(requested_name):
                result.append(None)
                continue
            matched = self._find_info_for_requested_name(infos, requested_name, used_info_ids)
            if matched is None:
                # Do not consume a slot when the name does not match.
                # Empty slots should be created only by explicit SKIP/None.
                missing_requested_names.append(requested_name)
                continue
            result.append(matched)
            used_info_ids.add(id(matched))
        if CUSTOM_PARAMETER_APPEND_REST:
            for info in infos:
                if info is None:
                    continue
                if id(info) in used_info_ids:
                    continue
                parameter = self._extract_parameter_from_info(info)
                if parameter is None:
                    continue
                parameter_name = self._get_parameter_name(parameter)
                if parameter_name == DEVICE_ON_PARAMETER_NAME:
                    continue
                result.append(info)
                used_info_ids.add(id(info))
        target_size = len(infos)
        if len(result) < target_size:
            result.extend([None] * (target_size - len(result)))
        elif len(result) > target_size:
            result = result[:target_size]
        try:
            if missing_requested_names:
                LOGGER.info(
                    "LCXL3 custom order missing names: %s",
                    ", ".join(str(name) for name in missing_requested_names),
                )
        except Exception:
            pass
        return result

    def _get_provided_parameters(self):
        device = self._get_current_device_for_custom_order()
        custom_order = self._resolve_custom_order(device)
        if not custom_order:
            return super()._get_provided_parameters()
        bank_provider = getattr(self, "_bank_provider", None)
        bank_index = getattr(bank_provider, "index", 0) if bank_provider is not None else 0
        banking_info = getattr(self, "_banking_info", None)
        if banking_info is not None and hasattr(banking_info, "device_bank_parameters"):
            bank_parameters = banking_info.device_bank_parameters(device, bank_index)
            reordered = [
                self._create_parameter_info(parameter, self._get_parameter_name(parameter))
                if parameter is not None
                else None
                for parameter in bank_parameters
            ]
        else:
            # Compatibility fallback for BankingInfo variants without device_bank_parameters.
            infos = super()._get_provided_parameters()
            reordered = self._apply_custom_order_to_provided_infos(list(infos), custom_order)
        try:
            LOGGER.info(
                "LCXL3 custom order applied: device=%s class=%s entries=%s bank=%s",
                getattr(device, "name", None),
                getattr(device, "class_name", None),
                len(custom_order),
                bank_index,
            )
        except Exception:
            pass
        return reordered
