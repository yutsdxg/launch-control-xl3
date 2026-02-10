from .colors import Rgb, make_color_for_liveobj

class Skin:
    
    class Transport:
        PlayOn = Rgb.GREEN
        PlayOff = Rgb.GREEN_HALF

    
    class Recording:
        ArrangementRecordOn = Rgb.RED
        ArrangementRecordOff = Rgb.RED_HALF
        SessionRecordOn = Rgb.RED
        SessionRecordOff = Rgb.RED_HALF
        SessionRecordTransition = Rgb.RED_BLINK

    
    class ViewControl:
        TrackPressed = Rgb.WHITE
        Track = Rgb.WHITE_HALF

    
    class Session:
        NavigationPressed = Rgb.WHITE
        Navigation = Rgb.WHITE_HALF

    
    class Device:
        NavigationPressed = Rgb.WHITE
        Navigation = Rgb.WHITE_HALF
        
        class Bank:
            NavigationPressed = Rgb.WHITE
            Navigation = Rgb.WHITE_HALF


    
    class Mixer:
        ArmOn = Rgb.RED
        ArmOff = Rgb.RED_HALF
        MuteOn = Rgb.ORANGE_HALF
        MuteOff = Rgb.ORANGE
        SoloOn = Rgb.BLUE
        SoloOff = Rgb.BLUE_HALF
        Selected = Rgb.WHITE
        NotSelected = make_color_for_liveobj
        IncrementSendIndexPressed = Rgb.WHITE
        IncrementSendIndex = Rgb.WHITE_HALF

    
    class DawControlButtonModes:
        
        class Solo:
            On = Rgb.BLUE

        
        class Arm:
            On = Rgb.RED


    
    class DawMixerButtonModes:
        
        class Mute:
            On = Rgb.ORANGE

        
        class TrackSelect:
            On = Rgb.WHITE


