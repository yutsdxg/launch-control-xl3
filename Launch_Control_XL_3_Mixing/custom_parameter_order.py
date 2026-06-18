"""
Device-specific parameter ordering for fixed assignments.

Add device names to CUSTOM_DEVICE_PARAMETER_ORDER when you want encoder/fader
parameter numbers to use a custom order instead of Live's raw parameter order.

Device keys can be display names, class names, or class display names. Trailing
numbers are ignored by the resolver. Use None or "SKIP" for an empty slot.
"""

# False: only assign entries listed below. Unspecified slots stay empty.
# True: append remaining Live parameters after the listed entries.
CUSTOM_PARAMETER_APPEND_REST = False

CUSTOM_DEVICE_PARAMETER_ORDER = {
    "Delay": (
        "Dry/Wet",
        "L 16th",
        "Feedback",
    ),
}
"""
    "Some Device": (
        "Attack",
        {"Attack": {"occurrence": 2}},
        "Release",
    ),
"""
