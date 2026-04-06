@echo off
setlocal

python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

python -m PyInstaller --noconfirm MidiMeasureVideoExporter.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete.
echo EXE: dist\MidiMeasureVideoExporter\MidiMeasureVideoExporter.exe
echo Keep the whole dist\MidiMeasureVideoExporter folder together when moving it.
