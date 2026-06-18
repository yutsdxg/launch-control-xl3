from ableton.v3.control_surface import ElementsBase, MapMode
from Launchkey_MK4.display_target import DisplayTargetElement

from . import midi
from .colored_encoder import ColoredEncoderElement

CHANNEL_DAW_MODE = 6
CHANNEL_ENCODER_LED = 15

CC_SHIFT_BUTTON = 63
CC_SOLO_MODIFIER = 65
CC_MUTE_MODIFIER = 66
CC_TRACK_RIGHT = 102
CC_TRACK_LEFT = 103
CC_PLAY = 116
CC_RECORD = 118

RANGE_TRACK_BUTTONS_1_8 = range(37, 45)
RANGE_TRACK_BUTTONS_9_16 = range(45, 53)
RANGE_FADERS = range(5, 13)
RANGE_UPPER_ENCODERS_ROW_1 = range(77, 85)
RANGE_UPPER_ENCODERS_ROW_2 = range(85, 93)
RANGE_LOWER_ENCODERS = range(93, 101)

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
        self.add_button(CC_SHIFT_BUTTON, "Shift_Button", channel=CHANNEL_DAW_MODE)
        self.add_button(CC_SOLO_MODIFIER, "Solo_Modifier_Button")
        self.add_button(CC_MUTE_MODIFIER, "Mute_Modifier_Button")
        self.add_button(CC_TRACK_RIGHT, "Track_Right_Button")
        self.add_button(CC_TRACK_LEFT, "Track_Left_Button")
        self.add_button(CC_PLAY, "Play_Button")
        self.add_button(CC_RECORD, "Record_Button")

        for index, identifier in enumerate(
            tuple(RANGE_TRACK_BUTTONS_1_8) + tuple(RANGE_TRACK_BUTTONS_9_16),
            start=1,
        ):
            self.add_button(identifier, "Track_Button_{}".format(index))

        self.add_encoder_matrix([RANGE_FADERS], "Faders", channels=CHANNEL_ENCODER_LED)
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
        self.add_sysex_element(midi.make_connection_message()[:-2], "Connection_Element")
        self.add_display_command_for_target("Temp", TARGET_TEMP, 3, disable_caching=True)
        for index in range(NUM_FADER_TARGETS):
            self.add_display_command_for_target("Fader_{}".format(index), TARGET_FADER_BASE + index, 3)
        for index in range(NUM_UPPER_ENCODER_TARGETS):
            self.add_display_command_for_target(
                "Upper_Encoder_{}".format(index),
                TARGET_UPPER_ENCODER_BASE + index,
                3,
            )
        for index in range(NUM_LOWER_ENCODER_TARGETS):
            self.add_display_command_for_target(
                "Lower_Encoder_{}".format(index),
                TARGET_LOWER_ENCODER_BASE + index,
                3,
            )

    def add_display_command_for_target(self, name, target, num_fields, disable_caching=False):
        self.add_element(
            "{}_Display_Command".format(name),
            DisplayTargetElement,
            midi.SYSEX_HEADER,
            target,
            num_fields,
            disable_caching=disable_caching,
        )
