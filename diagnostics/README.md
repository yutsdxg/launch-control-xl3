# Live内PythonのJXA起動診断

Issue #23の最初の検証に使う一時的なControl Surfaceです。キーイベントもMIDIも送りません。Live内PythonからmacOS標準の`osascript`を起動し、非ブロッキングのパイプで文字列を往復させ、標準入力を閉じると子プロセスが終了することを確認します。

## 実行

1. `LCXL3_JXA_Probe`フォルダーをLiveが読み込むMIDI Remote Scriptsフォルダーへ配置します。
2. 作業中のLive Setを保存したうえでLiveを再起動します。新しいControl Surfaceの一覧への反映に再起動が必要な場合があります。
3. LiveのMIDI設定の空いている行に`LCXL3 JXA Probe`を選びます。入力と出力はどちらも`None`です。
4. Liveの`Log.txt`で、次の行を確認します。

```text
LCXL3_JXA_PROBE PASS subprocess + nonblocking pipes + echo + EOF exit
```

Pythonバージョン、各モジュールのimport結果、子PID、終了結果もログへ記録します。失敗や5秒のタイムアウトの場合は`FAIL`を記録します。診断終了後はその行のControl Surfaceを`None`へ戻します。

## 判定の範囲

この診断の成功は、Liveからの外部プロセス起動と通信経路の成立を示します。アクセシビリティ権限、実際のキー受信、Serum 2での操作感は別に検証します。通常のPythonから同じ診断が成功しても、Live内での成功として扱いません。

本診断はLiveの入出力ポートや既存のコントローラー設定を変更しません。導入済みのBome版を新方式に切り替える作業とは分けて実施します。
