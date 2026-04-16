@echo off
setlocal

python -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1

for /d %%D in (dist_* dist_refresh build_* build_refresh) do (
    if exist "%%D" rmdir /s /q "%%D"
)
if exist dist\MidiMeasureVideoExporter rmdir /s /q dist\MidiMeasureVideoExporter
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm MidiMeasureVideoExporter.spec
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build

echo.
echo Build complete.
echo EXE: dist\MidiMeasureVideoExporter\MidiMeasureVideoExporter.exe
echo Keep the whole dist\MidiMeasureVideoExporter folder together when moving it.
