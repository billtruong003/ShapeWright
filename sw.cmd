@echo off
rem Shapewright CLI launcher for Windows: works from a fresh clone without installing the package (same as ./sw).
setlocal
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
python -m shapewright %*
exit /b %ERRORLEVEL%
