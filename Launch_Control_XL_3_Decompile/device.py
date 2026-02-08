from ableton.v3.control_surface.components import DeviceBankNavigationComponent as DeviceBankNavigationComponentBase
from ableton.v3.control_surface.components import DeviceComponent as DeviceComponentBase

class DeviceBankNavigationComponent(DeviceBankNavigationComponentBase):
    
    def _notify_bank_name(self):
        bank_names = self._banking_info.device_bank_names(self._bank_provider.device, bank_name_join_str = '\n')[self._bank_provider.index].split('\n')
        self.notify(self.notifications.Device.bank, '{}\n{}\n{}'.format(self._bank_provider.device.name, bank_names[0], bank_names[1] if len(bank_names) > 1 else '-'))



class DeviceComponent(DeviceComponentBase):
    def __init__(self, *a, **k):
        super().__init__(
            *a,
            bank_size=16,
            bank_navigation_component_type=DeviceBankNavigationComponent,
            quantized_parameter_sensitivity=0.5,
            **k
        )
