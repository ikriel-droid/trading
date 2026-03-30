@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0generate_small_live_validation_ppt.ps1" %*
exit /b %ERRORLEVEL%
