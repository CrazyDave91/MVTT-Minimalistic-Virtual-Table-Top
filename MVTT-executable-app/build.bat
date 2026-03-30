@echo off
REM This code was created with GitHub Copilot.
REM This codebase is released under the MIT License.
REM Use at your own risk. Provided "as is", without warranties of any kind.

REM MVTT Battlemap — build script for Windows EXE
REM Run from the battlemap-python-app directory after activating your venv.
REM
REM Output: dist/MVTT_Battlemap.exe (single file, no console window)

if exist MVTT_Battlemap.spec del /q MVTT_Battlemap.spec

pyinstaller ^
  --clean ^
  --onefile ^
  --windowed ^
  --name MVTT_Battlemap ^
  --add-data "assets\icons;assets\icons" ^
  --hidden-import PIL._tkinter_finder ^
  main.py

echo.
echo Build complete. Executable: dist\MVTT_Battlemap.exe
