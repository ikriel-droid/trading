@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0small_live_validation_helper.ps1" %*
exit /b %ERRORLEVEL%
