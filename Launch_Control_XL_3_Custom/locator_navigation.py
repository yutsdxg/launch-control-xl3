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
        if button is None:
            return None
        return self.register_slot(button, listener, "value")

    def _on_prev_locator_button_value(self, value):
        if value > 0:
            self._jump_to_locator("prev")

    def _on_next_locator_button_value(self, value):
        if value > 0:
            self._jump_to_locator("next")

    def _jump_to_locator(self, direction):
        can_jump_name = "can_jump_to_{}_cue".format(direction)
        jump_name = "jump_to_{}_cue".format(direction)
        try:
            if not getattr(self.song, can_jump_name):
                return
            getattr(self.song, jump_name)()
        except (AttributeError, RuntimeError):
            pass
