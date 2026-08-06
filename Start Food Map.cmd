@echo off
setlocal
title DuskRain Food Map
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-food-map.ps1" -ProjectRoot "%~dp0"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" echo Startup failed with exit code %EXIT_CODE%.
pause
exit /b %EXIT_CODE%
