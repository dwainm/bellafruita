"""Configuration settings for Bella Fruita apple sorting system."""

from dataclasses import dataclass


@dataclass
class ModbusConfig:
    """Modbus connection settings."""
    input_ip: str = "172.20.231.25"
    output_ip: str = "172.20.231.49"
    input_slave_id: int = 1
    output_slave_id: int = 1
    timeout: float = 1.0  # Network timeout in seconds (Modbus operation timeout)
    retries: int = 0  # Number of retry attempts per operation (0 = fail fast)


@dataclass
class SystemConfig:
    """Core system timing and monitoring settings."""
    poll_interval: float = 0.1
    log_stack_size: int = 10000  # Lines per log file before rotation
    log_retention_days: int = 7  # Delete old log files after this many days
    comms_timeout: float = 5.0  # Comms failure detection time (how long VERSION=0 before declaring comms failed)
    edge_detection_window_ms: float = 15000.0  # Time window for detecting button presses and signal edges (milliseconds)


@dataclass
class AppConfig:
    """Complete application configuration."""
    modbus: ModbusConfig
    system: SystemConfig
    site_name: str = "Bella Fruita"
    use_mock: bool = False
    debug: bool = False

    @classmethod
    def create_default(cls, use_mock: bool = False, debug: bool = False) -> 'AppConfig':
        """Create default configuration.

        Args:
            use_mock: Run in mock mode for testing
            debug: Enable debug logging for rule conditions

        Returns:
            AppConfig instance with default settings
        """
        return cls(
            modbus=ModbusConfig(),
            system=SystemConfig(),
            use_mock=use_mock,
            debug=debug
        )
