@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0complete_remaining.ps1" %*
endlocal
