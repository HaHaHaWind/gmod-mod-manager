@echo off
rem GMod Mod Manager - one-click start (Windows)
rem Double-click this file, or run it from a terminal.
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
echo.
pause
