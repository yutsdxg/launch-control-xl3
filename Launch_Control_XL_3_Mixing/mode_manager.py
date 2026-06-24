from ableton.v3.control_surface import Component

from .colors import mode_button_rgb
from .led import LedSender

MODE_MIXING = "mixing"
MODE_INSTRUMENT = "instrument"


class ModeManagerComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._mixing_button = None
        self._instrument_button = None
        self._mixing_button_slot = None
        self._instrument_button_slot = None
        self._selected_mode = MODE_MIXING
        self._on_mode_changed = None
        self._led_sender = LedSender()

    @property
    def selected_mode(self):
        return self._selected_mode

    def set_midi_sender(self, midi_sender):
        self._led_sender.set_midi_sender(midi_sender)
        self.refresh_led_feedback()

    def set_on_mode_changed(self, callback):
        self._on_mode_changed = callback
        self._notify_mode_changed()

    def set_mixing_button(self, button):
        self._mixing_button, self._mixing_button_slot = self._replace_button(
            self._mixing_button,
            self._mixing_button_slot,
            button,
            lambda value: self._on_mode_button_value(MODE_MIXING, value),
        )
        self.refresh_led_feedback()

    def set_instrument_button(self, button):
        self._instrument_button, self._instrument_button_slot = self._replace_button(
            self._instrument_button,
            self._instrument_button_slot,
            button,
            lambda value: self._on_mode_button_value(MODE_INSTRUMENT, value),
        )
        self.refresh_led_feedback()

    def refresh_led_feedback(self):
        self._update_mode_leds(force=True)

    def _replace_button(self, previous_button, previous_slot, button, listener):
        if previous_slot is not None:
            previous_slot.disconnect()
        if previous_button is not None:
            self._led_sender.forget(previous_button)
        slot = self.register_slot(button, listener, "value") if button is not None else None
        return button, slot

    def _on_mode_button_value(self, mode, value):
        if value > 0:
            self._set_selected_mode(mode)

    def _set_selected_mode(self, mode):
        if mode == self._selected_mode:
            self._update_mode_leds(force=True)
            return
        self._selected_mode = mode
        self._update_mode_leds(force=True)
        self._notify_mode_changed()

    def _notify_mode_changed(self):
        if self._on_mode_changed is None:
            return
        try:
            self._on_mode_changed(self._selected_mode)
        except RuntimeError:
            pass

    def _update_mode_leds(self, force=False):
        if self._mixing_button is not None:
            active = self._selected_mode == MODE_MIXING
            rgb = mode_button_rgb(active)
            self._led_sender.send_rgb(
                self._mixing_button,
                rgb,
                force=force,
            )
        if self._instrument_button is not None:
            active = self._selected_mode == MODE_INSTRUMENT
            rgb = mode_button_rgb(active)
            self._led_sender.send_rgb(
                self._instrument_button,
                rgb,
                force=force,
            )

    def disconnect(self):
        for slot in (self._mixing_button_slot, self._instrument_button_slot):
            if slot is not None:
                slot.disconnect()
        try:
            super().disconnect()
        except AttributeError:
            pass
