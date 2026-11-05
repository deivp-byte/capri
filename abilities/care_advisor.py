"""
abilities/care_advisor.py - Proactive Activity & Wellness Advisor for Capri
Inspired by capri-desktop-main Care.cs & Commentary.cs:
- Monitors foreground window activity (Coding, Gaming, Browsing, Idle)
- Real-time hardware telemetry alerts (RAM stress, CPU spikes, Low Disk)
- Ergonomic health check-ins (Hydration, Stretch, 20-20-20 Eye Rule, Late Night Sleep)
- Spider-Man Peter Parker voice: scientific, caring, witty, street-smart partner
- Non-intrusive pacing: cooldown timers prevent repetitive or annoying notifications
"""

from __future__ import annotations

import datetime
import os
import random
import time
from typing import Dict, Optional, Tuple

import psutil

from abilities.system_sensor import get_hardware_specs
from abilities.window_manager import get_topmost_app_window
from abilities.media_sensor import get_now_playing


class CareAdvisor:
    """
    Manages proactive reminders, desktop activity observations,
    and ergonomic wellness advice.
    """

    def __init__(self) -> None:
        self.session_start = time.monotonic()
        self.last_advice_time: float = time.monotonic() - 180.0 # Allow first check-in after brief warmup
        self.min_interval_seconds: float = 360.0  # 6 minutes minimum between unprompted spontaneous tips
        self.last_activity: str = "general"
        self.water_count: int = 0
        self.stretch_count: int = 0

    def get_proactive_observation(self, force: bool = False) -> Optional[str]:
        """
        Evaluates current machine state, focused window, and session duration.
        Returns a rich proactive comment if conditions are met, or None if resting.
        """
        now = time.monotonic()
        if not force and (now - self.last_advice_time < self.min_interval_seconds):
            return None

        # 1. Hardware Emergency / Resource Stress Check
        hw_alert = self._check_hardware_stress()
        if hw_alert:
            self.last_advice_time = now
            return hw_alert

        # 2. Late Night Sleep Nudge (between 23:30 and 06:00)
        late_alert = self._check_late_night()
        if late_alert and (force or random.random() < 0.70):
            self.last_advice_time = now
            return late_alert

        # 3. Active Window & Work Context Commentary
        app_alert = self._check_active_context()
        if app_alert and (force or random.random() < 0.65):
            self.last_advice_time = now
            return app_alert

        # 4. Ergonomic Wellness (Water, Eyes, Stretch)
        wellness_alert = self._check_ergonomic_care()
        if wellness_alert:
            self.last_advice_time = now
            return wellness_alert

        # 5. Fallback science/patrol trivia if forced
        if force:
            from abilities.spontaneous_talk import get_spontaneous_chatter
            self.last_advice_time = now
            return get_spontaneous_chatter()

        return None

    def _check_hardware_stress(self) -> Optional[str]:
        """Inspects CPU, RAM, and Disk for performance bottlenecks."""
        try:
            specs = get_hardware_specs()
            ram_pct = specs["ram"]["usage_pct"]
            cpu_pct = specs["cpu"]["usage_pct"]

            if ram_pct > 88.0:
                return (
                    f"⚠️ Ojo al dato, socio: la memoria RAM está al {ram_pct:.0f}%. "
                    "Parece que alguna app o pestaña del navegador tiene un apetito digno de Venom. "
                    "Si notas que el PC va lento, avísame y revisamos qué procesos están devorando memoria."
                )

            if cpu_pct > 85.0:
                return (
                    f"🔥 ¡Sentido arácnido vibrando! La CPU está trabajando al {cpu_pct:.0f}%. "
                    "Los ventiladores suenan como las turbinas del Quinjet de los Vengadores. ¿Qué compilación o render tienes entre manos?"
                )

            # Check drive C free space
            c_disk = psutil.disk_usage("C:\\")
            free_gb = c_disk.free / (1024 ** 3)
            if free_gb < 12.0:
                return (
                    f"💾 Consejo de mantenimiento: Te quedan solo {free_gb:.1f} GB libres en el disco principal C:. "
                    "Si quieres, puedo abrirte la carpeta de Descargas o la papelera para liberar espacio antes de que Windows proteste."
                )
        except Exception:
            pass
        return None

    def _check_late_night(self) -> Optional[str]:
        """Advises resting during late night or early morning hours."""
        dt = datetime.datetime.now()
        hour = dt.hour
        minute = dt.minute

        if (hour == 23 and minute >= 30) or (hour in (0, 1, 2, 3, 4, 5)):
            late_lines = [
                f"🌙 Socio, son las {dt.strftime('%H:%M')} de la noche... Hasta Spider-Man cuelga el traje para recargar energía celular.",
                "Oye, un buen científico sabe que el cerebro rinde el doble tras dormir 7 u 8 horas. No te quemes las pestañas hasta las tantas.",
                "Tía May siempre decía que nada bueno se programa pasadas las doce de la noche. Tómate un respiro y seguimos mañana con las pilas al 100%."
            ]
            return random.choice(late_lines)
        return None

    def _check_active_context(self) -> Optional[str]:
        """Analyzes focused app window (VS Code, Brave, Games, etc.)."""
        top = get_topmost_app_window()
        if not top:
            return None

        _, title, _ = top
        t_low = title.lower()

        # Coding context (VS Code, PyCharm, Sublime, Terminal, PowerShell)
        if any(code_app in t_low for code_app in ("visual studio code", "vscode", "pycharm", "cursor", "sublime", "powershell", "cmd.exe", "terminal")):
            code_tips = [
                "👨‍💻 Veo que estás dándole duro al código. Recuerda hacer commit de vez en cuando; las telarañas salvan caídas y Git salva proyectos.",
                "¡Ese entorno de desarrollo me resulta familiar! Consejo de laboratorio: si un bug te atasca más de 20 minutos, mirar por la ventana 1 minuto suele traer la solución.",
                "Revisando tus líneas de código... Tranquilo, no se lo contaré a Jameson si se te escapa un print de depuración suelto por ahí."
            ]
            return random.choice(code_tips)

        # Browsing / Research context
        if any(browser in t_low for browser in ("brave", "chrome", "firefox", "edge")):
            if any(study in t_low for study in ("github", "stackoverflow", "wikipedia", "docs", "documentación", "pdf", "tutorial")):
                return (
                    "📚 Leyendo documentación técnica, ¿eh? Peter Parker aprueba la investigación científica rigurosa. "
                    "Si necesitas que busque algo específico o abra carpetas de notas, solo pídemelo."
                )

        # Gaming context
        if any(game_kw in t_low for game_kw in ("steam", "epic games", "minecraft", "fortnite", "valorant", "league of legends", "cs2", "cyberpunk")):
            return (
                "🎮 ¡Modo jugón detectado! Mis reflejos arácnidos me dicen que esa partida la ganas tú. "
                "Céntrate en el juego; yo me quedo aquí en guardia por si asoma alguna notificación urgente."
            )

        return None

    def _check_ergonomic_care(self) -> Optional[str]:
        """Ergonomic suggestions based on session duration."""
        session_mins = (time.monotonic() - self.session_start) / 60.0

        if session_mins > 45.0 and self.stretch_count == 0:
            self.stretch_count += 1
            return (
                "🧘 Recordatorio ergonómico arácnido: Llevamos más de 45 minutos seguidos en la silla. "
                "Estira los hombros, rota las muñecas y relaja el cuello. ¡Mantener la flexibilidad es clave para cualquier acróbata del teclado!"
            )

        if session_mins > 80.0 and self.water_count == 0:
            self.water_count += 1
            return (
                "💧 ¡Alerta de hidratación! El cuerpo humano es un 60% agua y las neuronas la necesitan para disparar impulsos a toda velocidad. "
                "Échate un trago de agua antes de seguir con la siguiente tarea."
            )

        # 20-20-20 rule
        if random.random() < 0.40:
            return (
                "👀 Regla 20-20-20 de salud visual: Cada 20 minutos, mira a un punto a 6 metros (20 pies) de distancia durante 20 segundos. "
                "Tus ojos descansarán la tensión del monitor y evitarás la fatiga visual."
            )

        return None


# Global singleton instance
_CARE_ADVISOR = CareAdvisor()


def get_proactive_advice(force: bool = False) -> Optional[str]:
    """Public helper to get proactive advice from the care advisor."""
    return _CARE_ADVISOR.get_proactive_observation(force=force)
