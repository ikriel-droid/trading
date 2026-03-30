@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0validate_fresh_environment_deployment.ps1" %*
endlocal
