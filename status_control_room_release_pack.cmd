@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%status_control_room_release_pack.ps1" %*
endlocal
