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
