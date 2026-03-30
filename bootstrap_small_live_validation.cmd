@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0bootstrap_small_live_validation.ps1" %*
exit /b %ERRORLEVEL%
