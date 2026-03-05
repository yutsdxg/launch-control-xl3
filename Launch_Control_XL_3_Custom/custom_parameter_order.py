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
# - Instrument Rack選択時の子デバイス透過は未対応（本体デバイス選択時のみ適用）
#   例: Meldのカスタム順序はMeld本体を直接選択した場合のみ有効
#
CUSTOM_DEVICE_PARAMETER_ORDER = {
    "Wavetable": (
        # Encoder 1-8
        "Osc 1 Pos",
        "Osc 1 Effect 1",
        "Osc 1 Effect 2",
        "Osc 1 Gain",
        "Env 2 Attack",
        "Env 2 Decay",
        "Env 2 Sustain",
        "Env 2 Release",
        # Encoder 9-16
        "Osc 2 Pos",
        "Osc 2 Effect 1",
        "Osc 2 Effect 2",
        "Osc 2 Gain",
        "Amp Attack",
        "Amp Decay",
        "Amp Sustain",
        "Amp Release",
        # Encoder 17-20
        "Filter 1 Freq",
        "Filter 1 Res",
        "Env 2 Peak",
        "Filter 1 Drive",
        # Encoder 21
        "Volume",
        # Button 9-16
        "Sub On",
        "Osc 1 On",
        "Osc 2 On",
    ),
    "Analog": (
        # Encoder 1-8
        "OSC1 Octave",
        "OSC1 Shape",
        "OSC1 Level",
        "Noise Color",
        "FEG1 Attack",
        "FEG1 Decay",
        "FEG1 Sustain",
        "FEG1 Rel",
        # Encoder 9-16
        "OSC2 Octave",
        "OSC2 Shape",
        "OSC2 Level",
        "Noise Level",
        "AEG1 Attack",
        "AEG1 Decay",
        "AEG1 Sustain",
        "AEG1 Rel",
        # Encoder 17-20
        "Filter 1 Freq",
        "Filter 1 Res",
        "F1 Freq < Env",
        None,
        # Encoder 21
        "Volume",
        # Button 9-16
        "OSC1 On/Off",
        "OSC2 On/Off",
        "Noise On/Off",
        "Unison On/Off",
    ),
    "Drift": (
        # Encoder 1-8
        "Osc 1 Oct",
        "Osc 1 Wave",
        "Osc 1 Shape",
        "Osc 1 Gain",
        "Env 2 Attack",
        "Env 2 Decay",
        "Env 2 Sustain",
        "Env 2 Release",
        # Encoder 9-16
        "Osc 2 Oct",
        "Osc 2 Wave",
        "Osc 2 Shape",
        "Osc 2 Gain",
        "Env 1 Attack",
        "Env 1 Decay",
        "Env 1 Sustain",
        "Env 1 Release",
        # Encoder 17-20
        "LP Freq",
        "LP Reso",
        "LP Mod Amt 1",
        "HP Freq",
        # Encoder 21
        "Volume",
        # Button 9-16
        "Osc 1 On",
        "Osc 2 On",
        "Noise On",
        "LP Type",
    ),
    "Meld": (
        # Encoder 1-8
        "A Octave",
        "A Osc Type",
        "A Osc Shape",
        "A Osc Tone",
        "A Mod Attack",
        "A Mod Decay",
        "A Mod Peak",
        "A Mod Release",
        # Encoder 9-16
        "B Octave",
        "B Osc Type",
        "B Osc Shape",
        "B Osc Tone",
        "A Amp Attack",
        "A Amp Decay",
        "A Amp Sustain",
        "A Amp Release",
        # Encoder 17-20
        "A Filter Freq",
        "A Filter Q",
        "A Filter L-B-H-N",
        "A Filter Type",
        # Encoder 21
        "Volume",
        # Button 9-16
        "A On",
        "B On",
    ),
    "Sampler": (
        # Encoder 1-8
        None,
        None,
        None,
        None,
        "Fe Attack",
        "Fe Decay",
        "Fe Sustain",
        "Fe Release",
        # Encoder 9-16
        None,
        None,
        None,
        None,
        "Ve Attack",
        "Ve Decay",
        "Ve Sustain",
        "Ve Release",
        # Encoder 17-20
        "Filter Freq",
        "Filter Res",
        "Fe < Env",
        "Filter Drive",
        # Encoder 21
        "Volume",
        # Button 9-16
        "OSC1 On/Off",
        "OSC2 On/Off",
        "Noise On/Off",
        "Unison On/Off",
    ),
    "Saturator": (
        # Encoder 1-8
        "Type",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        # Encoder 9-16
        "Post Clip Mode",
        "Color On",
        "Color Amt Low",
        None,
        None,
        None,
        None,
        None,
        # Encoder 17-20
        "Drive",
        "Output",
        "Dry/Wet",
        None,
        # Encoder 21
        None,
    ),
    "Echo": (
        # Encoder 1-8
        {"L Division": {"mode_count": 7}},
        "L Sync Mode",
        "R Division",
        "R Sync Mode",
        "Reverb",
        None,
        None,
        "Stereo",
        # Encoder 9-16
        "L Offset",
        None,
        "R Offset",
        None,
        "Reverb Loc",
        "Reverb Decay",
        "Channel Mode",
        "Output",
        # Encoder 17-20
        "Input",
        "Feedback",
        "HP Freq",
        "LP Freq",
        # Encoder 21
        "Dry Wet",
        # Button 9-16
        "Link",
        "Clip Dry",
        "Filter On",

    ),
    "Reverb": (
        # Encoder 1-8
        "In Filter Freq",
        "ER Spin Amount",
        "ER Spin Rate",
        "HiFilter Freq",
        "HiShelf Gain",
        "Diffusion",
        "Chorus Amount",
        "Reflect",
        # Encoder 9-16
        "In Filter Width",
        None,
        "ER Shape",
        "LowShelf Freq",
        "LowShelf Gain",
        "Scale",
        "Chorus Rate",
        "Diffuse",
        # Encoder 17-20
        "Predelay",
        "Size",
        "Decay",
        "Stereo",
        # Encoder 21
        "Dry Wet",
        # Button 9-16
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
        None,
        "2 Gain A",
        "3 Gain A",
        None,
        None,
        None,
        None,
        None,
        # Encoder 17-20
        "1 Resonance A",
        "2 Resonance A",
        "3 Resonance A",
        "4 Resonance A",
        # Encoder 21
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
        # Encoder 1-8
        "Frequency",
        None,
        None,
        None,
        None,
        None,
        None,
        "Drive",
        # Encoder 9-16
        "Type",
        None,
        None,
        None,
        None,
        None,
        None,
        "Output",
        # Encoder 17-20
        "Resonance",
        "LFO Amount",
        "LFO Freq",
        None,
        # Encoder 21
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
