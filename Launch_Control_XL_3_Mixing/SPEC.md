# Launch_Control_XL_3_Mixing 仕様

この文書は、現行の `Launch_Control_XL_3_Mixing` とできる限り同一の設定を持つ Launch Control XL MK2 用 Remote MIDI Script を作るための仕様メモである。記述はこのリポジトリの現在の作業ツリーを基準にしている。

## 概要

- Ableton Live 12 系の `ableton.v3.control_surface.ControlSurface` ベースの Remote MIDI Script。
- 起動時の既定モードは `mixing`。
- `mixing` モードでは、固定パラメータ割り当てとトラック選択/solo/mute ボタンを有効化する。
- `instrument` モードでは、選択トラック上の 3 番目のデバイスをエンコーダ1〜23、8フェーダ、16ボタンへ割り当てる。Encoder 24は全音源共通の上下キー操作とする。
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
- 接続時にタッチ出力を有効化: `B6 47 7F`（チャンネル7、CC71、127）。切断時は `B6 47 00` で無効化する。
- 切断時 SysEx: `F0 00 20 29 02 15 02 00 F7`
- 識別後、相対エンコーダモード設定として以下の生 MIDI を送信する:
  - `(182, 69, 127)`
  - `(182, 72, 127)`
  - `(182, 73, 127)`

## MIDI 要素

CC は 10 進数表記。`Shift_Button` は `CHANNEL_DAW_MODE = 6`、フェーダとエンコーダの値入力は `CHANNEL_ENCODER_LED = 15`、エンコーダタッチは `CHANNEL_TOUCH = 14` を使う。その他のボタンは `ElementsBase.add_button` の既定チャンネルに従う（内部チャンネル番号は0始まり）。

| 要素 | CC / 範囲 | 内部名 | 備考 |
| --- | --- | --- | --- |
| Shift | 63 | `Shift_Button` | 押下中のエンコーダ／フェーダ操作はアサイン表示のみ |
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
| Encoder touch 1-24 | 77-100 | `Encoder_1_Touch` ... `24` | チャンネル15、127がtouch on、0がtouch off。値変更の入力とは別に受ける |

表示ターゲットは LCXL3 のディスプレイ向けで、MK2 では同一再現できない可能性が高い。

| 表示対象 | Target ID |
| --- | --- |
| Static（待機画面） | 53 |
| Temp | 54 |
| Fader 1-8 | 5-12 |
| Upper encoder 1-16 | 13-28 |
| Lower encoder 17-24 | 29-36 |

表示は常に 3 行構成、1 行 16 文字まで。`Config.three_line = 98`、`show_immediately=False` を使う。操作時は `trigger=True`、エンコーダの表示内容を事前登録・定期更新する場合は `trigger=False` とし、更新だけで画面を切り替えない。同一内容の事前登録は `DisplayTargetElement` のキャッシュにより通信されない。

## モード

| 操作 | 結果 |
| --- | --- |
| Page up | `mixing` モードを選択 |
| Page down | `instrument` モードを選択 |

`mixing` モードでは `Fixed_Assignments` と `Track_Buttons` を active、`Instrument_Assignments` を inactive にする。`instrument` モードでは逆に `Instrument_Assignments` のみ active にする。

Page up（`mixing`）の LED は黄色、Page down（`instrument`）の LED は青。選択中は明るさ `0.25`、非選択は `0.03` とし、他のボタンと同じ輝度係数を使う。

## 待機画面と無操作ロック

- 起動時は従来どおりMixingで操作可能。モードとロック状態はLive再起動をまたいで保存しない。
- 操作可能な待機画面は `MIXING` または `INSTRUMENT` の1語だけ。操作中は既存のパラメータ表示を出し、本体の一時表示が終了するとモード名へ戻る。
- エンコーダ、フェーダ、16ボタン、Page Up／Downの最後の有効な操作から180秒でロックする。Shift＋回転のtouch onもエンコーダの確認操作として扱う。
- 無操作時間は0.1秒周期で確認する。中立入力64、touch off、ボタン解放、内部更新、表示／LED送信、Live側の再生や値変化では延長しない。
- ロック中の液晶は `LOCKED` の1語だけ。全24エンコーダ／8フェーダの保存済み表示も更新し、Shift＋回転など本体だけで表示する操作でも維持する。
- ロック中は24エンコーダ・8フェーダ・16ボタンとSolo／Mute modifierを操作禁止とする。Device On、MetricAB、特殊／追加パラメータ、Encoder 24のキー送信も抑止する。再生・録音・ロケータ移動は操作可能。
- Page UpでMixingを選択して解除、Page DownでInstrumentを選択して解除。同じモードの再押下も解除となり、無操作時間をリセットする。ロック中のその他の入力では解除しない。
- ロックはShiftとは独立する。Shiftを離してもロック中ならLiveへのパラメータ接続を復帰しない。Shiftを押したまま解除した場合もShiftを離すまでは値操作しない。
- 遮断した入力は蓄積・再適用しない。解除操作自体では値を変更せず、解除後の新しい入力から最新の割り当てへ操作する。フェーダは既存の絶対値マッピングとLiveのtakeover設定を維持する。
- ロック中の操作対象LEDは元の色を保ち、通常の約1/5へ減光する。未割り当ては消灯のまま。選択トラックは点滅の点灯側の色で固定表示する。
- ロック中のPage Up／Downは両方とも同じ暗いグレー `(8, 8, 8)` で固定点灯し、点滅しない。解除後は通常の黄／青とトラック点滅へ戻す。
- 定期更新や外部の値変化でも減光を維持する。モード／ロック変更前に遅延送信された古いLED・表示は破棄し、現在の状態を上書きしない。再生／録音などのフィードバックは破棄しない。

`safety.py`の定数で操作感を調整する。

| 定数 | 初期値 | 意味 |
| --- | --- | --- |
| `INACTIVITY_LOCK_SECONDS` | `180.0` | 無操作ロック時間（秒） |
| `LOCKED_LED_FACTOR` | `0.2` | 通常のRGB出力に対するロック中の輝度係数 |
| `LOCKED_MODE_RGB` | `(8, 8, 8)` | ロック中の両モードボタンの暗いグレー |

減光・グレーの判別しやすさと解除後のフェーダtakeoverは実機で確認する。

## Shiftによるアサイン確認

- 操作可能な状態ではMixing／Instrumentの両モードで、Shiftを押しながらエンコーダ／フェーダを動かすと、通常と同じ「デバイス名またはトラック名・パラメータ名・現在値」の3行を表示する。割り当て先がない、または無効な場合は「操作子名・Unassigned・空行」を表示する。
- 全24エンコーダと8フェーダの表示内容は、操作を待たずに割り当て時点で本体へ登録する。0.1秒周期の割り当て更新とモード切替でも名前・現在値を更新するため、通常回転を一度もしていないエンコーダも本体のShift＋回転表示を利用できる。値CC・タッチCCの受信を初回登録の条件にしない。
- 本体を再識別したときは、アクティブなモードの表示コマンドの送信キャッシュを消して再登録する。接続前の登録が受理されなかった場合や、本体側の表示内容だけが消えた場合にも備える。
- Shift中の操作では値を書き換えない。Device On、MetricABのサブモード／AB Switch、Saturnなどの特殊パラメータ操作も抑止する。Encoder 1は現在のモード名を表示するだけで、エンコーダの中立入力 `64` は引き続き無視する。
- フェーダをShift中に上端／下端から中央へ戻しても、パラメータ値は維持される。Shift解除そのものは値を変更せず、次の操作から既存の絶対値マッピングへ戻る。独自の相対制御やオフセット補正は行わず、Liveの既存takeover設定を維持する。
- Value Scalingでは物理位置とパラメータ値の差を徐々に縮める。一定の移動量をそのまま現在値へ加減する方式とは異なる。Shift解除後の再接続直後の追従は実機で確認する。
- トラックボタン、Instrumentのパラメータボタン、モード切替、ロケータ、再生・録音ボタンはShift中も従来どおり動作する。エンコーダLEDは割り当て先の色・現在値・Pan方向を維持する。
- `Control_Router` がShiftを一度受け、両割り当てコンポーネントの `set_shift_pressed(bool)` に配布する。非アクティブなモードにも状態を保持する。
- Shift＋回転は本体のタッチ操作に相当する。通常の相対値CCを受ける前提にせず、チャンネル15のエンコーダタッチ入力を `preview_encoder(name)` へ送って現在のアサインを表示する。Shiftなしのタッチとtouch offは無視し、タッチ値127をパラメータ操作値として扱わない。
- Shift中は表示用の論理アサインを保持したままLiveへのMIDIパラメータ接続を解除する。定期更新、トラック変更、モード変更でも再接続せず、解除時に最新のアサインへ復帰する。特殊パラメータの入力蓄積はShiftの押下／解除でリセットし、押下中の操作は蓄積しない。

参考: [Ableton LiveのTakeover Mode](https://www.ableton.com/en/manual/midi-and-key-remote-control/#takeover-mode)

タッチ出力と表示の仕様: [Novation DAW mode](https://userguides.novationmusic.com/hc/en-gb/articles/27840466544402-Launch-Control-XL-3-programmer-s-DAW-mode)

## Mixing モードの固定割り当て

選択トラックは `song.view.selected_track`。`Loopcloud` トラックは、Live Set 内で名前が完全一致する最初のトラックを使う。デバイス番号は 1 始まり、デバイスパラメータ番号も 1 始まり。ただしデバイスパラメータ番号は `Device On` と空名パラメータを除いた後の番号で、カスタムパラメータ順序があればそれを適用した後の番号になる。

### Loopcloud サブモード

既定サブモード。未記載の `encoder_10`、`encoder_18`、`fader_2` は mixing モードでは割り当てなし。

| 物理操作子 | 割り当て |
| --- | --- |
| Encoder 1 | 左でMetricAB A側＋Loopcloud割り当て、右でMetricAB B側＋MetricAB割り当て。パラメータ接続なし |
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

Encoder 1はLoopcloudトラックのsoloを操作しない。既存のsolo状態にかかわらず、回転方向だけでサブモードとMetricABのA/Bを決める。表示は `Loopcloud` または `MetricAB` とし、soloによる別表示や切替の中間段階は設けない。

### MetricAB サブモード

Encoder 1 の入力値 `64` は無視する。現在の状態ごとの動作は以下。

| 現在の状態 | 左方向 | 右方向 |
| --- | --- | --- |
| `metric_ab` | `loopcloud` へ戻し、MetricAB の AB Switch を最小値にする | `metric_ab` のまま、MetricAB の AB Switch を最大値にする |
| `loopcloud` | `loopcloud` のまま、MetricAB の AB Switch を最小値にする | `metric_ab` へ切り替え、MetricAB の AB Switch を最大値にする |

AB Switchの最小値がA側、最大値がB側。同方向の再入力でも指定側へ設定し、外部からA/Bが変更されていても回転方向と一致させる。Shift中・中立入力64・非アクティブ時はサブモードとA/Bを変更しない。

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

Solo/Mute modifier はラッチ式。同じ modifier をもう一度押すと Select へ戻る。Solo から Mute を押すと Mute へ切り替わる。Shift はエンコーダ／フェーダのアサイン確認に使い、トラックボタン動作は変えない。

トラックボタン LED:

- solo 中のトラックは常に blue。
- solo でないトラックは Live のトラックカラーを RGB 化する。
- mute でなければ明るさ `0.25`、mute なら `0.03`。
- 選択トラックは 0.5 秒周期で「現在色」と off を点滅する。
- Solo modifier LED は active 時 blue、idle 時 very dim blue。
- Mute modifier LED は active 時 yellow、idle 時 dark yellow。

## Instrument モード

Instrument モードのパラメータ操作は選択トラックの3番目のデバイス、つまり`track.devices[2]`を対象にする。対象デバイスが存在しない場合は未割り当て。Encoder 24のキー操作はデバイスの有無にかかわらず有効。

対象デバイスのパラメータは、`Device On` と空名パラメータを除外した後、カスタムパラメータ順序を適用する。番号は 1 始まり。

| 物理操作子 | 割り当て |
| --- | --- |
| Encoder 1-23 | Parameter 1-23 |
| Encoder 24 | プリセット一覧の上下キー（Parameter 24は使用しない） |
| Fader 1-8 | Parameter 25-32 |
| Track Button 1-16 | Parameter 33-48 |

Instrument ボタンは押下時のみ反応する。対象パラメータの現在値が範囲の中点より大きければ最小値へ、それ以外なら最大値へトグルする。LED は白系で、on 相当なら明るさ `0.25`、off 相当なら `0.03`、未割り当てなら off。

Instrument モードのパラメータ操作時の表示は `対象デバイス名 / パラメータ名 / 値`。

### Encoder 24の上下キー

CH16 / CC100の相対入力を、64未満なら上キー、64超なら下キー、64なら無操作へ変換する。最小回転も加速値も1入力として扱う。Instrument全体で専用に予約し、`custom_parameter_order.py`での定義や選択中デバイスの制限は設けない。Mixingでは従来のPanへ戻る。フェーダー25番、ボタン33番からのパラメータ配置を維持する。

表示は`Keyboard / Preset Up-Down / UpまたはDown`、待機時は3行目を空にする。LEDは青25%。Shift中とタッチ入力は表示だけでキーを送らない。

`keyboard_navigation.py`冒頭の定数で連続回転を調整する。

| 設定 | 初期値 | 意味 |
| --- | --- | --- |
| `REPEAT_INPUTS_PER_PRESS` | `1` | 連続時の1押下に必要な入力数 |
| `MIN_PRESS_INTERVAL` | `0.0`秒 | 連続時の最小押下間隔 |
| `GESTURE_GAP` | `0.25`秒 | 無入力で一連の回転を区切る時間 |

回し始めと方向反転時は即時に1回の送信を試みる。無入力からの自動連打は行わない。Shift、モード切替、前面アプリ変更、ポート変更、切断で蓄積をリセットする。

macOS標準の`/usr/bin/osascript -l JavaScript`をサーフェス起動時に1本だけ起動し、JXAのObjective-C bridgeからCoreGraphicsを呼ぶ。キーコードは上126／下125、修飾キーなしの押下・解放を1組、LiveのPIDへ送信する。送信直前にLiveが前面か確認し、前面を奪わない。Live終了時は子プロセスも終了する。

入力の有効期限は受信から50ms、未完了要求は最大1件。処理が追いつかない入力は破棄し、回転停止後に遅れて再生しない。したがって高速回転時にすべての入力が押下になる保証はない。Liveの入力コールバックで応答や子プロセスの終了を待たない。

利用時はプラグインのプリセット一覧をクリックしてフォーカスを置く。前面Live内でどのUIがキーを受けるかは現在のフォーカスに従い、一覧以外へフォーカスを移した場合はそのUIが上下キーを受ける。音源のウインドウ識別やパラメータ変更の検出は行わない。

Liveの入力・出力はLCXL3のDAWポートへ直接接続する。Bomeや専用出力CCは不要。macOS「プライバシーとセキュリティ → アクセシビリティ」でLiveのキー送信権限を確認する。初期化・通信に失敗した場合はキー機能だけを停止し、`Log.txt`の`LCXL3 keyboard navigation:`へ原因を記録する。権限不足時は送信を抑止し、許可を再確認する。詳しい確認手順は`diagnostics/README.md`を参照。

## カスタムパラメータ順序

カスタム順序は `mixing` と `instrument` の両方で使う。

- キーはデバイスの `name`、`class_name`、`class_display_name` のいずれかに一致すれば適用する。
- 比較時は空白正規化、小文字化、末尾の数字削除を行う。例: `Serum 2` は `serum` として扱う。
- `instrumentvector` と `wavetable`、`instrumentmeld` と `meld`、`hybrid` と `reverb` は相互 alias。
- `None` または `SKIP` は空スロット。
- `{"Parameter": {"occurrence": 2}}` のように同名パラメータの何番目かを指定できる。
- instrument モードでは `{"Parameter": {"invert_direction": True}}` でエンコーダの値方向を反転し、`{"Parameter": {"invert_led": True}}` でボタンの点灯条件を反転できる。反転LEDのオフ状態も他のボタンと同じ暗い点灯とする。
- `CUSTOM_PARAMETER_APPEND_REST = False` なので、カスタム順序にない残りパラメータは末尾へ追加しない。未指定スロットは未割り当て。

現在定義されているカスタム順序:

| デバイス | スロット |
| --- | --- |
| Serum 2 | Enc 1-8: `A Octave`, `A Unison`, `A Uni Detune`, `B Octave`, `B Unison`, `B Uni Detune`, empty, empty |
| Serum 2 | Enc 9-16: `A WT Pos`, `A Warp`, `A Level`, `B WT Pos`, `B Warp`, `B Level`, empty, empty |
| Serum 2 | Enc 17-24: `Filter 1 Freq`, `Filter 1 Res`, `Mod 1 Amount`, `Filter 1 Drive`, empty, empty, `Main Vol`, 上下キー |
| Serum 2 | Fader 1-8: `Env 2 Attack`, `Env 2 Decay`, `Env 2 Sustain`, `Env 2 Release`, `Env 1 Attack`, `Env 1 Decay`, `Env 1 Sustain`, `Env 1 Release` |
| Serum 2 | Button 1-8: `Sub Enable`, `A Enable`, `B Enable`, `C Enable`, `Noise Enable`, `Clip Player Enable`, `Arp Enable`, empty |
| Omnisphere | Enc 1-8: `1 A Transpose Semitones`, `1 A Level`, `1 B Transpose Semitones`, `1 B Level`, `1 C Transpose Semitones`, `1 C Level`, `1 D Transpose Semitones`, `1 D Level` |
| Omnisphere | Enc 9-16: `1 A Shape`, `1 A Symmetry`, `1 B Shape`, `1 B Symmetry`, `1 C Shape`, `1 C Symmetry`, `1 D Shape`, `1 D Symmetry` |
| Omnisphere | Enc 17-24: `1 Global Filt Cut`, `1 Global Filt Res`, `1 Global Filt Env`, `1 Global Flt Env Vel`, `1 Global Ambi Amount`, `1 A Tune Octave`, `Master Gain`, 上下キー |
| Omnisphere | Fader 1-8: `1 Global Flt Env Atk`, `1 Global Flt Env Dcy`, `1 Global Flt Env Sus`, `1 Global Flt Env Rls`, `1 Global Amp Env Atk`, `1 Global Amp Env Dcy`, `1 Global Amp Env Sus`, `1 Global Amp Env Rls` |
| Omnisphere | Button 1-8: `1 A Layer On`, `1 B Layer On`, `1 C Layer On`, `1 D Layer On`, `1 Bypass All Effects`, `1 Arp On`, empty, empty |
| Diva | Enc 1-16: ベースはEnc 8のFeedback以外は空。OSCモデル別のオーバーライドで割り当てる（下記参照） |
| Diva | Enc 17-24: `Frequency`, `Resonance`, `Freq Mod Depth`, `KeyFollow`, `Mode`（5段階）, `DepthMod Dpt1`（同名2つを反転操作）, `Output`, 上下キー |
| Diva | Fader 1-4: Filter envelope `Attack`, `Decay`, `Sustain`, `Release`（各 `occurrence: 1`）; Fader 5-8: Amp envelopeの同4項目（各 `occurrence: 2`） |
| Diva | Button 1-8: `OnOff`, `Active #FX1`, `Active #FX2`, empty, empty, empty, empty, empty |
| Delay | `Dry/Wet`, `L 16th`, `Feedback` |
| ADPTR MetricAB | `Selected Track`, `Selected Cue`, `AB Switch` |

Omnisphere の `1 A/B/C/D Transpose Semitones` と `1 A Tune Octave` は値方向を反転し、右回しで音程が上がる。`1 Bypass All Effects` はバイパス中に暗く点灯、エフェクト有効時に明るく点灯する。ボタン押下による min/max のトグル動作と、画面に表示するパラメータ値は変更しない。

方向反転または段階値を設定したエンコーダは Live の通常接続を解除して手動で値を更新する。Shift 中は表示のみ更新する。LED は実際のパラメータ値に追従する。通常方向では右回しが内部値の増加、`invert_direction` を指定した場合は減少になる。

`1 A Tune Octave` は `discrete_count: 5` を設定し、`-2, -1, 0, +1, +2` の5段階として扱う。

- Saturn 2 と同じ正規化インデックス変換を使い、raw範囲を5値（最小値、25%、50%、75%、最大値）に対応させる。現在値に最も近いインデックスから隣の1段階へ進む。
- 同方向の入力2回で1段階進む。加速したCCでも一度に複数段階を飛ばさない。入力64は無効。方向を変えると入力の蓄積をリセットする。
- 両端では止まる。割り当て時やShift操作だけでは音程を変更しない。Shift切り替え、割り当て変更・解除時は蓄積をリセットする。
- 値更新は入力時のみ行い、表示値の探索や `str_for_value(raw)`、`value_items` の取得は行わない。

`1 A/B/C/D Transpose Semitones` は `discrete_values` で次の実測内部値を指定し、同方向の入力2回で隣の12半音へ進める。加速入力・方向変更・Shift・割り当て変更時の扱いは Tune Octave と共通。現在の内部値に最も近い候補から隣へ進み、両端では止まる。割り当て時や周期更新では音程を書き換えない。

| Omnisphere本体の音程 | 内部値 | 観測時のLive Configure表示 | 採取元 |
| --- | --- | --- | --- |
| -24 | 0.984252 | -25 semis | A |
| -12 | 0.7407507 | -13 semis | B |
| 0 | 0.5054741 | -1 semis | C |
| +12 | 0.2519685 | 12 semis | D |
| +24 | 0.0 | 24 semis | A |

2026-09-27にOmnisphere本体の表示をユーザーが確認した値。内部値はLiveのアクセシビリティ表示から採取した小数であり、音程範囲の境界・中心ではない。特に -24 は内部値の最大値1.0と同一視しない。この値を使う検証版はユーザーによる実機確認でOKとなった。音程の確認にはLive ConfigureではなくOmnisphere本体を用いる。

候補は内部値の昇順で保持し、入力時に直接代入する。`str_for_value(raw)` や `value_items` による探索は行わない。設定値が昇順でない・範囲外・2個未満の場合は値を変更しない。

`discrete_values` / `discrete_count` のない反転エンコーダは相対CCの差分 `64 - value` を使う。連続値は範囲の `1/127`、量子化された値は `value_items` の1項目（項目がない場合は1）を単位に動かし、上下限で止める。

DivaはLiveのConfigureでフィルターエンベロープの組を先、アンプエンベロープの組を後に並べた状態を前提とする。`occurrence` は同名パラメータのLive内の出現順であり、DivaのENV番号や役割を自動判別する指定ではない。同名パラメータのConfigure順を入れ替える場合は、この指定も合わせて変更する。

`Tune1`（Encoder 1）と `Tune2`（Encoder 5、DCO以外）は `discrete_values: (0.1, 0.3, 0.5, 0.7, 0.9)` で -24 / -12 / 0 / +12 / +24 半音に切り替える。Triple VCOのTune3（Encoder 9）も同じ5段階を使う。2026-09-27に別プロセスのDiva VST3 1.4.8（revision 16519）で、Tune1（ParamID 86）とTune2（87）の変換API・設定後の読み戻し・表示文字列を確認した。両パラメータの正規化値0〜1は -30〜+30 半音に対応する。Liveの画面・アクセシビリティ表示の半音値は、そのまま代入する内部値として扱わない。Live Python API自体の値域は、この独立ホスト検証では未測定。

右回しで上昇、左回しで下降し、同方向のMIDI入力2回で現在値に最も近い候補から隣の1段階へ進む。加速入力でも1段階とし、±24で止める。Shift・方向変更・割り当て変更時の蓄積リセットはOmnisphereと共通。値は入力時に上記の固定値を直接代入し、表示値の探索、割り当て時や周期更新でのスナップは行わない。

### モデルなどの選択値による割り当て変更

`CUSTOM_DEVICE_PARAMETER_ORDER` を基本の並びとし、`CUSTOM_DEVICE_PARAMETER_OVERRIDES` に条件と操作子ごとの上書きを記述する。DivaのEncoder 1〜16は共通のEncoder 8（Feedback）を除き、ベースを `None` にしてOSCモデルごとに割り当てる。

| OSCモデル | Encoder 1〜7 | Encoder 9〜16 |
| --- | --- | --- |
| Triple VCO | Tune1, Shape1, Volume1, 空, Tune2, Shape2, Volume2 | Tune3, Shape3, Volume3, 空, 空, 空, 空, NoiseVol |
| Dual VCO | Tune1, PulseWidth, FM, 空, Tune2, Sync2, OscMix | Triangle1On, Saw1On, Pwm1On, Noise1On, Triangle2On, Saw2On, Pulse2On, Sine2On |
| DCO | Tune1, SawShape, PulseShape, SuboscShape, 空, 空, 空 | PulseWidth, 空, Volume3, NoiseVol, 空, 空, 空, 空 |
| Dual VCO Eco | Tune1, EcoWave1, Volume1, 空, Tune2, EcoWave2, Volume2 | PulseWidth, 空, 空, 空, 空, 空, 空, 空 |
| Digital | Tune1, DigitalType1, FM, 空, Tune2, DigitalType2, OscMix | PulseWidth, DigitalShape2, 空, 空, DigitalShape3, DigitalShape4, 空, 空 |
| 未定義のモデル／Model未表出 | すべて空 | すべて空 |

上表はユーザーが編集した5モデルの設定を保持したもの。Encoder 8・17〜23・フェーダー・ボタンは共通のベース設定を使い、Encoder 24は上下キーに予約する。モデル別設定で `encoder_22` を省略すると共通のDepthMod操作を継承し、明示的に `None` を指定するとそのモデルでは未割り当てになる。

EcoWave1 / EcoWave2（Encoder 2 / 6）には `discrete_count: 4` を指定し、同方向のMIDI入力2回で1〜4の隣の段階へ進む。内部値の最小値・1/3・2/3・最大値の4点を使い、加速した入力も1回として数える。方向変更・Shift・モデル切替による再割り当て時は入力蓄積をリセットし、両端で止める。Triple VCOのShape1 / Shape2 / Shape3は通常の連続操作とする。

設定例（全体の配置は `custom_parameter_order.py` を参照）:

```python
CUSTOM_DEVICE_PARAMETER_OVERRIDES = {
    "Diva": (
        {
            "when": {"parameter": "Model", "occurrence": 1, "normalized_value": DIVA_TRIPLE_VCO},
            "assignments": {"encoder_2": "Shape1", "encoder_6": "Shape2"},
        },
        {
            "when": {"parameter": "Model", "occurrence": 1, "normalized_value": DIVA_DUAL_VCO_ECO},
            "assignments": {
                "encoder_2": {"EcoWave1": {"discrete_count": 4}},
                "encoder_6": {"EcoWave2": {"discrete_count": 4}},
            },
        },
    ),
}
```

- `when.parameter` は条件に使うConfigure上のパラメータ名。大文字小文字・空白を正規化して完全一致で検索する。`occurrence` は同名の何番目かを1から指定し、省略時は1。現在のDivaではフィルターのModelをConfigureから除き、OSCのModelだけを表出する。
- `normalized_value` は `(parameter.value - parameter.min) / (parameter.max - parameter.min)` の期待値。画面の数値ではない。誤差 `1e-6` 以内を一致とする。Diva OSC Modelは独立VST3ホストでTriple VCO=0、Dual VCO=0.25、DCO=0.5、Dual VCO Eco=0.75、Digital=1と確認済み。
- `assignments`のキーは`encoder_1`〜`encoder_23`（`encoder_24`は上下キー予約のため設定を使用しない）、`fader_1`〜`fader_8`、`button_1`〜`button_16`。値には基本順と同じパラメータ名、`occurrence` や段階値などのオプション付き辞書、未割り当ての `None` / `"SKIP"` が使える。複数の条件が成立すると、後のルールが同じ操作子の指定を上書きする。
- 判定対象がない・無効・読取不可なら、そのルールは不成立。成立したルールの割り当て先が未表出なら、その操作子は未割り当てとする。DivaではModelに加えEcoWave1とEcoWave2をConfigureに表出させる。
- パラメータ一覧と判定対象の参照をキャッシュし、既存の0.1秒更新で判定対象の現在値だけを読む。同一対象を使う複数ルールでも1更新に1回とする。成立するルールが変わったときだけ並びを再構成し、変わった操作子だけ接続し直す。表示やLEDも新しいパラメータへ追従し、Shift中は接続せず表示のみ更新する。モデル切替時にパラメータ値を書き換えたり、変更のないTuneの2入力蓄積をリセットしたりしない。
- `str_for_value` / `value_items` や表示値の探索は使わない。選択トラック・音源の変更、インストゥルメントモードへの入り直しでキャッシュを作り直す。同じ音源のConfigure項目を追加・削除した場合も、モードへ入り直すと新しい一覧を取り込む。

### 複数パラメータの相対操作と左回し時の固定値設定

Divaの共通Encoder 22は、Configureで1つ目と2つ目の `DepthMod Dpt1` を反転操作する。それぞれの現在値から、右回しでDepthを下げ、左回しでDepthを上げる。左回しでは同時に、Configureで1つ目と2つ目の `DepthMod Src1` を両方 `none` にする。表示とLEDは1つ目のDepthを代表として使う。

```python
{"DepthMod Dpt1": {
    "occurrence": 1,
    "invert_direction": True,
    "relative_targets": (
        {"parameter": "DepthMod Dpt1", "occurrence": 2, "invert_direction": True},
    ),
    "on_left": (
        {"parameter": "DepthMod Src1", "occurrence": 1, "normalized_value": 0.0},
        {"parameter": "DepthMod Src1", "occurrence": 2, "normalized_value": 0.0},
    ),
}}
```

- `on_left` の方向は `invert_direction` 適用前の物理入力（CC < 64）で判定する。Depthが上限でもSource解除は行う。右回しはSourceを変更しない。
- `on_left` は従来の辞書1つ、または辞書のtuple/listを指定できる。各Sourceを独立に処理し、1つが欠落・無効でも残りを設定する。
- `relative_targets` は同じ入力で相対操作する追加対象の辞書、または辞書のtuple/list。対象ごとに `invert_direction` を指定する。各パラメータの値域に対する1/127刻みでそれぞれの現在値から動かし、上下限を個別に適用する。主対象の値をコピーせず、主対象の `discrete_values` / `discrete_count` や2入力蓄積も継承しない。量子化パラメータは通常の手動相対操作と同じ項目単位になる。同じ追加対象や主対象の重複指定で2回動かさない。
- 追加対象の名前は大文字小文字・空白を正規化した完全一致で検索し、`occurrence` はConfigure順の同名パラメータを1から数える。省略時は1。`normalized_value` は0〜1で指定し、対象の実際のmin/maxへ変換する。
- Diva VST3 1.4.8の変換APIで、LFO1/2の `DepthMod Src1`（ParamID 60/70）とも `none` が正規化値0であることを確認した。LFO番号とConfigureの出現順は別物なので、操作対象はConfigure順で指定する。
- 設定先が既に目標値なら再書込みしない。割り当て・周期更新・Shiftプレビュー・CC64・非アクティブ時にも書き込まない。主パラメータが未割当・無効なら追加設定も実行しない。追加先が欠落・無効でも主パラメータや他の追加先は通常どおり動く。
- `on_left` / `relative_targets` を持つエンコーダも通常接続を解除して手動操作する。追加先の参照は割り当て変更時にキャッシュする。入力時に最新のトラック／モデルへ割り当てを揃えてから、追加設定と主パラメータ操作を実行する。

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
| Page up / Mixing active/inactive | yellow、`0.25` / `0.03` |
| Page down / Instrument active/inactive | blue、`0.25` / `0.03` |
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
