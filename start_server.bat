@echo off
cd /d C:\Users\rishi\OneDrive\Desktop\YT
C:\Users\rishi\OneDrive\Desktop\YT\venv\Scripts\python.exe -m uvicorn webapp.main:app --host 0.0.0.0 --port 8000 --reload
