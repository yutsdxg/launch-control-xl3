from .colors import Rgb


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
