"""Settings for the inactivity lock. Tune LED levels on the hardware."""

INACTIVITY_LOCK_SECONDS = 180.0
LOCKED_LED_FACTOR = 0.2
LOCKED_MODE_RGB = (8, 8, 8)


def locked_led_rgb(rgb):
    """Dim the current state without lighting unassigned controls."""
    return tuple(max(0, min(127, int(round(channel * LOCKED_LED_FACTOR)))) for channel in rgb)
