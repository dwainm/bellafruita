#!/bin/bash
# Continuous flood test - starts mock server and runs 100000 turbo events

# Setup Python venv if it exists
if [ -d "venv" ]; then
    echo "Activating venv..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating .venv..."
    source .venv/bin/activate
fi

echo "Starting mock server in background..."
python main.py --mock --view web &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for server to start..."
for i in {1..30}; do
    if curl -s http://localhost:7682/api/inputs > /dev/null 2>&1; then
        echo "Server ready!"
        break
    fi
    sleep 0.5
done

# Check if server started
if ! curl -s http://localhost:7682/api/inputs > /dev/null 2>&1; then
    echo "ERROR: Server failed to start"
    kill $SERVER_PID 2>/dev/null
    exit 1
fi

# Open dashboard in browser
echo "Opening dashboard..."
open http://localhost:7681

echo "Starting flood test with 100000 cycles..."
python test_mock_flood.py --cycles 100000 --turbo

echo "Flood test complete. Stopping server..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null

echo "Done."
