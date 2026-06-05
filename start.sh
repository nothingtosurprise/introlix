#!/bin/bash

# Function to stop all background processes when received exit signal
cleanup() {
    echo "Stopping background processes..."
    kill -TERM "$BACKEND_PID" 2>/dev/null
    kill -TERM "$FRONTEND_PID" 2>/dev/null
    wait "$BACKEND_PID" 2>/dev/null
    wait "$FRONTEND_PID" 2>/dev/null
    exit 0
}

# Trap SIGTERM and SIGINT
trap cleanup SIGTERM SIGINT

# Start backend on port 8042
echo "Starting backend on port 8042..."
python -m uvicorn app:app --host 0.0.0.0 --port 8042 &
BACKEND_PID=$!

# Start frontend on port 8043
echo "Starting frontend on port 8043..."
cd web
PORT=8043 pnpm start &
FRONTEND_PID=$!

# Wait for both processes
wait "$BACKEND_PID" "$FRONTEND_PID"
