"""Mock input control server for testing.

Provides a web interface to control mock input states during testing
without hardware. Only available in mock mode.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
import uvicorn
from pathlib import Path

from io_mapping import MODBUS_MAP


class InputStateRequest(BaseModel):
    value: bool


class RegisterValueRequest(BaseModel):
    value: int


class MockControlServer:
    """Web server for controlling mock input states."""

    def __init__(self, mock_input_client, mock_output_client, log_manager, port: int = 7682):
        self.mock_input_client = mock_input_client
        self.mock_output_client = mock_output_client
        self.log_manager = log_manager
        self.port = port
        self.app = FastAPI(title="Bella Fruita Mock Control")
        self._setup_routes()

    def _setup_routes(self):
        @self.app.get("/", response_class=HTMLResponse)
        async def root():
            static_dir = Path(__file__).parent.parent / "static"
            mock_file = static_dir / "mock_control.html"
            if mock_file.exists():
                return FileResponse(mock_file)
            return HTMLResponse("<h1>Error: mock_control.html not found</h1>", status_code=500)

        @self.app.get("/api/inputs")
        async def get_all_inputs():
            inputs = []
            for address, info in MODBUS_MAP['INPUT']['coils'].items():
                input_number = address + 1
                input_info = self.mock_input_client.get_input_info(input_number)
                inputs.append({
                    'input_number': input_number,
                    'address': address,
                    'label': info['label'],
                    'description': info['description'],
                    'state': input_info.get('state', False) if input_info else False
                })
            return {'inputs': inputs}

        @self.app.get("/api/inputs/{input_number}")
        async def get_input(input_number: int):
            if input_number < 1 or input_number > 16:
                raise HTTPException(status_code=404, detail="Input not found (valid: 1-16)")
            input_info = self.mock_input_client.get_input_info(input_number)
            if not input_info:
                raise HTTPException(status_code=404, detail="Input not found")
            return {
                'input_number': input_number,
                'label': input_info.get('label', ''),
                'description': input_info.get('description', ''),
                'state': input_info.get('state', False)
            }

        @self.app.post("/api/inputs/{input_number}")
        async def set_input(input_number: int, request: InputStateRequest):
            if input_number < 1 or input_number > 16:
                raise HTTPException(status_code=404, detail="Input not found (valid: 1-16)")
            self.mock_input_client.set_input_state(input_number, request.value)
            input_info = self.mock_input_client.get_input_info(input_number)
            self.log_manager.debug(f"Mock: Set {input_info.get('label', f'Input {input_number}')} = {request.value}")
            return {
                'success': True,
                'input_number': input_number,
                'label': input_info.get('label', ''),
                'state': request.value
            }

        @self.app.get("/api/registers/version")
        async def get_version_register():
            return {'address': 0, 'value': self.mock_output_client._holding_registers.get(0, 0)}

        @self.app.post("/api/registers/version")
        async def set_version_register(request: RegisterValueRequest):
            self.mock_output_client.set_register(0, request.value)
            self.log_manager.debug(f"Mock: Set VERSION register = {request.value}")
            return {'success': True, 'address': 0, 'value': request.value}

    def run(self):
        self.log_manager.info(f"Mock control server: http://localhost:{self.port}")
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
            access_log=False
        )
        server = uvicorn.Server(config)
        server.run()


def run_mock_control_server(mock_input_client, mock_output_client, log_manager, port: int = 7682):
    """Run mock control server (blocking)."""
    server = MockControlServer(mock_input_client, mock_output_client, log_manager, port)
    server.run()
