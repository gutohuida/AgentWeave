#!/usr/bin/env bash
# Kill the 8011 drive Hub's whole process tree (a crash, not a clean shutdown) and start it again
# from source on the current checkout. Prints the new pid.
set -u
DB="${AW_DB_PATH:-C:/Users/huida/AppData/Local/Temp/aw0905/aw0905.db}"
LOG="${AW_HUB_LOG:-/c/Users/huida/AppData/Local/Temp/aw0905/hub8011.log}"
PID=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*8011*' } | Select-Object -First 1).ProcessId" | tr -d '\r')
if [ -n "$PID" ]; then
  powershell -NoProfile -Command "taskkill /PID $PID /T /F" >/dev/null 2>&1
  echo "killed tree of $PID"
fi
cd /c/Users/huida/Documents/projects/AgentWeave/hub || exit 1
DATABASE_URL="sqlite+aiosqlite:///$DB" AW_LOG_LEVEL=INFO nohup py -3.11 -m uvicorn hub.main:app --port 8011 --host 127.0.0.1 >> "$LOG" 2>&1 &
for i in $(seq 1 30); do
  sleep 2
  if curl -s -m 2 http://127.0.0.1:8011/health >/dev/null 2>&1 && [ -n "$(curl -s -m 2 http://127.0.0.1:8011/health)" ]; then
    NEW=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -like '*8011*' } | Select-Object -First 1).ProcessId" | tr -d '\r')
    echo "hub up again, pid $NEW"
    exit 0
  fi
done
echo "hub did not come back"; exit 1
