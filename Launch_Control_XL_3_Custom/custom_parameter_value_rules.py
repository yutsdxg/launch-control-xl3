# -*- coding: utf-8 -*-
"""
Parameter value movement rules that do not affect device banking order.
"""

# Global rules match the Live parameter name regardless of device or encoder slot.
CUSTOM_GLOBAL_PARAMETER_VALUE_RULES = {
    "Analog 1 O1 Coarse": {
        "step_size": 12,
        "center": 0,
        "display_min": -36,
        "display_max": 36,
        "input_mode": "cc_bins",
        "input_resolution": 128,
    },
    "Analog 1 O2 Coarse": {
        "step_size": 12,
        "center": 0,
        "display_min": -36,
        "display_max": 36,
        "input_mode": "cc_bins",
        "input_resolution": 128,
    },
}

# Reserved for future cases where a short or duplicated parameter name should
# only be handled for a specific device.
CUSTOM_DEVICE_PARAMETER_VALUE_RULES = {}
