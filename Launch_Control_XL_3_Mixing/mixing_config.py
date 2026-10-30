"""Mixingの起動設定。変更後はRemote MIDI Scriptを再読み込みする。

device / send / occurrence は1始まり。deviceは選択トラック直下の順番。
parameterはLiveが公開する名前との完全一致。Noneまたは未指定は未割り当て。
Instrumentの配置は従来どおりcustom_parameter_order.pyで設定する。
"""

# "configured": 下記の設定を使う新Mixing（標準）。"legacy": 従来の固定Mixing。
MIXING_IMPLEMENTATION = "configured"

MIXING_ASSIGNMENTS = {
    # エンコーダー上段
    "encoder_1": None,
    "encoder_2": None,
    "encoder_3": None,
    "encoder_4": None,
    "encoder_5": None,
    "encoder_6": None,
    "encoder_7": None,
    "encoder_8": {"mixer": "cue_volume"},
    # エンコーダー中段
    "encoder_9": None,
    "encoder_10": None,
    "encoder_11": None,
    "encoder_12": None,
    "encoder_13": None,
    "encoder_14": None,
    "encoder_15": None,
    "encoder_16": None,
    # エンコーダー下段
    "encoder_17": None,
    "encoder_18": None,
    "encoder_19": None,
    "encoder_20": None,
    "encoder_21": None,
    "encoder_22": None,
    "encoder_23": None,
    "encoder_24": None,
    # フェーダー
    "fader_1": None,
    "fader_2": None,
    "fader_3": None,
    "fader_4": None,
    "fader_5": None,
    "fader_6": None,
    "fader_7": None,
    "fader_8": None,
}

# 記入例：使う枠のNoneを下記のような辞書に置き換える。
# "encoder_1": {"device": 4, "parameter": "Device On", "directional_on_off": True},
# "encoder_8": {"mixer": "cue_volume"},  # Masterのブラウザ・プレビュー音量
# "encoder_9": {"device": 4, "parameter": "Attack"},
# "encoder_10": {"device": 5, "parameter": "Gain", "occurrence": 2},
# "encoder_16": {"mixer": "send", "send": 1},
# "encoder_24": {"mixer": "pan"},
# "fader_8": {"mixer": "volume"},
# directional_on_off=Trueは左回しで最小値、右回しで最大値。エンコーダー専用。
# 省略またはFalseなら通常操作。Device Onもフェーダーへ通常割り当て可能。
