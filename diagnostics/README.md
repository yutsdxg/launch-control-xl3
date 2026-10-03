# Live内PythonのJXA起動診断

Issue #23の最初の検証に使う一時的なControl Surfaceです。キーイベントもMIDIも送りません。Live内PythonからmacOS標準の`osascript`を起動し、非ブロッキングのパイプで文字列を往復させ、標準入力を閉じると子プロセスが終了することを確認します。

## 実行

1. `LCXL3_JXA_Probe`フォルダーをLiveが読み込むMIDI Remote Scriptsフォルダーへ配置します。同じフォルダーへ、本体の`jxa_keyboard.py`と`keyboard_worker.js`もコピーします。
2. 作業中のLive Setを保存したうえでLiveを再起動します。新しいControl Surfaceの一覧への反映に再起動が必要な場合があります。
3. LiveのMIDI設定の空いている行に`LCXL3 JXA Probe`を選びます。入力と出力はどちらも`None`です。
4. Liveの`Log.txt`で、次の行を確認します。

```text
LCXL3_JXA_PROBE PASS subprocess + nonblocking pipes + echo + EOF exit
LCXL3_JXA_PROBE PASS production worker + reaper thread; frontmost=True allowed=True
```

Pythonバージョン、各モジュールのimport結果、子PID、終了結果もログへ記録します。続けて本体と同じ送信クラスを`diagnostic=True`で起動し、終了処理用スレッドとworkerの初期化を確認します。`frontmost`と`allowed`は実際の前面状態と権限によって変わります。`allowed=False`でも起動診断自体は成功しますが、キー送信には権限の確認が必要です。失敗や5秒のタイムアウトの場合は`FAIL`を記録します。診断終了後はその行のControl Surfaceを`None`へ戻します。

## 判定の範囲

この診断の成功は、Liveからの外部プロセス起動と通信経路の成立を示します。実際のキー受信、Serum 2での操作感は別に検証します。通常のPythonから同じ診断が成功しても、Live内での成功として扱いません。スクリプトを修正した場合、サーフェスの選び直しだけではPythonモジュールが更新されないため、Liveを再起動します。

本診断はLiveの入出力ポートや既存のコントローラー設定を変更しません。導入済みのBome版を新方式に切り替える作業とは分けて実施します。

## 確認記録（2026-10-03）

Live 12.4.6 / 内蔵Python 3.11.6で、モジュールimport、JXA echo往復、EOF正常終了、本体workerの診断起動、reaperスレッドの起動が成功しました。Live前面時に`frontmost=True`、キー送信権限が未許可の状態で`allowed=False`を確認しています。この時点では実キー受信と物理エンコーダの操作感は未確認です。

本体の自動テストは`python3 -B -m unittest discover -s tests`で実行します。最小・中立・加速入力、連続・反転、Shift、他アプリ前面、モード／ポート変更、Pan復帰、期限切れ、通信異常と終了処理を検証します。
