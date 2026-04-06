# MIDI Measure Video Exporter

このアプリは、MIDIファイルを読み込み、1小節ごとに固定表示を切り替えながらノーツを可視化し、発音中のノーツだけを白色に切り替えつつ、音声なしのMP4動画として曲全体を書き出すWindows向けデスクトップアプリです。

## 表示仕様

- 解像度: `1920x1080`
- 背景色: 黒
- 通常ノーツ色: 黒よりの灰色
- 発音中ノーツ色: 白
- 表示方式: 1小節ごとに固定表示を切り替え

## セットアップ

```powershell
python -m pip install -r requirements.txt
```

## 起動方法

```powershell
python main.py
```

または `run.bat` をダブルクリックしてください。

## EXEの作成

```powershell
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm MidiMeasureVideoExporter.spec
```

または `build_exe.bat` を実行してください。

生成される実行ファイルは次の場所です。

```text
dist\MidiMeasureVideoExporter\MidiMeasureVideoExporter.exe
```

配布や移動をするときは、`_internal` を含む `dist\MidiMeasureVideoExporter` フォルダごとまとめて扱ってください。EXEはその中の同梱ランタイムを利用します。

## 使い方

1. `.mid` または `.midi` ファイルを開きます。
2. 再生ボタンで小節ごとの切り替え表示をプレビューします。
3. `MP4を書き出す` で動画を書き出します。

## 補足

- 出力される動画に音声は含まれません。
- 複数トラックのノーツはまとめて1つの表示にしています。
- 拍子変更があるMIDIにも対応しており、その拍子に合わせて小節ごとに切り替わります。
- EXE版にはMP4書き出しに必要なFFmpegランタイムが含まれています。
