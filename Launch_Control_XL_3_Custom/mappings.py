from ableton.v3.control_surface.mode import ImmediateBehaviour, make_reenter_behaviour
from .midi import SET_RELATIVE_ENCODER_MODES

def set_relative_encoder_mode(control_surface):
    def send_messages():
        for msg in SET_RELATIVE_ENCODER_MODES:
            control_surface.send_midi(msg)

    return send_messages


def make_relative_encoder_mode_behavior(control_surface):
    return make_reenter_behaviour(ImmediateBehaviour, on_reenter=set_relative_encoder_mode(control_surface))


def create_mappings(control_surface):
    return {
        "Transport": {
            "play_toggle_button": "play_button",
            "play_pause_button": "play_button_with_shift",
        },
        "View_Based_Recording": {
            "record_button": "record_button",
        },
        "Mixer": {
            "volume_controls": "faders",
        },
        "View_Control": {
            "prev_track_button": "track_left_button",
            "next_track_button": "track_right_button",
        },
        "Session_Navigation": {
            "page_left_button": "track_left_button_with_shift",
            "page_right_button": "track_right_button_with_shift",
        },
        "Encoder_Touch": {
            "touch_controls": "encoder_touch_elements",
        },
        "Daw_Control_Button_Modes": {
            "cycle_mode_button": "daw_control_mode_button",
            "solo": {
                "component": "Mixer",
                "solo_buttons": "daw_control_buttons",
            },
            "arm": {
                "component": "Mixer",
                "arm_buttons": "daw_control_buttons",
            },
        },
        "Daw_Mixer_Button_Modes": {
            "cycle_mode_button": "daw_mixer_mode_button",
            "mute": {
                "component": "Mixer",
                "mute_buttons": "daw_mixer_buttons",
            },
            "track_select": {
                "component": "Mixer",
                "track_select_buttons": "daw_mixer_buttons",
            },
        },
        "Encoder_Modes": {
            "is_private": True,
            "mode_selection_control": "encoder_mode_element",
            "daw_mixer": {
                "modes": [
                    {
                        "component": "Mixer",
                        "send_controls": "upper_encoders",
                        "pan_controls": "lower_encoders",
                        "prev_send_index_button": "page_up_button",
                        "next_send_index_button": "page_down_button",
                    },
                    set_relative_encoder_mode(control_surface),
                ],
                "behaviour": make_relative_encoder_mode_behavior(control_surface),
                "index": 1,
            },
            "daw_control": {
                "modes": [
                    {
                        "component": "Device",
                        "parameter_controls": "device_parameter_encoders",
                        "prev_bank_button": "page_up_button",
                        "next_bank_button": "page_down_button",
                    },
                    {
                        "component": "Device_Navigation",
                        "prev_button": "page_up_button_with_shift",
                        "next_button": "page_down_button_with_shift",
                    },
                    set_relative_encoder_mode(control_surface),
                ],
                "behaviour": make_relative_encoder_mode_behavior(control_surface),
                "index": 2,
            },
        },
    }
