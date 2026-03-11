from ableton.v3.control_surface.components import DeviceBankNavigationComponent as DeviceBankNavigationComponentBase
from ableton.v3.control_surface.components import DeviceComponent as DeviceComponentBase
from .custom_parameter_order import CUSTOM_DEVICE_PARAMETER_ORDER, CUSTOM_PARAMETER_APPEND_REST
from .custom_parameter_utils import (
    DEVICE_ON_PARAMETER_NAME,
    build_device_order_index,
    normalize_device_key,
    order_named_items,
)
import logging

DEVICE_BANK_SIZE = 21
DEVICE_QUANTIZED_PARAMETER_SENSITIVITY = 0.5
BANK_NAME_JOIN_SEPARATOR = "\n"
BANK_NAME_FALLBACK = "-"
CUSTOM_BANK_NAME_PREFIX = "Custom"


CUSTOM_DEVICE_PARAMETER_ORDER_INDEX = build_device_order_index(CUSTOM_DEVICE_PARAMETER_ORDER)
LOGGER = logging.getLogger(__name__)


class _CustomParameterBankingInfo(object):
    def __init__(self, delegate, bank_size):
        self._delegate = delegate
        self._bank_size = bank_size

    def __getattr__(self, name):
        return getattr(self._delegate, name)

    def device_bank_count(self, device, *a, **k):
        flat_parameters = self._preferred_flat_parameters(device)
        if flat_parameters is None:
            return self._delegate.device_bank_count(device, *a, **k)
        total = len(flat_parameters)
        if total <= 0:
            return 1
        return max(1, (total + self._bank_size - 1) // self._bank_size)

    def device_bank_names(self, device, *a, **k):
        custom_count = self.device_bank_count(device, *a, **k)
        flat_parameters = self._preferred_flat_parameters(device)
        if flat_parameters is None:
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
        flat_parameters = self._preferred_flat_parameters(device)
        if flat_parameters is None:
            return self._delegate.device_bank_parameters(device, bank_index, *a, **k)
        start = bank_index * self._bank_size
        end = start + self._bank_size
        bank = list(flat_parameters[start:end])
        if len(bank) < self._bank_size:
            bank.extend([None] * (self._bank_size - len(bank)))
        return tuple(bank)

    def device_bank_definition(self, device, *a, **k):
        # Avoid DescribedDeviceParameterBank path when custom bank_count is active.
        # This keeps bank_count and bank_definition aligned and prevents IndexError.
        if self._preferred_flat_parameters(device) is not None:
            return None
        delegate = self._delegate
        if hasattr(delegate, "device_bank_definition"):
            return delegate.device_bank_definition(device, *a, **k)
        return None

    def uses_duplicate_name_banking(self, device):
        return self._build_duplicate_name_flat_parameters(device) is not None

    def _preferred_flat_parameters(self, device):
        custom_flat = self._build_custom_flat_parameters(device)
        if custom_flat is not None:
            return custom_flat
        return self._build_duplicate_name_flat_parameters(device)

    def _build_custom_flat_parameters(self, device):
        custom_order = self._resolve_custom_order(device)
        if custom_order is None:
            return None
        parameters = tuple(getattr(device, "parameters", ()))
        if not parameters:
            return []
        custom_flat, missing_requested_names = order_named_items(
            parameters,
            custom_order,
            append_rest=CUSTOM_PARAMETER_APPEND_REST,
            get_name=self._parameter_name,
            is_valid_item=self._is_assignable_parameter,
            keep_missing_slots=True,
        )
        if CUSTOM_PARAMETER_APPEND_REST:
            custom_flat = tuple(custom_flat)
        try:
            if missing_requested_names:
                LOGGER.info(
                    "LCXL3 custom order missing names: %s",
                    ", ".join(str(name) for name in missing_requested_names),
                )
        except Exception:
            pass
        return custom_flat

    def _resolve_custom_order(self, device):
        name_keys = (
            getattr(device, "name", ""),
            getattr(device, "class_name", ""),
            getattr(device, "class_display_name", ""),
        )
        for key in name_keys:
            normalized = normalize_device_key(key)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
        return None

    def _parameter_name(self, parameter):
        return getattr(parameter, "name", "") or ""

    def _is_assignable_parameter(self, parameter):
        return parameter is not None and self._parameter_name(parameter) not in ("", DEVICE_ON_PARAMETER_NAME)

    def _build_duplicate_name_flat_parameters(self, device):
        if self._resolve_custom_order(device) is not None:
            return None
        parameters = self._all_assignable_parameters(device)
        if not parameters or not self._has_duplicate_parameter_names(parameters):
            return None
        return parameters

    def _all_assignable_parameters(self, device):
        try:
            parameters = tuple(getattr(device, "parameters", ()))
        except RuntimeError:
            return ()
        return tuple(parameter for parameter in parameters if self._is_assignable_parameter(parameter))

    def _has_duplicate_parameter_names(self, parameters):
        seen_names = set()
        for parameter in parameters:
            name = self._parameter_name(parameter)
            if name in seen_names:
                return True
            seen_names.add(name)
        return False

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
        for key in name_keys:
            normalized = normalize_device_key(key)
            if normalized and normalized in CUSTOM_DEVICE_PARAMETER_ORDER_INDEX:
                return CUSTOM_DEVICE_PARAMETER_ORDER_INDEX[normalized]
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

    def _get_parameter_name_for_info(self, info):
        return self._get_parameter_name(self._extract_parameter_from_info(info))

    def _is_valid_parameter_info(self, info):
        return self._get_parameter_name_for_info(info) not in ("", DEVICE_ON_PARAMETER_NAME)

    def _parameter_info_base_name(self, info):
        parameter_name = self._get_parameter_name_for_info(info)
        if parameter_name:
            return parameter_name
        if info is None:
            return ""
        return getattr(info, "name", "") or ""

    def _uniquify_parameter_infos(self, infos):
        if not infos:
            return infos
        name_counts = {}
        for info in infos:
            base_name = self._parameter_info_base_name(info)
            if not base_name:
                continue
            name_counts[base_name] = name_counts.get(base_name, 0) + 1
        if not any(count > 1 for count in name_counts.values()):
            return infos

        result = []
        seen_names = {}
        for info in infos:
            if info is None:
                result.append(None)
                continue
            parameter = self._extract_parameter_from_info(info)
            base_name = self._parameter_info_base_name(info)
            if parameter is None or not base_name:
                result.append(info)
                continue

            occurrence = seen_names.get(base_name, 0) + 1
            seen_names[base_name] = occurrence
            unique_name = base_name if occurrence == 1 else "{} [{}]".format(base_name, occurrence)
            if unique_name == getattr(info, "name", None):
                result.append(info)
                continue
            result.append(self._create_parameter_info(parameter, unique_name))
        return tuple(result)

    def _apply_custom_order_to_provided_infos(self, infos, custom_order):
        if not infos:
            return infos
        result, missing_requested_names = order_named_items(
            infos,
            custom_order,
            append_rest=CUSTOM_PARAMETER_APPEND_REST,
            get_name=self._get_parameter_name_for_info,
            is_valid_item=self._is_valid_parameter_info,
            keep_missing_slots=False,
        )
        result = list(result)
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
        bank_provider = getattr(self, "_bank_provider", None)
        bank_index = getattr(bank_provider, "index", 0) if bank_provider is not None else 0
        banking_info = getattr(self, "_banking_info", None)
        use_custom_banking = bool(custom_order)
        if not use_custom_banking and banking_info is not None and hasattr(banking_info, "uses_duplicate_name_banking"):
            use_custom_banking = banking_info.uses_duplicate_name_banking(device)
        if use_custom_banking and banking_info is not None and hasattr(banking_info, "device_bank_parameters"):
            bank_parameters = banking_info.device_bank_parameters(device, bank_index)
            reordered = [
                self._create_parameter_info(parameter, self._get_parameter_name(parameter))
                if parameter is not None
                else None
                for parameter in bank_parameters
            ]
        elif not custom_order:
            return self._uniquify_parameter_infos(super()._get_provided_parameters())
        else:
            # Compatibility fallback for BankingInfo variants without device_bank_parameters.
            infos = super()._get_provided_parameters()
            reordered = self._apply_custom_order_to_provided_infos(list(infos), custom_order)
        reordered = self._uniquify_parameter_infos(reordered)
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
