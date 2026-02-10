from ableton.v3.base import nop
from ableton.v3.control_surface import ElementsBase, MapMode
from ableton.v3.control_surface.elements import ButtonMatrixElement
from Launchkey_MK4.display_target import DisplayTargetElement
from . import midi
from .colored_encoder import ColoredEncoderElement

# MIDI channels
CHANNEL_DAW_MODE = 6
CHANNEL_ENCODER_LED = 15
CHANNEL_TOUCH = 14

# Button CCs
CC_SHIFT_BUTTON = 63
CC_ENCODER_MODE = 30
CC_ENCODER_USER_MODE = 31
CC_DAW_CONTROL_MODE = 65
CC_DAW_MIXER_MODE = 66
CC_TRACK_RIGHT = 102
CC_TRACK_LEFT = 103
CC_NOVATION = 104
CC_PAGE_UP = 106
CC_PAGE_DOWN = 107
CC_PLAY = 116
CC_RECORD = 118

# Matrix ranges
RANGE_DAW_CONTROL_BUTTONS = range(37, 45)
RANGE_DAW_MIXER_BUTTONS = range(45, 53)
RANGE_FADERS = range(5, 13)
RANGE_UPPER_ENCODERS_ROW_1 = range(77, 85)
RANGE_UPPER_ENCODERS_ROW_2 = range(85, 93)
RANGE_LOWER_ENCODERS = range(93, 101)
RANGE_ENCODER_TOUCH = range(77, 101)

# Display targets
TARGET_STATIC = 53
TARGET_TEMP = 54
TARGET_FADER_BASE = 5
TARGET_UPPER_ENCODER_BASE = 13
TARGET_LOWER_ENCODER_BASE = 29
NUM_FADER_TARGETS = 8
NUM_UPPER_ENCODER_TARGETS = 16
NUM_LOWER_ENCODER_TARGETS = 8

class Elements(ElementsBase):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.add_modifier_button(CC_SHIFT_BUTTON, "Shift_Button", channel=CHANNEL_DAW_MODE)

        self.add_button(CC_ENCODER_MODE, "Encoder_Mode_Element", channel=CHANNEL_DAW_MODE)
        self.add_button(CC_ENCODER_USER_MODE, "Encoder_User_Mode_Element", channel=CHANNEL_DAW_MODE)
        self.add_button(CC_DAW_CONTROL_MODE, "Daw_Control_Mode_Button")
        self.add_button(CC_DAW_MIXER_MODE, "Daw_Mixer_Mode_Button")
        self.add_button(CC_TRACK_RIGHT, "Track_Right_Button")
        self.add_button(CC_TRACK_LEFT, "Track_Left_Button")
        self.add_button(CC_NOVATION, "Novation_Button")
        self.add_button(CC_PAGE_UP, "Page_Up_Button")
        self.add_button(CC_PAGE_DOWN, "Page_Down_Button")
        self.add_button(CC_PLAY, "Play_Button")
        self.add_button(CC_RECORD, "Record_Button")

        self.add_button_matrix([RANGE_DAW_CONTROL_BUTTONS], "Daw_Control_Buttons")
        self.add_button_matrix([RANGE_DAW_MIXER_BUTTONS], "Daw_Mixer_Buttons")

        self.add_modified_control(control=self.play_button, modifier=self.shift_button)
        self.add_modified_control(control=self.track_right_button, modifier=self.shift_button)
        self.add_modified_control(control=self.track_left_button, modifier=self.shift_button)
        self.add_modified_control(control=self.page_up_button, modifier=self.shift_button)
        self.add_modified_control(control=self.page_down_button, modifier=self.shift_button)

        self.add_encoder_matrix([RANGE_FADERS], "Faders", channels=CHANNEL_ENCODER_LED)
        self.add_button_matrix([RANGE_FADERS], "Fader_Touch_Elements", channels=CHANNEL_TOUCH, is_private=True)

        self.add_matrix(
            [RANGE_UPPER_ENCODERS_ROW_1, RANGE_UPPER_ENCODERS_ROW_2],
            "Upper_Encoders",
            map_mode=MapMode.LinearBinaryOffset,
            channels=CHANNEL_ENCODER_LED,
            element_factory=ColoredEncoderElement,
        )
        self.add_matrix(
            [RANGE_LOWER_ENCODERS],
            "Lower_Encoders",
            map_mode=MapMode.LinearBinaryOffset,
            channels=CHANNEL_ENCODER_LED,
            element_factory=ColoredEncoderElement,
        )
        self.add_element(
            "Device_Parameter_Encoders",
            ButtonMatrixElement,
            rows=[list(self.upper_encoders_raw) + list(self.lower_encoders_raw[:5])],
            is_private=True,
        )
        self.add_button_matrix([RANGE_ENCODER_TOUCH], "Encoder_Touch_Elements", channels=CHANNEL_TOUCH, is_private=True)

        self.add_sysex_element(midi.make_connection_message()[:-2], "Connection_Element")

        self.add_display_command_for_target("Static", TARGET_STATIC, 9)
        self.add_display_command_for_target("Temp", TARGET_TEMP, 3, disable_caching=True)
        for i in range(NUM_FADER_TARGETS):
            self.add_display_command_for_target("Fader_{}".format(i), TARGET_FADER_BASE + i, 3)
        for i in range(NUM_UPPER_ENCODER_TARGETS):
            self.add_display_command_for_target(
                "Upper_Encoder_{}".format(i),
                TARGET_UPPER_ENCODER_BASE + i,
                3,
            )
        for i in range(NUM_LOWER_ENCODER_TARGETS):
            self.add_display_command_for_target(
                "Lower_Encoder_{}".format(i),
                TARGET_LOWER_ENCODER_BASE + i,
                3,
            )

        # 固定値送信を無効化して、モード切替側で明示送信する。
        self.encoder_mode_element.send_value = nop

    def add_display_command_for_target(self, name, target, num_fields, disable_caching=False):
        self.add_element(
            "{}_Display_Command".format(name),
            DisplayTargetElement,
            midi.SYSEX_HEADER,
            target,
            num_fields,
            disable_caching=disable_caching,
        )
