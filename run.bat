@echo off
title Sathi-Connect by Degitalservice
echo.
echo  ╔═══════════════════════════════════════╗
echo  ║   Sathi-Connect — Degitalservice     ║
echo  ╚═══════════════════════════════════════╝
echo.
echo  Installing dependencies...
pip install flask requests -q
echo  Starting server...
echo  Browser will open automatically.
echo.
python app.py
pause
