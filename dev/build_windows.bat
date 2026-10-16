@echo off
REM Builds VoiceCast.vst3 + standalone app and installs the VST3 for Wave Link.
REM Needs: Visual Studio 2022 (Desktop development with C++), CMake, Git.
REM Run from "x64 Native Tools Command Prompt for VS 2022" or a normal terminal.
setlocal
cd /d "%~dp0..\plugin"

cmake -B build -A x64 || goto :fail
cmake --build build --config Release --target VoiceCast_VST3 VoiceCast_Standalone || goto :fail

set "SRC=%~dp0..\plugin\build\VoiceCast_artefacts\Release\VST3\Instant Voicemod.vst3"
set "DST=%CommonProgramFiles%\VST3\Instant Voicemod.vst3"
echo.
net session >nul 2>&1
if errorlevel 1 (
  echo Built OK, but copying into %CommonProgramFiles%\VST3 needs administrator rights.
  echo Right-click build_windows.bat ^> "Run as administrator" to install, or copy this folder by hand:
  echo   %SRC%
) else (
  if exist "%DST%" rmdir /S /Q "%DST%"
  xcopy /E /I /Y /Q "%SRC%" "%DST%" >nul && echo Installed VST3 to %DST%
)

echo.
echo Done.
echo  - Restart Wave Link and add "VoiceCast" as an effect on your mic channel.
echo  - Standalone app (test without Wave Link): plugin\build\VoiceCast_artefacts\Release\Standalone\Instant Voicemod.exe
exit /b 0

:fail
echo Build failed. Scroll up for the first error.
exit /b 1
