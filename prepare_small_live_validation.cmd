@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0prepare_small_live_validation.ps1" %*
endlocal
