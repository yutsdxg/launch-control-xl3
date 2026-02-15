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
            "volume_controls": "mixer_volume_faders",
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
            "device_toggle": {
                "component": "Device_Toggle",
                "toggle_button_1": "device_toggle_1_button",
                "toggle_button_2": "device_toggle_2_button",
                "toggle_button_3": "device_toggle_3_button",
                "toggle_button_4": "device_toggle_4_button",
                "toggle_button_5": "device_toggle_5_button",
                "toggle_button_6": "device_toggle_6_button",
                "toggle_button_7": "device_toggle_7_button",
                "toggle_button_8": "device_toggle_8_button",
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
                        "pan_controls": "mixer_pan_encoders",
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
