@echo off
set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
start "" %CHROME% --remote-debugging-port=9222 --user-data-dir=".\sessions\member1"
start "" %CHROME% --remote-debugging-port=9223 --user-data-dir=".\sessions\member2"
start "" %CHROME% --remote-debugging-port=9224 --user-data-dir=".\sessions\member3"
start "" %CHROME% --remote-debugging-port=9225 --user-data-dir=".\sessions\member4"