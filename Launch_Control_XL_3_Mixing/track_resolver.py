from ableton.v3.live import liveobj_valid


def song_tracks(song):
    try:
        return tuple(song.tracks)
    except (AttributeError, RuntimeError):
        return ()


def selected_track(song):
    try:
        track = song.view.selected_track
    except (AttributeError, RuntimeError):
        return None
    return track if liveobj_valid(track) else None


def top_level_groups(song):
    groups = []
    for track in song_tracks(song):
        try:
            if getattr(track, "is_foldable", False) and not getattr(track, "is_grouped", False):
                groups.append(track)
        except RuntimeError:
            continue
    return tuple(groups)


def direct_group_children(song, group):
    children = []
    for track in song_tracks(song):
        try:
            if getattr(track, "is_grouped", False) and getattr(track, "group_track", None) == group:
                children.append(track)
        except RuntimeError:
            continue
    return tuple(children)


def first_named_track(song, name):
    for track in song_tracks(song):
        try:
            if track.name == name:
                return track
        except RuntimeError:
            continue
    return None


def track_button_targets(song):
    groups = top_level_groups(song)
    first_group = groups[0] if len(groups) > 0 else None
    second_group = groups[1] if len(groups) > 1 else None
    first_children = direct_group_children(song, first_group) if first_group is not None else ()
    second_children = direct_group_children(song, second_group) if second_group is not None else ()
    return (
        first_group,
        *first_children[:6],
        *([None] * max(0, 6 - len(first_children))),
        first_named_track(song, "Bass"),
        second_group,
        *second_children[:7],
        *([None] * max(0, 7 - len(second_children))),
    )
