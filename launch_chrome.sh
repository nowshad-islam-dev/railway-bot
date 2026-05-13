#!/bin/bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

"$CHROME" --remote-debugging-port=9222 --user-data-dir="./sessions/member1" &
"$CHROME" --remote-debugging-port=9223 --user-data-dir="./sessions/member2"
# "$CHROME" --remote-debugging-port=9224 --user-data-dir="./sessions/member3" &
# "$CHROME" --remote-debugging-port=9225 --user-data-dir="./sessions/member4" &