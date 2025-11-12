"""Web dashboard server for monitoring system state.

This module provides a read-only web interface for viewing the system state
in real-time via WebSocket updates.
"""

import asyncio
import json
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pathlib import Path


class WebDashboard:
    """Web dashboard server with real-time WebSocket updates."""

    def __init__(self, shared_state, log_manager, config, port: int = 7681):
        """Initialize web dashboard.

        Args:
            shared_state: SystemState instance (thread-safe)
            log_manager: LogManager instance
            config: AppConfig instance
            port: Port to listen on
        """
        self.shared_state = shared_state
        self.log_manager = log_manager
        self.config = config
        self.port = port
        self.app = FastAPI(title="Bella Fruita Dashboard")

        # Setup routes
        self._setup_routes()

        # Active WebSocket connections
        self.active_connections = []

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            """Serve main dashboard page."""
            static_dir = Path(__file__).parent.parent / "static"
            index_file = static_dir / "index.html"

            if index_file.exists():
                return FileResponse(index_file)
            else:
                return HTMLResponse("""
                    <html>
                        <head><title>Bella Fruita Dashboard</title></head>
                        <body>
                            <h1>Error: Dashboard not found</h1>
                            <p>static/index.html is missing</p>
                        </body>
                    </html>
                """, status_code=500)

        @self.app.get("/api/state")
        async def get_state():
            """REST endpoint for current state snapshot."""
            return self.shared_state.get_snapshot()

        @self.app.get("/api/config")
        async def get_config():
            """REST endpoint for configuration values."""
            return {
                "site_name": self.config.site_name
            }

        @self.app.get("/api/logs")
        async def get_logs():
            """REST endpoint for recent log entries."""
            recent_events = self.log_manager.get_recent_events(count=100)

            # Format events for frontend
            logs = []
            for event in recent_events:
                logs.append({
                    "timestamp": event.get_formatted_time(),
                    "level": event.level,
                    "message": event.message
                })

            return {"logs": logs}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time state updates."""
            await websocket.accept()
            self.active_connections.append(websocket)
            self.log_manager.info(f"Web client connected (total: {len(self.active_connections)})")

            try:
                # Send initial state immediately
                snapshot = self.shared_state.get_snapshot()
                await websocket.send_json(snapshot)

                # Keep connection alive and send updates
                while True:
                    # Get latest state
                    snapshot = self.shared_state.get_snapshot()

                    # Send to client
                    await websocket.send_json(snapshot)

                    # Wait before next update (10 updates/second)
                    await asyncio.sleep(0.1)

            except WebSocketDisconnect:
                self.active_connections.remove(websocket)
                self.log_manager.info(f"Web client disconnected (total: {len(self.active_connections)})")
            except Exception as e:
                self.log_manager.error(f"WebSocket error: {e}")
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)

    def run(self):
        """Run the web server (blocking).

        This should be called from a separate thread or process.
        """
        self.log_manager.info(f"Starting web dashboard on http://0.0.0.0:{self.port}")
        self.log_manager.info(f"Access dashboard at: http://localhost:{self.port}")

        # Run uvicorn server
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",  # Reduce uvicorn noise
            access_log=False
        )
        server = uvicorn.Server(config)
        server.run()


def run_web_dashboard(shared_state, log_manager, config, port: int = 7681):
    """Run web dashboard in current thread (blocking).

    Args:
        shared_state: SystemState instance
        log_manager: LogManager instance
        config: AppConfig instance
        port: Port to listen on
    """
    dashboard = WebDashboard(shared_state, log_manager, config, port)
    dashboard.run()
