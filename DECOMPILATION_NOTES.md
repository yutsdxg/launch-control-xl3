# Launch_Control_XL_3 `.pyc` 復元メモ

## 1. 判明した前提
- 対象ファイルはすべて `.pyc`。
- マジック番号は `a70d0d0a`。
- `~/.pyenv/versions/3.11.14/bin/python` の `importlib.util.MAGIC_NUMBER` も `a70d0d0a`。
- つまり **CPython 3.11 系でコンパイル** されたバイトコード。

## 2. この環境でできたこと
以下スクリプトで `.pyc` から復元に必要な情報を抽出済み。

- スクリプト: `/Users/yuts/Data/Dev/launch-control-xl3/scripts/extract_pyc_artifacts.py`
- 出力先: `/Users/yuts/Data/Dev/launch-control-xl3/recovered_dis/`

出力内容:
- `metadata.json`: 元ファイルパス (`co_filename`)、関数名、引数情報、シンボル名
- `disassembly.txt`: `dis` による逆アセンブル結果

実行コマンド:

```bash
~/.pyenv/versions/3.11.14/bin/python \
  /Users/yuts/Data/Dev/launch-control-xl3/scripts/extract_pyc_artifacts.py \
  --input-dir /Users/yuts/Data/Dev/launch-control-xl3/Launch_Control_XL_3 \
  --output-dir /Users/yuts/Data/Dev/launch-control-xl3/recovered_dis
```

## 3. 「コンパイル前のソース」を作る現実的な方法

### 方法A: デコンパイラで自動復元（最優先）
1. Python 3.11 の環境を使う
2. 3.11 バイトコード対応デコンパイラを試す（複数）
3. 生成された `.py` を人手で修正

候補:
- `pycdc`（対応状況はバージョン依存。3.11は不完全な場合あり）
- `decompyle3`（3.11で失敗するケースがあるため補助的に使用）

### 方法B: `disassembly.txt` から手動再構成
1. `metadata.json` の関数シグネチャ情報を下敷きにする
2. `disassembly.txt` で制御フローと呼び出し順を復元
3. まず動く最小実装を作り、Ableton側で差分検証する

この案件では、方法Aだけで完全一致する保証は薄く、**A+B併用** が最短です。

## 4. 補足
- `metadata.json` 内の `co_filename` に、ビルド時の元パスが残っている。
- 例: `output/Live/mac_universal_64_static/Release/python-bundle/MIDI Remote Scripts/Launch_Control_XL_3/device.py`
- これは参照用の埋め込み文字列で、ローカルにそのパスが存在するとは限らない。

## 5. 今回の実測結果（重要）
- `decompyle3` / `uncompyle6` はこの対象で `Unsupported Python version, 3.11` となり、実用的な出力は得られなかった。
- `pycdc` は一部を復元できたが、`MAKE_CELL` など未対応 opcode があり、そのままでは壊れたコードが混在した。
- 結果として、**`pycdc` の部分復元 + `recovered_dis/*/disassembly.txt` で手修正** が実運用上の最短ルートだった。

## 6. 手修正で実際に詰まったポイント
- `colors.py`
  - `make_simple_color = (lambda ... )()` という誤復元が出る場合がある。
  - 正しくは `@memoize` 付きの関数定義。
- `display.py`
  - `view.CompoundView(...)` に生関数を渡すと `render_condition` 系のエラーになる。
  - `main_view = view.View(...)` が必要。
  - `DisplayContent.with_parameters()` の `cls((), ...)` は誤りで、`cls(..., **k)` にする。
- `colored_encoder.py`
  - 最小実装のままだとエンコーダ LED が点灯しない。
  - `_update_parameter_listeners` / `_send_led_color` / `_parameter_value_changed` の復元が必要。
- `midi.py`
  - `make_connection_message(connect=(True,))` は復元由来の表記ゆれ。
  - `connect=True` に統一しておくと誤解が減る。

## 7. 動作確認の観点
- 読み込み可否だけでなく、以下を確認する:
  1. コントロールサーフェス一覧に表示されること
  2. DAWポート (`LCXL3 ... DAW Out/In`) で起動できること
  3. エンコーダLED、表示更新、モード切替が機能すること
- 不具合時は `~/Library/Preferences/Ableton/Live 12.3.5/Log.txt` の `RemoteScriptError` を時刻付きで追う。

## 8. 成果物の扱い
- 元データ（`.pyc`）は `Launch_Control_XL_3/` に保持。
- 復元・修正版（Pythonソース）は、実運用ディレクトリ（例: `Launch_Control_XL_3_Decompile/`）にまとめる。
- 中間生成物（`logs/`, `recovered_dis/`, `recovered_py/`, `pycdc/`, 仮想環境）は、最終コミット対象から除外してよい。
