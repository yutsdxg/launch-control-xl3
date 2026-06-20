import time

from ableton.v3.base import task
from ableton.v3.control_surface import Component
from ableton.v3.live import action, liveobj_valid

from .colors import Theme, active_track_rgb, dim_track_rgb, track_rgb
from .led import LedSender
from .track_resolver import selected_track, track_button_targets

LED_UPDATE_INTERVAL = 0.1
SELECTED_BLINK_INTERVAL = 0.5
BUTTON_MODE_SELECT = "select"
BUTTON_MODE_SOLO = "solo"
BUTTON_MODE_MUTE = "mute"
SELECTED_TRACK_REPRESS_ACTION = BUTTON_MODE_MUTE


class TrackButtonsComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._track_buttons = [None] * 16
        self._track_button_slots = [None] * 16
        self._shift_button = None
        self._solo_modifier_button = None
        self._mute_modifier_button = None
        self._shift_slot = None
        self._solo_modifier_slot = None
        self._mute_modifier_slot = None
        self._shift_pressed = False
        self._button_mode = BUTTON_MODE_SELECT
        self._led_sender = LedSender()
        self._led_update_task = self._tasks.add(
            task.loop(
                task.sequence(
                    task.run(self._update_led_feedback),
                    task.delay(LED_UPDATE_INTERVAL),
                )
            )
        )

    def set_midi_sender(self, midi_sender):
        self._led_sender.set_midi_sender(midi_sender)
        self.refresh_led_feedback()

    def set_shift_button(self, button):
        self._shift_button, self._shift_slot = self._replace_modifier(
            self._shift_button,
            self._shift_slot,
            button,
            self._on_shift_value,
        )
        self.refresh_led_feedback()

    def set_solo_modifier_button(self, button):
        self._solo_modifier_button, self._solo_modifier_slot = self._replace_modifier(
            self._solo_modifier_button,
            self._solo_modifier_slot,
            button,
            self._on_solo_modifier_value,
        )
        self.refresh_led_feedback()

    def set_mute_modifier_button(self, button):
        self._mute_modifier_button, self._mute_modifier_slot = self._replace_modifier(
            self._mute_modifier_button,
            self._mute_modifier_slot,
            button,
            self._on_mute_modifier_value,
        )
        self.refresh_led_feedback()

    def set_track_button_1(self, button):
        self._set_track_button(0, button)

    def set_track_button_2(self, button):
        self._set_track_button(1, button)

    def set_track_button_3(self, button):
        self._set_track_button(2, button)

    def set_track_button_4(self, button):
        self._set_track_button(3, button)

    def set_track_button_5(self, button):
        self._set_track_button(4, button)

    def set_track_button_6(self, button):
        self._set_track_button(5, button)

    def set_track_button_7(self, button):
        self._set_track_button(6, button)

    def set_track_button_8(self, button):
        self._set_track_button(7, button)

    def set_track_button_9(self, button):
        self._set_track_button(8, button)

    def set_track_button_10(self, button):
        self._set_track_button(9, button)

    def set_track_button_11(self, button):
        self._set_track_button(10, button)

    def set_track_button_12(self, button):
        self._set_track_button(11, button)

    def set_track_button_13(self, button):
        self._set_track_button(12, button)

    def set_track_button_14(self, button):
        self._set_track_button(13, button)

    def set_track_button_15(self, button):
        self._set_track_button(14, button)

    def set_track_button_16(self, button):
        self._set_track_button(15, button)

    def refresh_led_feedback(self):
        self._update_modifier_leds(force=True)
        self._update_track_button_leds(force=True)

    def _replace_modifier(self, previous_button, previous_slot, button, listener):
        if previous_slot is not None:
            previous_slot.disconnect()
        if previous_button is not None:
            self._led_sender.forget(previous_button)
        slot = self.register_slot(button, listener, "value") if button is not None else None
        return button, slot

    def _set_track_button(self, index, button):
        slot = self._track_button_slots[index]
        if slot is not None:
            slot.disconnect()
        previous = self._track_buttons[index]
        if previous is not None:
            self._led_sender.forget(previous)
        self._track_buttons[index] = button
        self._track_button_slots[index] = (
            self.register_slot(
                button,
                lambda value, *a, _index=index: self._on_track_button_value(_index, value),
                "value",
            )
            if button is not None
            else None
        )
        self._update_track_button_led(index, force=True)

    def _on_shift_value(self, value):
        self._shift_pressed = value > 0
        self.refresh_led_feedback()

    def _on_solo_modifier_value(self, value):
        if value > 0:
            self._toggle_button_mode(BUTTON_MODE_SOLO)

    def _on_mute_modifier_value(self, value):
        if value > 0:
            self._toggle_button_mode(BUTTON_MODE_MUTE)

    def _toggle_button_mode(self, mode):
        self._button_mode = BUTTON_MODE_SELECT if self._button_mode == mode else mode
        self._update_modifier_leds(force=True)

    def _on_track_button_value(self, index, value):
        if value <= 0:
            return
        target = self._track_target(index)
        if not liveobj_valid(target):
            return
        if self._button_mode == BUTTON_MODE_SOLO:
            self._toggle_track_bool(target, "solo")
        elif self._button_mode == BUTTON_MODE_MUTE:
            self._toggle_track_bool(target, "mute")
        elif self._is_selected(target):
            self._apply_selected_track_repress_action(target)
        else:
            self._select_track(target)
        self._update_track_button_leds(force=True)

    def _apply_selected_track_repress_action(self, track):
        if SELECTED_TRACK_REPRESS_ACTION == BUTTON_MODE_SOLO:
            self._toggle_track_bool(track, "solo")
        else:
            self._toggle_track_bool(track, "mute")

    def _toggle_track_bool(self, track, attribute):
        try:
            setattr(track, attribute, not bool(getattr(track, attribute)))
        except (AttributeError, RuntimeError):
            pass

    def _track_bool(self, track, attribute):
        try:
            return bool(getattr(track, attribute))
        except (AttributeError, RuntimeError):
            return False

    def _select_track(self, track):
        try:
            action.select(track)
        except RuntimeError:
            pass
        try:
            self.song.view.selected_track = track
        except (AttributeError, RuntimeError):
            pass

    def _update_led_feedback(self):
        self._update_modifier_leds()
        self._update_track_button_leds()

    def _update_modifier_leds(self, force=False):
        if self._solo_modifier_button is not None:
            rgb = Theme.SOLO_ON if self._button_mode == BUTTON_MODE_SOLO else Theme.SOLO_MODIFIER_IDLE
            self._led_sender.send_rgb(self._solo_modifier_button, rgb, force=force)
        if self._mute_modifier_button is not None:
            rgb = Theme.MUTE_MODIFIER_ON if self._button_mode == BUTTON_MODE_MUTE else Theme.MUTE_MODIFIER_IDLE
            self._led_sender.send_rgb(self._mute_modifier_button, rgb, force=force)

    def _update_track_button_leds(self, force=False):
        for index in range(len(self._track_buttons)):
            self._update_track_button_led(index, force=force)

    def _update_track_button_led(self, index, force=False):
        button = self._track_buttons[index]
        if button is None:
            return
        self._led_sender.send_rgb(button, self._track_rgb(index), force=force)

    def _track_rgb(self, index):
        track = self._track_target(index)
        if not liveobj_valid(track):
            return Theme.OFF
        try:
            if bool(track.solo):
                return Theme.SOLO_ON
        except (AttributeError, RuntimeError):
            pass
        rgb = track_rgb(track)
        try:
            state_rgb = dim_track_rgb(rgb) if bool(track.mute) else active_track_rgb(rgb)
        except (AttributeError, RuntimeError):
            state_rgb = active_track_rgb(rgb)
        if self._is_selected(track):
            return state_rgb if self._selected_blink_is_on() else Theme.OFF
        return state_rgb

    def _track_target(self, index):
        targets = track_button_targets(self.song)
        return targets[index] if 0 <= index < len(targets) else None

    def _is_selected(self, track):
        current = selected_track(self.song)
        try:
            return current == track
        except RuntimeError:
            return False

    def _selected_blink_is_on(self):
        return int(time.monotonic() / SELECTED_BLINK_INTERVAL) % 2 == 0

    def disconnect(self):
        for slot in tuple(self._track_button_slots):
            if slot is not None:
                slot.disconnect()
        for slot in (self._shift_slot, self._solo_modifier_slot, self._mute_modifier_slot):
            if slot is not None:
                slot.disconnect()
        try:
            super().disconnect()
        except AttributeError:
            pass
