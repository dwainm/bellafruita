"""Configuration settings for Bella Fruita apple sorting system."""

from dataclasses import dataclass


@dataclass
class ModbusConfig:
    """Modbus connection settings."""
    input_ip: str = "172.20.231.25"
    output_ip: str = "172.20.231.49"
    #input_ip: str = "172.20.231.125" # boet
    #output_ip: str = "172.20.231.41" # boet
    input_slave_id: int = 1
    output_slave_id: int = 1
    timeout: float = 10.0  # Network timeout in seconds (Modbus operation timeout)
    retries: int = 0  # Number of retry attempts per operation (0 = fail fast)


@dataclass
class SystemConfig:
    """Core system timing and monitoring settings."""
    poll_interval: float = 0.1
    log_stack_size: int = 3000
    comms_timeout: float = 5.0  # Comms failure detection time (how long VERSION=0 before declaring comms failed)
    edge_detection_window_ms: float = 15000.0  # Time window for detecting button presses and signal edges (milliseconds)


@dataclass
class TUIConfig:
    """Terminal UI update rates."""
    poll_rate: float = 0.1
    log_refresh_rate: float = 3.0
    heartbeat_reset_rate: float = 0.25


@dataclass
class AppConfig:
    """Complete application configuration."""
    modbus: ModbusConfig
    system: SystemConfig
    tui: TUIConfig
    use_mock: bool = False

    @classmethod
    def create_default(cls, use_mock: bool = False) -> 'AppConfig':
        """Create default configuration.

        Args:
            use_mock: Run in mock mode for testing

        Returns:
            AppConfig instance with default settings
        """
        return cls(
            modbus=ModbusConfig(),
            system=SystemConfig(),
            tui=TUIConfig(),
            use_mock=use_mock
        )
