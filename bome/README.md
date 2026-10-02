# Encoder 24でプリセット一覧を上下する

`LCXL3 Preset Navigation.bmtp`をBome MIDI Translator Pro 1.9以降で開く。新規プロジェクトとして使い、Bome Virtual Port 1を使用する。既存のデバイス選択設定は必要ない。

## 接続

Bomeを起動した状態で、Liveの「設定 → Link, Tempo & MIDI」にある該当Control Surfaceの行を次のように設定する。

| 項目 | 選択 |
|---|---|
| Control Surface | Launch Control XL 3 Mixing |
| Input | Bome MIDI Translator 1 |
| Output | Bome MIDI Translator 1 |

Liveの表示名に`Virtual In/Out`が付く場合は、同じ番号1のポートを選ぶ。InputはBomeからLiveへ、OutputはLiveからBomeへの経路になる。ハードウェアのDAWポートをInputとして併用しない（同じ入力を二重に受け取るため）。Bome仮想ポートのTrack/Sync/Remoteを追加で有効にする必要はない。

プロジェクトのMIDI Routerには次の2本を設定済み。機器名が異なる場合だけ、実際のLCXL3のDAWポートに変更する。

| Bome内のMIDI IN | Bome内のMIDI OUT |
|---|---|
| LCXL3 1 DAW Out | Bome Virtual Port 1（OUT） |
| Bome Virtual Port 1（IN） | LCXL3 1 DAW In |

番号1の自動エイリアスを使い、仮想ポートの表示名の違いに対応する。コントローラーからの操作・識別応答をLiveへ、LiveからのLED・表示・識別要求をコントローラーへ通す。Bomeは使用中ずっと起動しておく。

## macOSと音源の準備

「システム設定 → プライバシーとセキュリティ → アクセシビリティ」でBome MIDI Translator Proを許可する。Bomeから送るキーは現在フォーカスしているアプリのUIへ届く。

Liveを前面にし、Instrumentモードへ切り替える。Serum 2などのプリセット一覧をクリックし、物理キーボードの上下キーで選択が動くことを確認してからEncoder 24を回す。Bomeを開いた後に一度Liveへフォーカスを移すと前面判定が同期する。プロジェクトの初期状態はキー送信を無効にするため、フォーカス通知を受けるまで矢印を出さない。

## MIDI仕様

| 方向 | CH | CC | 値 | 意味 |
|---|---:|---:|---:|---|
| Script → Bome | 16 | 119 | 1 | 上キーを1回（BF 77 01） |
| Script → Bome | 16 | 119 | 2 | 下キーを1回（BF 77 02） |
| Script → Bome | 16 | 119 | 0 | 前面状態の問い合わせ（BF 77 00） |
| Bome → Script | 16 | 118 | 1 | Liveが前面（BF 76 01） |
| Bome → Script | 16 | 118 | 0 | Live以外が前面（BF 76 00） |

CC119は常時Swallowし、コントローラーへ送らない。キー変換はBome Virtual In 1だけを受け、`ga=1`（Liveが前面）のときだけ実行する。Application Focusの対象は`Ableton Live 12 Suite.app`。別エディションのLiveを使う場合は2つのフォーカスTranslatorの対象アプリを変更する。

Keyboard出力はPhysical Keysの上／下矢印について、押下と解放を1組送る。修飾キー、自動リピート、送信タイマー、遅延送信は使用しない。

フォーカス変化はCC118でScriptへ返すので、回転の入力数や押下間隔の状態もリセットされる。Script再接続時にはCC119値0で現在の状態を問い合わせる。RecordボタンはCH1なので、CH16のCC118とは競合しない。

## 感度の調整と確認

`Launch_Control_XL_3_Mixing/keyboard_navigation.py`の設定を変更し、Live再起動後に確認する。

| 設定 | 初期値 |
|---|---:|
| REPEAT_INPUTS_PER_PRESS | 1入力 |
| MIN_PRESS_INTERVAL | 0.0秒 |
| GESTURE_GAP | 0.25秒 |

- 小さな左回転で上1回、右回転で下1回。加速入力もMIDIメッセージ1件につき1回。
- ゆっくり／速く連続回転し、動きすぎる場合は入力数または最小間隔を増やす。
- 方向反転・回転停止後の再開は即時1回。止めた後の自動連打はない。
- Shift中の回転／タッチは表示だけ。他アプリが前面なら矢印を送らない。
- Mixingへ戻るとEncoder 24はPanへ復帰する。

BomeのLog WindowでMIDI IN/OUTとIncoming/Outgoingを有効にすると、Port 1でのCC119受信、上下キー出力、CC118による前面通知を確認できる。LiveのMIDI受信ランプだけではキー送信の成否は判定できない。

## 参考

- [Bome公式マニュアル](https://www.bome.com/bome/downloads/manuals/miditranslator_manual.pdf): p.17 仮想ポート、p.41 Swallow、p.50–51 Keystroke、p.87 Application Focus。
- [Novation公式DAWモード仕様](https://userguides.novationmusic.com/hc/en-gb/articles/27840466544402-Launch-Control-XL-3-programmer-s-DAW-mode): CCチャンネル、相対入力、表示SysEx。
