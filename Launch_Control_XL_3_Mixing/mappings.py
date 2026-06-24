def create_mappings(_control_surface):
    control_router = {}
    for index in range(1, 25):
        if index <= 16:
            control = "upper_encoders_raw[{}]".format(index - 1)
            display = "upper_encoder_{}_display_command".format(index - 1)
        else:
            control = "lower_encoders_raw[{}]".format(index - 17)
            display = "lower_encoder_{}_display_command".format(index - 17)
        control_router["encoder_{}".format(index)] = control
        control_router["encoder_{}_display".format(index)] = display
    for index in range(1, 9):
        control_router["fader_{}".format(index)] = "faders_raw[{}]".format(index - 1)
        control_router["fader_{}_display".format(index)] = "fader_{}_display_command".format(index - 1)
    for index in range(1, 17):
        control_router["track_button_{}".format(index)] = "track_button_{}".format(index)
    track_buttons = {
        "shift_button": "shift_button",
        "solo_modifier_button": "solo_modifier_button",
        "mute_modifier_button": "mute_modifier_button",
    }
    return {
        "Transport": {
            "play_toggle_button": "play_button",
        },
        "View_Based_Recording": {
            "record_button": "record_button",
        },
        "Control_Router": control_router,
        "Fixed_Assignments": {},
        "Track_Buttons": track_buttons,
        "Mode_Manager": {
            "mixing_button": "page_up_button",
            "instrument_button": "page_down_button",
        },
        "Instrument_Assignments": {},
        "Locator_Navigation": {
            "prev_locator_button": "track_left_button",
            "next_locator_button": "track_right_button",
        },
    }
