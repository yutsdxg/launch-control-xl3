from time import monotonic

from ableton.v3.base import task
from ableton.v3.control_surface import Component

from .colors import Theme, mode_button_rgb
from .display import cancel_display, send_display, send_locked_display
from .led import LedSender
from .safety import INACTIVITY_LOCK_SECONDS, LOCKED_MODE_RGB

MODE_MIXING = "mixing"
MODE_INSTRUMENT = "instrument"


class ModeManagerComponent(Component):
    def __init__(self, *a, clock=None, idle_timeout=INACTIVITY_LOCK_SECONDS, **k):
        super().__init__(*a, **k)
        self._mixing_button = None
        self._instrument_button = None
        self._mixing_button_slot = None
        self._instrument_button_slot = None
        self._selected_mode = MODE_MIXING
        self._on_mode_changed = None
        self._led_sender = LedSender()
        self._clock = clock or monotonic
        self._idle_timeout = float(idle_timeout)
        self._last_activity = self._clock()
        self._locked = False
        self._on_lock_changed = None
        self._static_display = None
        self._temp_display = None
        self._tasks.add(task.loop(task.sequence(task.run(self.check_idle), task.delay(0.1))))

    @property
    def selected_mode(self):
        return self._selected_mode

    @property
    def locked(self):
        return self._locked

    def set_on_lock_changed(self, callback):
        self._on_lock_changed = callback
        callback(self._locked)

    def record_activity(self):
        if not self._locked:
            self._last_activity = self._clock()

    def check_idle(self):
        if not self._locked and self._clock() - self._last_activity >= self._idle_timeout:
            self._set_locked(True)

    def _set_locked(self, locked):
        if self._locked == locked:
            return
        self._locked = locked
        if self._on_lock_changed is not None:
            self._on_lock_changed(locked)
        self.refresh_led_feedback()
        self.refresh_display_feedback(show_immediately=True)

    def set_static_display(self, command):
        self._static_display = command
        self.refresh_display_feedback()

    def set_temp_display(self, command):
        self._temp_display = command

    def refresh_display_feedback(self, show_immediately=False):
        for command in (self._static_display, self._temp_display):
            if command is not None:
                command.clear_send_cache()
        send_display(
            self._static_display,
            ("LOCKED" if self._locked else self._selected_mode.upper(), "", ""),
            show_immediately=show_immediately,
        )
        if self._locked:
            # Replace any notification already covering the stationary screen.
            send_locked_display(self._temp_display, trigger=show_immediately)
        else:
            cancel_display(self._temp_display)

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
            was_locked = self._locked
            self._set_selected_mode(mode)
            self._last_activity = self._clock()
            self._set_locked(False)
            if not was_locked:
                self.refresh_display_feedback(show_immediately=True)

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
            rgb = LOCKED_MODE_RGB if self._locked else mode_button_rgb(active, Theme.MODE_MIXING)
            self._led_sender.send_rgb(
                self._mixing_button,
                rgb,
                force=force,
            )
        if self._instrument_button is not None:
            active = self._selected_mode == MODE_INSTRUMENT
            rgb = LOCKED_MODE_RGB if self._locked else mode_button_rgb(active, Theme.MODE_INSTRUMENT)
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
