# Launch_Control_XL_3_Mixing 仕様

この文書は、現行の `Launch_Control_XL_3_Mixing` とできる限り同一の設定を持つ Launch Control XL MK2 用 Remote MIDI Script を作るための仕様メモである。記述はこのリポジトリの現在の作業ツリーを基準にしている。

## 概要

- Ableton Live 12 系の `ableton.v3.control_surface.ControlSurface` ベースの Remote MIDI Script。
- 起動時の既定モードは `mixing`。
- `mixing` モードでは、固定パラメータ割り当てとトラック選択/solo/mute ボタンを有効化する。
- `instrument` モードでは、選択トラック上の 3 番目のデバイスを 24 エンコーダ、8 フェーダ、16 ボタンへ直列割り当てする。
- 物理コントロールは `Control_Router` に一度集約され、`Fixed_Assignments`、`Instrument_Assignments`、`Track_Buttons` へ転送される。
- `AUTO_LOAD` は使っていない。

## デバイス認識とポート

- Controller ID:
  - `vendor_id`: `4661`
  - `product_ids`: `328` から `335`
  - `model_name`: `LCXL3 1` から `LCXL3 8`
- `identity_response_id_bytes`: `(0, 32, 41, -1, 1, 0, 1)`
- ポート:
  - 入力 2 本: 通常入力、`SCRIPT` 入力
  - 出力 2 本: 通常出力、`SYNC` + `SCRIPT` 出力
- 接続時 SysEx: `F0 00 20 29 02 15 02 7F F7`
- 切断時 SysEx: `F0 00 20 29 02 15 02 00 F7`
- 識別後、相対エンコーダモード設定として以下の生 MIDI を送信する:
  - `(182, 69, 127)`
  - `(182, 72, 127)`
  - `(182, 73, 127)`

## MIDI 要素

CC は 10 進数表記。`Shift_Button` だけ明示的に `CHANNEL_DAW_MODE = 6`、フェーダとエンコーダは `CHANNEL_ENCODER_LED = 15` を使う。その他のボタンは `ElementsBase.add_button` の既定チャンネルに従う。

| 要素 | CC / 範囲 | 内部名 | 備考 |
| --- | --- | --- | --- |
| Shift | 63 | `Shift_Button` | トラックボタン処理では状態保持のみ。現状アクション変更には使わない |
| Solo modifier | 65 | `Solo_Modifier_Button` | トラックボタンを solo モードへ切り替え |
| Mute modifier | 66 | `Mute_Modifier_Button` | トラックボタンを mute モードへ切り替え |
| Track right | 102 | `Track_Right_Button` | 次ロケータ |
| Track left | 103 | `Track_Left_Button` | 前ロケータ |
| Page up | 106 | `Page_Up_Button` | `mixing` モード |
| Page down | 107 | `Page_Down_Button` | `instrument` モード |
| Play | 116 | `Play_Button` | `Transport.play_toggle_button` |
| Record | 118 | `Record_Button` | `View_Based_Recording.record_button` |
| Track buttons 1-8 | 37-44 | `Track_Button_1` ... `8` | mixing ではトラック操作、instrument ではボタンパラメータ |
| Track buttons 9-16 | 45-52 | `Track_Button_9` ... `16` | 同上 |
| Faders 1-8 | 5-12 | `Faders` matrix | 8 本、チャンネル 15 |
| Encoders 1-8 | 77-84 | `Upper_Encoders` row 1 | `MapMode.LinearBinaryOffset` |
| Encoders 9-16 | 85-92 | `Upper_Encoders` row 2 | `MapMode.LinearBinaryOffset` |
| Encoders 17-24 | 93-100 | `Lower_Encoders` | `MapMode.LinearBinaryOffset` |

表示ターゲットは LCXL3 のディスプレイ向けで、MK2 では同一再現できない可能性が高い。

| 表示対象 | Target ID |
| --- | --- |
| Temp | 54 |
| Fader 1-8 | 5-12 |
| Upper encoder 1-16 | 13-28 |
| Lower encoder 17-24 | 29-36 |

表示は常に 3 行構成、1 行 16 文字まで。`Config.three_line = 98`、`trigger=True`、`show_immediately=False` で送信する。

## モード

| 操作 | 結果 |
| --- | --- |
| Page up | `mixing` モードを選択 |
| Page down | `instrument` モードを選択 |

`mixing` モードでは `Fixed_Assignments` と `Track_Buttons` を active、`Instrument_Assignments` を inactive にする。`instrument` モードでは逆に `Instrument_Assignments` のみ active にする。

モード LED は白系 RGB で、選択中は明るさ `0.25`、非選択は `0.03`。

## Mixing モードの固定割り当て

選択トラックは `song.view.selected_track`。`Loopcloud` トラックは、Live Set 内で名前が完全一致する最初のトラックを使う。デバイス番号は 1 始まり、デバイスパラメータ番号も 1 始まり。ただしデバイスパラメータ番号は `Device On` と空名パラメータを除いた後の番号で、カスタムパラメータ順序があればそれを適用した後の番号になる。

### Loopcloud サブモード

既定サブモード。未記載の `encoder_10`、`encoder_18`、`fader_2` は mixing モードでは割り当てなし。

| 物理操作子 | 割り当て |
| --- | --- |
| Encoder 1 | Loopcloud / MetricAB サブモード切り替え。パラメータ接続なし |
| Encoder 2 | 選択トラック Device 1 の `Device On` |
| Encoder 3 | 選択トラック Device 4 の `Device On` |
| Encoder 4 | 選択トラック Device 5 の `Device On` |
| Encoder 5 | 選択トラック Device 6 の `Device On` |
| Encoder 6 | 選択トラック Device 7 の `Device On` |
| Encoder 7 | 選択トラック Device 9 の `Device On` |
| Encoder 8 | Master の Cue Volume |
| Encoder 9 | `Loopcloud` トラック Device 2 Parameter 2 |
| Encoder 11 | 選択トラック Device 4 Parameter 3 |
| Encoder 12 | 選択トラック Device 5 Parameter 3 |
| Encoder 13 | 選択トラック Device 6 Parameter 3 |
| Encoder 14 | 選択トラック Device 7 Parameter 3 |
| Encoder 15 | 選択トラック Device 9 Parameter 3 |
| Encoder 16 | 選択トラック Send 1 |
| Encoder 17 | `Loopcloud` トラック Device 2 Parameter 1 |
| Encoder 19 | 選択トラック Device 4 Parameter 2 |
| Encoder 20 | 選択トラック Device 5 Parameter 2 |
| Encoder 21 | 選択トラック Device 6 Parameter 2 |
| Encoder 22 | 選択トラック Device 7 Parameter 2 |
| Encoder 23 | 選択トラック Device 9 Parameter 2 |
| Encoder 24 | 選択トラック Track Panning |
| Fader 1 | `Loopcloud` トラック Volume |
| Fader 3 | 選択トラック Device 4 Parameter 1 |
| Fader 4 | 選択トラック Device 5 Parameter 1 |
| Fader 5 | 選択トラック Device 6 Parameter 1 |
| Fader 6 | 選択トラック Device 7 Parameter 1 |
| Fader 7 | 選択トラック Device 9 Parameter 1 |
| Fader 8 | 選択トラック Volume |

### MetricAB サブモード

Encoder 1 を右方向へ回すと `metric_ab`、左方向へ回すと `loopcloud` へ戻る。入力値 `64` は無視する。右方向は MetricAB の AB Switch を最大値、左方向は最小値にする。

MetricAB デバイスは Master トラック上から `device.name == "ADPTR MetricAB"` で検索する。`class_name` や `class_display_name` が一致しても、`name` が完全一致しなければ対象外。

MetricAB サブモード時だけ、以下の 3 コントロールを Master 上の `ADPTR MetricAB` に差し替える。対象デバイスがない場合、これら 3 コントロールは未割り当てになる。

| 物理操作子 | MetricAB 割り当て |
| --- | --- |
| Fader 1 | MetricAB Parameter 1 = `Selected Track` |
| Encoder 17 | MetricAB Parameter 2 = `Selected Cue` |
| Encoder 9 | MetricAB Parameter 3 = `AB Switch` |

Encoder 8 の Cue Volume、Encoder 16 の Send 1、その他の選択トラック系割り当ては MetricAB サブモードでも変わらない。

### Device On エンコーダ

Encoder 2-7 は通常のパラメータ接続ではなく、相対入力方向で対象デバイスの `Device On` を直接書き換える。

| 入力値 | 動作 |
| --- | --- |
| `< 64` | 対象 `Device On` を最小値へ |
| `64` | 無視 |
| `> 64` | 対象 `Device On` を最大値へ |

操作後、3 行表示は `デバイス名 / Device On / 値`。

## Mixing モードのトラックボタン

トラックボタンの対象は、Live Set のトップレベルグループとその直下の子トラックから決まる。トップレベルグループは `is_foldable=True` かつ `is_grouped=False` のトラック。直下の子トラックは `is_grouped=True` かつ `group_track` が対象グループのトラックで、ネストしたグループも子として扱う。

| Button | 対象 |
| --- | --- |
| 1 | 1 番目のトップレベルグループ |
| 2-7 | 1 番目のトップレベルグループの直下子トラック 1-6 |
| 8 | 名前が `Bass` の最初のトラック |
| 9 | 2 番目のトップレベルグループ |
| 10-16 | 2 番目のトップレベルグループの直下子トラック 1-7 |

対象がないボタンは LED off、押しても何もしない。

トラックボタンの動作モード:

| モード | 選択方法 | ボタン押下時の動作 |
| --- | --- | --- |
| Select | 既定。Solo/Mute modifier を再度押して解除 | 未選択トラックなら選択。選択済みトラックを再押下すると mute をトグル |
| Solo | Solo modifier を押す | 対象トラックの `solo` をトグル。選択は変更しない |
| Mute | Mute modifier を押す | 対象トラックの `mute` をトグル。選択は変更しない |

Solo/Mute modifier はラッチ式。同じ modifier をもう一度押すと Select へ戻る。Solo から Mute を押すと Mute へ切り替わる。Shift は現在、押下状態を保存して LED を更新するだけで、トラックボタン動作は変えない。

トラックボタン LED:

- solo 中のトラックは常に blue。
- solo でないトラックは Live のトラックカラーを RGB 化する。
- mute でなければ明るさ `0.25`、mute なら `0.03`。
- 選択トラックは 0.5 秒周期で「現在色」と off を点滅する。
- Solo modifier LED は active 時 blue、idle 時 very dim blue。
- Mute modifier LED は active 時 yellow、idle 時 dark yellow。

## Instrument モード

Instrument モードは選択トラックの 3 番目のデバイス、つまり `track.devices[2]` を対象にする。対象デバイスが存在しない場合は未割り当て。

対象デバイスのパラメータは、`Device On` と空名パラメータを除外した後、カスタムパラメータ順序を適用する。番号は 1 始まり。

| 物理操作子 | 割り当て |
| --- | --- |
| Encoder 1-24 | Parameter 1-24 |
| Fader 1-8 | Parameter 25-32 |
| Track Button 1-16 | Parameter 33-48 |

Instrument ボタンは押下時のみ反応する。対象パラメータの現在値が範囲の中点より大きければ最小値へ、それ以外なら最大値へトグルする。LED は白系で、on 相当なら明るさ `0.25`、off 相当なら `0.03`、未割り当てなら off。

Instrument モードのパラメータ操作時の表示は `対象デバイス名 / パラメータ名 / 値`。

## カスタムパラメータ順序

カスタム順序は `mixing` と `instrument` の両方で使う。

- キーはデバイスの `name`、`class_name`、`class_display_name` のいずれかに一致すれば適用する。
- 比較時は空白正規化、小文字化、末尾の数字削除を行う。例: `Serum 2` は `serum` として扱う。
- `instrumentvector` と `wavetable`、`instrumentmeld` と `meld`、`hybrid` と `reverb` は相互 alias。
- `None` または `SKIP` は空スロット。
- `{"Parameter": {"occurrence": 2}}` のように同名パラメータの何番目かを指定できる。
- `CUSTOM_PARAMETER_APPEND_REST = False` なので、カスタム順序にない残りパラメータは末尾へ追加しない。未指定スロットは未割り当て。

現在定義されているカスタム順序:

| デバイス | スロット |
| --- | --- |
| Serum 2 | Enc 1-8: `A Octave`, `A Unison`, `A Uni Detune`, `B Octave`, `B Unison`, `B Uni Detune`, empty, empty |
| Serum 2 | Enc 9-16: `A WT Pos`, `A Warp`, `A Level`, `B WT Pos`, `B Warp`, `B Level`, empty, empty |
| Serum 2 | Enc 17-24: `Filter 1 Freq`, `Filter 1 Res`, `Mod 1 Amount`, `Filter 1 Drive`, empty, empty, empty, `Main Vol` |
| Serum 2 | Fader 1-8: `Env 2 Attack`, `Env 2 Decay`, `Env 2 Sustain`, `Env 2 Release`, `Env 1 Attack`, `Env 1 Decay`, `Env 1 Sustain`, `Env 1 Release` |
| Serum 2 | Button 1-8: `Sub Enable`, `A Enable`, `B Enable`, `C Enable`, `Noise Enable`, `Clip Player Enable`, `Arp Enable`, empty |
| Omnisphere | Enc 1-8: `1 A Transpose Semitones`, empty, `1 B Transpose Semitones`, empty, `1 C Transpose Semitones`, empty, `1 D Transpose Semitones`, empty |
| Omnisphere | Enc 9-16: `1 A Shape`, `1 A Level`, `1 B Shape`, `1 B Level`, `1 C Shape`, `1 C Level`, `1 D Shape`, `1 D Level` |
| Omnisphere | Enc 17-24: `1 Global Filt Cut`, `1 Global Filt Res`, `1 Global Filt Env`, empty, empty, empty, empty, `Master Gain` |
| Omnisphere | Fader 1-8: `1 Global Flt Env Atk`, `1 Global Flt Env Dcy`, `1 Global Flt Env Sus`, `1 Global Flt Env Rls`, `1 Global Amp Env Atk`, `1 Global Amp Env Dcy`, `1 Global Amp Env Sus`, `1 Global Amp Env Rls` |
| Omnisphere | Button 1-8: `1 A Layer On`, `1 B Layer On`, `1 C Layer On`, `1 D Layer On`, `1 Bypass All Effects`, `1 Arp On`, empty, empty |
| Delay | `Dry/Wet`, `L 16th`, `Feedback` |
| ADPTR MetricAB | `Selected Track`, `Selected Cue`, `AB Switch` |

## 特殊パラメータ処理

通常のパラメータは Live の `connect_to(parameter)` に接続する。例外として、mixing モードのエンコーダに割り当たった特殊パラメータは通常接続せず、値入力をスクリプト側で処理する。フェーダに割り当たった場合は通常接続のまま。

相対入力の方向は `> 64` が正方向、`< 64` が負方向、`64` が無効。

### Saturn 2 Band 1 Style

- 対象デバイス: `name`、`class_display_name`、`class_name` のいずれかに `saturn 2` または `saturn2` を含むデバイス。
- 対象パラメータ名: `Band 1 Style`
- 許可スタイル: `Warm Tube`、`Warm Tape`、`Warm Transformer`
- `value_items` があれば各スタイル名から index を解決する。
- `value_items` がない場合は 28 項目として fallback し、index `2`, `6`, `22` を使う。
- 入力 2 ステップで 1 回だけ値を変更する。
- 現在値が許可外なら、回した方向にある最寄りの許可値へ移動する。

### 小さい離散値パラメータ

以下のいずれかなら小さい離散値パラメータとして扱う。

- `value_items` が 2-5 個。
- `is_quantized=True` かつ整数の `min` から `max` が 2-5 個。
- ADPTR MetricAB の `Selected Cue` は 4 個として fallback。
- ADPTR MetricAB の `AB Switch` は 2 個として fallback。

項目数 3 以上の場合は入力 2 ステップで 1 回、項目数 2 の場合は 1 ステップで 1 回変更する。方向に応じて隣の index へ進み、端で clamp する。

## LED と色

RGB LED 送信は SysEx `F0 00 20 29 02 15 01 53 <control_index> <r> <g> <b> F7`。`LedSender` は最後に送ったメッセージを control index ごとにキャッシュし、同じ RGB は再送しない。`force=True` のときは再送する。

エンコーダ LED の `control_index` は `message_identifier() - 64`。通常のボタン LED は `message_identifier()` を使う。

主な色仕様:

| 対象 | 色 |
| --- | --- |
| Device On Encoder 2 / 3 | yellow |
| Device On Encoder 4 / 5 / 7 | green |
| Device On Encoder 6 | red |
| Device On on 明るさ | `0.25` |
| Device On off 明るさ | `0.03` |
| Encoder 1 Loopcloud | yellow、明るさ `0.25` |
| Encoder 1 MetricAB | orange、明るさ `0.25` |
| Mode button active/inactive | white、`0.25` / `0.03` |
| Instrument button on/off | white、`0.25` / `0.03` |
| Track active/mute | track color、`0.25` / `0.03` |
| Solo track | blue |
| Mute modifier active/idle | yellow / dark yellow |
| Solo modifier active/idle | blue / idle blue |

通常パラメータ用エンコーダ LED:

- 正規化値が 0 なら white、明るさ `0.03`。
- 正規化値が MIDI 7bit 換算で 64 なら white、明るさ `0.175`。
- 正規化値が最大なら white、明るさ `0.38`。
- デバイスパラメータは 8 色 bin を使い、明るさ `0.25`。
- Track Volume は light blue、その他 mixer parameter は turquoise、明るさ `0.25`。
- Track Panning は表示文字列に `L` があれば dark blue、`R` があれば orange、それ以外は white half。

Transport / Recording skin:

- Play on/off: green / green half
- Arrangement Record on/off: red / red half
- Session Record on/off/transition: red / red half / red blink

## 更新、再接続、キャッシュ

- `Fixed_Assignments` と `Instrument_Assignments` は 0.1 秒周期で割り当てを更新する。
- トラックボタン LED も 0.1 秒周期で更新する。
- 選択トラック、対象デバイス、デバイス数、デバイス名、class 名、パラメータ名、min/max などの署名が変わった場合だけ再接続する。
- 同じデバイスのパラメータ列はキャッシュし、Live が同等の wrapper を返すだけなら不要な release/connect を避ける。
- モード非 active 化時:
  - `Fixed_Assignments` は全パラメータを release し、Encoder 1 と Device On エンコーダの手動 LED 状態を消す。
  - `Instrument_Assignments` は全パラメータを release し、instrument ボタン LED を off にする。
  - `Track_Buttons` は modifier LED を off にし、入力を無視する。

## ロケータ、再生、録音

- Track left ボタンで `song.jump_to_prev_cue()`。
- Track right ボタンで `song.jump_to_next_cue()`。
- 実行前に `can_jump_to_prev_cue` / `can_jump_to_next_cue` を見る。
- Play は `Launchkey_MK4.transport.TransportComponent` の `play_toggle_button` に渡す。
- Record は `View_Based_Recording.record_button` に渡す。

## MK2 移植時の注意

- 機能仕様として優先すべきものは、モード構造、fixed/instrument の割り当て表、トラックボタン対象解決、特殊パラメータ処理、カスタムパラメータ順序。
- LCXL3 固有の SysEx、RGB LED、ディスプレイターゲット、相対エンコーダモード設定は MK2 側の仕様に合わせて置き換える必要がある。
- MK2 で LCXL3 と同じ表示がない場合、`send_display` 呼び出しは no-op 化するか、別のフィードバックに置き換える。
- MK2 の LED が RGB でない場合でも、on/off、solo/mute、mode active/inactive の意味は維持する。
