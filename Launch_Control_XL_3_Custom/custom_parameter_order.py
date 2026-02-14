# -*- coding: utf-8 -*-  # Ableton Liveの付属デバイス用カスタムパラメータ順序
"""
Ableton Live標準のパラメータ順序を任意に変更したい場合は、ここにデバイス名をキーとした
`CUSTOM_DEVICE_PARAMETER_ORDER` を追記してください。

デバイス名は表示名・クラス名のどちらでも指定できます。末尾の数字などは自動的に無視されます。

「何もアサインしない」スロットを作りたい場合は、その位置に `None` もしくは `"SKIP"` を指定してください。
"""

# False: custom_parameter_order.py に書いた項目だけをアサイン（未指定は空き）
# True: 書いた項目の後ろにデフォルトの残りパラメータを自動で連結
CUSTOM_PARAMETER_APPEND_REST = False

# 離散モード切り替えの増減制御は、必要な項目だけ dict で指定します。
#
# - 通常: "Parameter Name"
# - 未割り当て: None / "SKIP"
# - モード数を明示する場合だけ: {"Parameter Name": {"mode_count": 7}}
#
CUSTOM_DEVICE_PARAMETER_ORDER = {
    "Wavetable": (
        "Osc 1 Gain",
        "Osc 1 Pos",
        "Osc 1 Effect 1",
        "Osc 1 Effect 2",
        "Osc 2 Gain",
        "Osc 2 Pos",
        "Osc 2 Effect 1",
        "Osc 2 Effect 2",
        "Amp Attack",
        "Amp Decay",
        "Amp Sustain",
        "Amp Release",
        "Env 2 Attack",
        "Env 2 Decay",
        "Env 2 Sustain",
        "Env 2 Release",
        "Filter 1 Freq",
        "Filter 1 Res",
        "Env 2 Peak",
        "Filter 1 Drive",
        "Volume",
        "Sub On",
        "Osc 1 On",
        "Osc 2 On",
    ),
    "Saturator": (
        "Type",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "Post Clip Mode",
        "Color On",
        "Color Amt Low",
        None,
        None,
        None,
        None,
        None,
        "Drive",
        "Output",
        "Dry/Wet",
    ),
    "Echo": (
        # 1-8
        {"L Division": {"mode_count": 7}},
        "L Sync Mode",
        "R Division",
        "R Sync Mode",
        "Reverb",
        None,
        None,
        "Stereo",
        # 9-16
        "L Offset",
        None,
        "R Offset",
        None,
        "Reverb Loc",
        "Reverb Decay",
        "Channel Mode",
        "Output",
        # 17-21
        "Input",
        "Feedback",
        "HP Freq",
        "LP Freq",
        # 22
        "Dry Wet",
        # Button 9-16
        "Link",
        "Clip Dry",
        "Filter On",

    ),
    "Reverb": (
        # 1-8
        "In Filter Freq",
        "ER Spin Amount",
        "ER Spin Rate",
        "HiFilter Freq",
        "HiShelf Gain",
        "Diffusion",
        "Chorus Amount",
        "Reflect",
        # 9-16
        "In Filter Width",
        None,
        "ER Shape",
        "LowShelf Freq",
        "LowShelf Gain",
        "Scale",
        "Chorus Rate",
        "Diffuse",
        # 17-21
        "Predelay",
        "Size",
        "Decay",
        "Stereo",
        "Dry Wet",
    ),
    "EQ Eight": (
        # Encoder 1-8
        "1 Frequency A",
        "2 Frequency A",
        "3 Frequency A",
        "4 Frequency A",
        None,
        None,
        None,
        None,
        # Encoder 9-16
        "1 Resonance A",
        "2 Gain A",
        "3 Gain A",
        "4 Resonance A",
        None,
        None,
        None,
        None,
        # Encoder 17-21
        "1 Filter Type A",
        "2 Resonance A",
        "3 Resonance A",
        "4 Filter Type A",
        # Encoder 22
        "Output Gain",
        # Button 9-16
        "1 Filter On A",
        "2 Filter On A",
        "3 Filter On A",
        "4 Filter On A",
        None,
        None,
        None,
        None,
    ),
    "Auto Filter": (
        # 1-8
        "Frequency",
        None,
        None,
        None,
        None,
        None,
        None,
        "Drive",
        # 9-16
        "Type",
        None,
        None,
        None,
        None,
        None,
        None,
        "Output",
        # 17-21
        "Resonance",
        "LFO Amount",
        "LFO Freq",
        None,
        # 22
        "Dry Wet",
        # Button 9-16
        "Slope",
        None,
        None,
        None,
        None,
        None,
        None,
        "Soft Clip On",
    ),
}
"""
    "Reverb": (
        # 1-8
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        # 9-16
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        # 17-21
        None,
        None,
        None,
        None,
        # 22
        None,
        # Button 9-16
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
"""
