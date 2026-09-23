@echo off
rem Windows Batch wrapper for akstack orchestrator
set SCRIPT_DIR=%~dp0..
set PYTHONPATH=%SCRIPT_DIR%
python -m orchestrator.cli %*
