from ableton.v3.control_surface import Component


class LocatorNavigationComponent(Component):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._prev_locator_button_slot = None
        self._next_locator_button_slot = None

    def set_prev_locator_button(self, button):
        self._prev_locator_button_slot = self._replace_button_slot(
            self._prev_locator_button_slot,
            button,
            self._on_prev_locator_button_value,
        )

    def set_next_locator_button(self, button):
        self._next_locator_button_slot = self._replace_button_slot(
            self._next_locator_button_slot,
            button,
            self._on_next_locator_button_value,
        )

    def _replace_button_slot(self, slot, button, listener):
        if slot is not None:
            slot.disconnect()
        return self.register_slot(button, listener, "value") if button is not None else None

    def _on_prev_locator_button_value(self, value):
        if value > 0:
            self._jump_to_locator("prev")

    def _on_next_locator_button_value(self, value):
        if value > 0:
            self._jump_to_locator("next")

    def _jump_to_locator(self, direction):
        try:
            if getattr(self.song, "can_jump_to_{}_cue".format(direction)):
                getattr(self.song, "jump_to_{}_cue".format(direction))()
        except (AttributeError, RuntimeError):
            pass
