"""
abilities/system_sensor.py - Real-Time Hardware & System Specifications Telemetry

Provides deep, zero-overhead hardware introspection:
- Operating System details & kernel version
- CPU model, core counts, and real-time utilization
- RAM memory metrics (total, used, free, percentage)
- Storage volumes (total capacity, available space per drive)
- GPU graphics cards (NVIDIA, AMD, Intel)
- Battery state & power charging status
- System uptime & active user session
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional
import psutil


_CACHED_GPU: Optional[List[str]] = None
_LAST_GPU_SCAN: float = 0.0


def get_gpu_names() -> List[str]:
    """Retrieves detected GPU / graphics adapter names (cached for performance)."""
    global _CACHED_GPU, _LAST_GPU_SCAN
    now = time.monotonic()
    if _CACHED_GPU is not None and (now - _LAST_GPU_SCAN) < 300.0:
        return _CACHED_GPU

    gpus = []
    if sys.platform == "win32":
        try:
            cmd = ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_VideoController).Name"]
            out = subprocess.check_output(cmd, text=True, timeout=2.5).strip()
            gpus = [line.strip() for line in out.splitlines() if line.strip()]
        except Exception:
            pass
    elif sys.platform.startswith("linux"):
        try:
            out = subprocess.check_output(["lspci"], text=True, timeout=2.0)
            for line in out.splitlines():
                if "VGA" in line or "3D" in line:
                    parts = line.split(":", 2)
                    gpus.append(parts[-1].strip() if len(parts) > 2 else line.strip())
        except Exception:
            pass

    _CACHED_GPU = gpus
    _LAST_GPU_SCAN = now
    return gpus


def get_hardware_specs() -> Dict[str, Any]:
    """
    Gathers detailed hardware specifications and real-time load telemetry.
    """
    # OS
    os_name = f"{platform.system()} {platform.release()}"
    arch = platform.machine()

    # CPU
    cpu_model = platform.processor() or "Procesador multinúcleo"
    cpu_cores_logical = psutil.cpu_count(logical=True) or 1
    cpu_cores_physical = psutil.cpu_count(logical=False) or 1
    cpu_usage = psutil.cpu_percent(interval=None)

    # RAM
    vm = psutil.virtual_memory()
    ram_total_gb = round(vm.total / (1024 ** 3), 1)
    ram_used_gb = round(vm.used / (1024 ** 3), 1)
    ram_free_gb = round(vm.available / (1024 ** 3), 1)
    ram_pct = vm.percent

    # Disks
    disks = []
    try:
        if sys.platform == "win32":
            drives = ["C:\\"]
            # Look for other common drive letters
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                path = f"{letter}:\\"
                if os.path.exists(path):
                    drives.append(path)
        else:
            drives = ["/"]

        for d in drives:
            try:
                usage = psutil.disk_usage(d)
                disks.append({
                    "drive": d,
                    "total_gb": round(usage.total / (1024 ** 3), 1),
                    "free_gb": round(usage.free / (1024 ** 3), 1),
                    "used_pct": usage.percent,
                })
            except Exception:
                pass
    except Exception:
        pass

    # GPU
    gpus = get_gpu_names()

    # Battery
    battery_info = None
    try:
        bat = psutil.sensors_battery()
        if bat:
            battery_info = {
                "percent": bat.percent,
                "power_plugged": bat.power_plugged,
            }
    except Exception:
        pass

    # Uptime
    uptime_seconds = int(time.time() - psutil.boot_time())
    hours = uptime_seconds // 3600
    minutes = (uptime_seconds % 3600) // 60
    uptime_str = f"{hours}h {minutes}m"

    return {
        "os": f"{os_name} ({arch})",
        "cpu": {
            "model": cpu_model,
            "logical_cores": cpu_cores_logical,
            "physical_cores": cpu_cores_physical,
            "usage_pct": cpu_usage,
        },
        "ram": {
            "total_gb": ram_total_gb,
            "used_gb": ram_used_gb,
            "free_gb": ram_free_gb,
            "usage_pct": ram_pct,
        },
        "disks": disks,
        "gpus": gpus,
        "battery": battery_info,
        "uptime": uptime_str,
    }


def format_system_report() -> str:
    """Formats full hardware telemetry as a concise, structured report for the LLM."""
    specs = get_hardware_specs()

    gpu_str = ", ".join(specs["gpus"]) if specs["gpus"] else "Integrada / Estándar"
    disk_parts = [f"{d['drive']} ({d['free_gb']} GB libres de {d['total_gb']} GB, {d['used_pct']}% usado)" for d in specs["disks"]]
    disks_str = "; ".join(disk_parts)

    battery_str = ""
    if specs["battery"]:
        status = "cargando" if specs["battery"]["power_plugged"] else "en batería"
        battery_str = f" | Batería: {specs['battery']['percent']}% ({status})"

    return (
        f"Sistema Operativo: {specs['os']} | Tiempo encendido: {specs['uptime']}\n"
        f"Procesador (CPU): {specs['cpu']['model']} ({specs['cpu']['logical_cores']} hilos, uso actual: {specs['cpu']['usage_pct']}%)\n"
        f"Memoria RAM: {specs['ram']['total_gb']} GB totales ({specs['ram']['free_gb']} GB disponibles, uso actual: {specs['ram']['usage_pct']}%)\n"
        f"Tarjeta Gráfica (GPU): {gpu_str}\n"
        f"Almacenamiento: {disks_str}{battery_str}"
    )


def get_quick_system_summary() -> str:
    """One-line telemetry snippet for prompt injection."""
    try:
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        gpus = get_gpu_names()
        gpu_lead = gpus[-1] if gpus else "GPU Estándar"
        return (
            f"PC: {platform.system()} {platform.release()} | "
            f"RAM: {vm.percent}% usado ({round(vm.available / (1024**3), 1)}GB libre) | "
            f"CPU: {cpu}% | GPU: {gpu_lead}"
        )
    except Exception:
        return f"PC: {platform.system()} {platform.release()}"
