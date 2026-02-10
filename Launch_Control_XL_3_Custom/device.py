from ableton.v3.control_surface.components import DeviceBankNavigationComponent as DeviceBankNavigationComponentBase
from ableton.v3.control_surface.components import DeviceComponent as DeviceComponentBase

DEVICE_BANK_SIZE = 21
DEVICE_QUANTIZED_PARAMETER_SENSITIVITY = 0.5
BANK_NAME_JOIN_SEPARATOR = "\n"
BANK_NAME_FALLBACK = "-"


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
