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
    mappings = { }
    mappings['Transport'] = dict(play_toggle_button = 'play_button', play_pause_button = 'play_button_with_shift')
    mappings['View_Based_Recording'] = dict(record_button = 'record_button')
    mappings['Mixer'] = dict(volume_controls = 'faders')
    mappings['View_Control'] = dict(prev_track_button = 'track_left_button', next_track_button = 'track_right_button')
    mappings['Session_Navigation'] = dict(page_left_button = 'track_left_button_with_shift', page_right_button = 'track_right_button_with_shift')
    mappings['Encoder_Touch'] = dict(touch_controls = 'encoder_touch_elements')
    mappings['Daw_Control_Button_Modes'] = dict(cycle_mode_button = 'daw_control_mode_button', solo = dict(component = 'Mixer', solo_buttons = 'daw_control_buttons'), arm = dict(component = 'Mixer', arm_buttons = 'daw_control_buttons'))
    mappings['Daw_Mixer_Button_Modes'] = dict(cycle_mode_button = 'daw_mixer_mode_button', mute = dict(component = 'Mixer', mute_buttons = 'daw_mixer_buttons'), track_select = dict(component = 'Mixer', track_select_buttons = 'daw_mixer_buttons'))
    mappings['Encoder_Modes'] = dict(is_private = True, mode_selection_control = 'encoder_mode_element', daw_mixer = dict(modes = [
        dict(component = 'Mixer', send_controls = 'upper_encoders', pan_controls = 'lower_encoders', prev_send_index_button = 'page_up_button', next_send_index_button = 'page_down_button'),
        set_relative_encoder_mode(control_surface)], behaviour = make_relative_encoder_mode_behavior(control_surface), index = 1), daw_control = dict(modes = [
        dict(component = 'Device', parameter_controls = 'upper_encoders', prev_bank_button = 'page_up_button', next_bank_button = 'page_down_button'),
        dict(component = 'Device_Navigation', prev_button = 'page_up_button_with_shift', next_button = 'page_down_button_with_shift'),
        dict(component = 'Transport', arrangement_position_encoder = 'lower_encoders_raw[0]', loop_start_encoder = 'lower_encoders_raw[3]', loop_length_encoder = 'lower_encoders_raw[4]', loop_toggle_encoder = 'lower_encoders_raw[5]', tempo_coarse_encoder = 'lower_encoders_raw[7]'),
        dict(component = 'Zoom', horizontal_zoom_encoder = 'lower_encoders_raw[1]', vertical_zoom_encoder = 'lower_encoders_raw[2]'),
        dict(component = 'Cue_Point', encoder = 'lower_encoders_raw[6]'),
        set_relative_encoder_mode(control_surface)], behaviour = make_relative_encoder_mode_behavior(control_surface), index = 2))
    return mappings
