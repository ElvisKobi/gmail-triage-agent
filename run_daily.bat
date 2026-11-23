@echo off
cd /d C:\Users\elvis\Downloads\gmail_triage_agent
if not exist logs mkdir logs
echo. >> logs\agent.log
echo ===== Run started %date% %time% ===== >> logs\agent.log
.venv\Scripts\python.exe -u summarize.py >> logs\agent.log 2>&1
echo ===== Run ended %date% %time% (exit code %errorlevel%) ===== >> logs\agent.log