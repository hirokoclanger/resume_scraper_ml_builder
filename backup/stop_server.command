#!/bin/bash
# Double-click to stop the job finder server (port 8765).
PORT="${JOB_FINDER_PORT:-8765}"
PIDS=$(lsof -ti tcp:$PORT 2>/dev/null)
if [ -z "$PIDS" ]; then
  echo "No server running on port $PORT."
else
  echo "Stopping server (PIDs: $PIDS)..."
  kill $PIDS 2>/dev/null
  sleep 1
  # Force kill if still running
  REMAINING=$(lsof -ti tcp:$PORT 2>/dev/null)
  if [ -n "$REMAINING" ]; then
    kill -9 $REMAINING 2>/dev/null
  fi
  echo "Stopped."
fi
sleep 1
