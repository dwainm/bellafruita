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
from fastapi.middleware.cors import CORSMiddleware
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

        # Allow CORS for mock control server (only in mock mode)
        if config.use_mock:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )

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
            from datetime import datetime
            recent_events = self.log_manager.get_recent_events(count=2000)

            logs = []
            for event in recent_events:
                dt = datetime.fromtimestamp(event.timestamp)
                logs.append({
                    "timestamp": event.get_formatted_time(),
                    "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": dt.strftime("%Y-%m-%d"),
                    "level": event.level,
                    "message": event.message
                })

            return {"logs": logs, "total": len(logs)}

        @self.app.get("/api/log-files")
        async def get_log_files():
            """List available log files for the log reader view."""
            log_dir = self.log_manager.log_file.parent
            current_name = self.log_manager.log_file.name

            files = []
            for path in log_dir.glob("*.jsonl"):
                try:
                    stat = path.stat()
                    files.append({
                        "name": path.name,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "is_current": path.name == current_name,
                    })
                except Exception:
                    continue

            files.sort(key=lambda item: item["modified"], reverse=True)
            return {"files": files, "total": len(files)}

        @self.app.get("/api/log-files/{filename}")
        async def get_log_file_entries(filename: str):
            """Read all entries from a selected log file."""
            # Simple hardening: prevent path traversal and nested paths
            if "/" in filename or "\\" in filename or ".." in filename:
                return {"error": "Invalid filename", "logs": [], "total": 0}

            log_dir = self.log_manager.log_file.parent.resolve()
            target_file = (log_dir / filename).resolve()

            # Ensure selected file stays within log directory
            if target_file.parent != log_dir or not target_file.exists() or target_file.suffix != ".jsonl":
                return {"error": "File not found", "logs": [], "total": 0}

            from datetime import datetime

            def _read_log_entries(path: Path):
                rows = []
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            ts = float(entry.get("timestamp", 0))
                            dt = datetime.fromtimestamp(ts) if ts else None
                            rows.append({
                                "timestamp": dt.strftime("%H:%M:%S.%f")[:-3] if dt else "",
                                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "",
                                "date": dt.strftime("%Y-%m-%d") if dt else "",
                                "level": entry.get("level", "INFO"),
                                "message": entry.get("message", ""),
                            })
                        except Exception:
                            # Keep malformed lines visible for diagnostics
                            rows.append({
                                "timestamp": "",
                                "datetime": "",
                                "date": "",
                                "level": "RAW",
                                "message": line,
                            })
                return rows

            try:
                logs = await asyncio.to_thread(_read_log_entries, target_file)
            except Exception as e:
                return {"error": str(e), "logs": [], "total": 0}

            return {
                "file": filename,
                "logs": logs,
                "total": len(logs),
            }

        if self.config.use_mock:
            @self.app.post("/api/test/flood")
            async def flood_logs(count: int = 100, delay_ms: int = 50):
                """Inject test events to watch UI update in real-time (mock mode only)."""
                import asyncio
                import random

                messages = [
                    "Mode: READY -> MOVING_C3_TO_C2",
                    "Mode: MOVING_C3_TO_C2 -> READY",
                    "Started MOVING_C2_TO_PALM - MOTOR_2 running",
                    "MOTOR_2 stopped after 1s delay",
                    "Motor 3 started after 2 second delay",
                    "Completed MOVING_C3_TO_C2 - both motors stopped",
                    "KLAAR_GEWEEG flag set via API",
                    "Bin detected on S1",
                ]
                levels = ['INFO', 'INFO', 'INFO', 'WARNING']

                for i in range(count):
                    level = random.choice(levels)
                    msg = f"[Test {i+1}/{count}] {random.choice(messages)}"
                    self.log_manager.log_event(level, msg)
                    await asyncio.sleep(delay_ms / 1000.0)

                return {"success": True, "generated": count}

        @self.app.post("/tipbins")
        async def set_klaar_geweeg():
            """POST endpoint to set klaar_geweeg state to true."""
            import tempfile
            import os

            # Create a flag file to signal the polling thread
            flag_file = os.path.join(tempfile.gettempdir(), 'bellafruita_klaar_geweeg.flag')
            try:
                with open(flag_file, 'w') as f:
                    f.write('1')
                self.log_manager.debug(f"Created KLAAR_GEWEEG flag file: {flag_file}")
                return {"success": True, "klaar_geweeg": True}
            except Exception as e:
                self.log_manager.error(f"Failed to create KLAAR_GEWEEG flag file: {e}")
                return {"success": False, "error": str(e)}

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time state updates."""
            await websocket.accept()
            self.active_connections.append(websocket)
            self.log_manager.debug(f"Web client connected (total: {len(self.active_connections)})")

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

                    # Wait before next update (2 updates/second)
                    await asyncio.sleep(0.5)

            except WebSocketDisconnect:
                self.active_connections.remove(websocket)
                self.log_manager.debug(f"Web client disconnected (total: {len(self.active_connections)})")
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
