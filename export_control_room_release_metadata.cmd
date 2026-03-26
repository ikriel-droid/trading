@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%export_control_room_release_metadata.ps1" %*
endlocal
