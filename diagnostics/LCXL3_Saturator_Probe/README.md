# SaturatorのDrive入力順序を確認する診断用Control Surface

このControl Surfaceは、既存の`Launch_Control_XL_3_Mixing`に登録された`parameter: "Drive"`の割り当てを観測します。エンコーダー番号・フェーダー番号やデバイス名では絞りません。デバイスがSaturator以外でも、Driveが割り当てられていれば診断対象です。

パラメータ値、既存の割り当て、MIDI設定は変更しません。MIDIの送信・注入も行いません。Live標準のマッピングが実際に受け入れた値と、Pythonへ転送された操作入力の順序を調べるためのものです。物理コントローラーの操作は人が行います。

## 導入

1. 作業中のLive Setを保存します。
2. `LCXL3_Saturator_Probe`フォルダーを、Liveが読み込むMIDI Remote Scriptsフォルダーへ配置します。本体フォルダー内へ入れないでください。
3. Liveを再起動します。
4. MIDI環境設定の空いているControl Surface行に`LCXL3 Saturator Probe`を選びます。**入力と出力はどちらも`None`**にします。既存のMixing用Control Surface行と入出力は維持します。
5. MixingモードでDriveを割り当てたトラックを選び、無操作ロックを解除します。

名前の一覧反映とPythonモジュールの再読み込みのため、修正後もLiveを再起動します。診断後は追加したControl Surface行だけを`None`へ戻します。

## ログ

Liveの`Log.txt`で`LCXL3_SATURATOR_PROBE`を検索します。プレフィックスの後ろは1行のJSONです。

| event | 記録内容 |
| --- | --- |
| `start` / `stop` | 診断開始・終了 |
| `status` | `observing`または対象割り当て待ち |
| `bind` / `unbind` | 対象の接続・解除。実デバイス、トラック、操作子名を含む |
| `parameter` | 接続時の全パラメータ。0始まりの位置、名前、元の名前、内部値、範囲、表示、選択肢など |
| `drive_value` | Drive変更通知時の前回通知値と現在の実値 |
| `control_input` | 既存の操作子のvalue listenerへ届いた入力、実際のDrive／Output、active／Shift／lock状態 |
| `task_boundary` | 操作または値変更があった後の診断タスク実行時点の実値 |

`seq`はログの連番、`t_ms`は診断開始からの単調時計の経過ミリ秒、`probe_tick`は0.1秒周期の診断タスクの番号です。`probe_tick`は音声バッファー番号や個別のMIDI処理周期ではありません。

同じDriveに複数の操作子を割り当てた場合、Drive変更リスナーは共有し、`control_input`には入力した操作子の名前を記録します。TypeやColorの値にかかわらず順序を観測できます。補正機能の有効条件を満たしたかどうかは、この診断自体では判定しません。

## 実機での確認

以下を別々に実施し、順序と値をログから確認します。診断プログラムが自動でPASSを判断することはありません。

1. Driveを物理フェーダーで動かし、`control_input`時点の実値と`drive_value`の前後関係を確認します。
2. マウスでDriveを変更し、物理入力がないときの変更通知と次の`task_boundary`を確認します。
3. Pickupモードでは、マウス変更後にフェーダーを現在値へ到達させない範囲で動かします。`control_input`があってもDriveが変わっていないことを確認し、その後、値をまたいで追従が始まる入力を確認します。
4. Value Scalingでもマウス変更後のフェーダー操作を確認します。CCから再計算した目標値ではなく、ログにある実際のDrive値を比較します。
5. エンコーダーへDriveを割り当てた場合も確認します。Shift中、ロック中、非active中の入力は状態フラグで識別し、補正候補の入力から除外します。
6. Outputの手動変更、トラック切替、デバイスの変更、同一Driveへの複数割り当てを確認します。

通常のPythonのテストや`receive_midi()`の直接呼び出しは、Liveのネイティブマッピングとtakeoverを通ったことの証拠にはなりません。
