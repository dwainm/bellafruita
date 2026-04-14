"""Cross-platform system resource monitoring."""

import os
import platform
from typing import Dict, Any


def get_system_stats() -> Dict[str, Any]:
    """Get current system resource usage.
    
    Returns:
        Dict with cpu_percent, memory_percent, disk_percent, uptime_seconds,
        and load_average (Unix only).
    """
    try:
        import psutil
    except ImportError:
        return _get_basic_stats_fallback()
    
    stats = {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
        "uptime_seconds": _get_uptime_seconds(),
    }
    
    if hasattr(os, 'getloadavg'):
        load_avg = os.getloadavg()
        stats["load_average"] = {
            "1min": round(load_avg[0], 2),
            "5min": round(load_avg[1], 2),
            "15min": round(load_avg[2], 2),
        }
    
    return stats


def _get_uptime_seconds() -> float:
    """Get system uptime in seconds."""
    try:
        import psutil
        import time
        return time.time() - psutil.boot_time()
    except Exception:
        return 0.0


def _get_basic_stats_fallback() -> Dict[str, Any]:
    """Fallback stats when psutil is not available."""
    return {
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
        "disk_percent": 0.0,
        "uptime_seconds": 0.0,
        "error": "psutil not available",
    }
