from ableton.v3.base import depends, find_if, listenable_property
from ableton.v3.control_surface.components import SessionNavigationComponent as SessionNavigationComponentBase
from ableton.v3.control_surface.controls import ButtonControl
from ableton.v3.control_surface.display import Renderable
from ableton.v3.live import action, liveobj_valid, simple_track_name

class SessionNavigationComponent(Renderable, SessionNavigationComponentBase):
    page_left_button = ButtonControl(
        color="Session.Navigation",
        pressed_color="Session.NavigationPressed",
    )
    page_right_button = ButtonControl(
        color="Session.Navigation",
        pressed_color="Session.NavigationPressed",
    )
    track_range_string = listenable_property.managed("")

    @depends(session_ring=None)
    def __init__(self, session_ring=None, *a, **k):
        super().__init__(*a, session_ring=session_ring, snap_track_offset=True, **k)
        self._session_ring = session_ring
        self.register_slot(self._page_horizontal.scrollable, self._on_tracks_scrolled, "scrolled")
        self.register_slot(self._scroll_horizontal.scrollable, self._on_tracks_scrolled, "scrolled")
        self.register_slot(session_ring, self._on_tracks_changed, "tracks")
        self._on_tracks_changed()

    def set_page_left_button(self, button):
        self.page_left_button.set_control_element(button)

    def set_page_right_button(self, button):
        self.page_right_button.set_control_element(button)

    @page_left_button.pressed
    def page_left_button(self, _):
        if self._page_horizontal.can_scroll_up():
            self._page_horizontal.scroll_up()
        elif self._can_page_left:
            self._session_ring.is_controlling_returns = False
            self._on_tracks_scrolled()

    @page_right_button.pressed
    def page_right_button(self, _):
        if self._page_horizontal.can_scroll_down():
            self._page_horizontal.scroll_down()
        elif self._can_page_right:
            self._session_ring.is_controlling_returns = True
            self._on_tracks_scrolled()

    @property
    def _can_page_left(self):
        return self._page_horizontal.can_scroll_up() or self._session_ring.is_controlling_returns

    @property
    def _can_page_right(self):
        return self._page_horizontal.can_scroll_down() or (
            not self._session_ring.is_controlling_returns and self._session_ring.can_control_returns
        )

    def _on_tracks_scrolled(self):
        if self._session_ring.track_offset in range(len(self._session_ring.tracks_to_use())):
            action.select(self._session_ring.tracks_to_use()[self._session_ring.track_offset])

    def _on_tracks_changed(self):
        self.page_left_button.enabled = self._can_page_left
        self.page_right_button.enabled = self._can_page_right
        self.track_range_string = self._get_track_range_string()

    def _get_track_range_string(self):
        header = "Return" if self._session_ring.is_controlling_returns else "Track"
        tracks = self._session_ring.tracks
        first_track = find_if(liveobj_valid, tracks)
        last_track = find_if(liveobj_valid, reversed(tracks))
        if first_track == last_track:
            return "{} {}".format(header, simple_track_name(first_track))
        return "{}s {}-{}".format(
            header,
            simple_track_name(first_track),
            simple_track_name(last_track),
        )
