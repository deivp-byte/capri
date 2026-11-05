"""
abilities/spontaneous_talk.py - Spontaneous In-Character Chatter & Trivia Engine

Generates organic, contextual remarks for Spider-Man while idling on the user's desktop:
1. Real-time PC Awareness:
   - High RAM / CPU alerts in Peter Parker's voice
   - Music comments when Spotify / YouTube is active
   - Late-night reminders to sleep (after 1:00 AM)
   - Long uptime marathon observations
2. Genuine Science & Technology Trivia:
   - Spider silk biomechanics & polymer tensile strength
   - Algorithmic complexity, memory management & computing history
   - Physics, material science (graphene, quantum quirks)
3. Neighborhood Patrol & Lab Partner Banter:
   - Friendly jokes about Tony Stark's toys, Aunt May, Daily Bugle, and desktop guard duty.
"""

from __future__ import annotations

import datetime
import random
import time
from typing import List, Optional

from abilities.media_sensor import get_now_playing
from abilities.system_sensor import get_hardware_specs


# ==============================================================================
# SCIENCE & TECH TRIVIA BANK
# ==============================================================================
SCIENCE_TRIVIA: List[str] = [
    "¿Sabías que la seda arácnida real de Nephila clavipes tiene una resistencia a la tracción superior al acero de alta aleación y es 5 veces más ligera? De ahí saqué la fórmula de mis telarañas.",
    "Dato científico: si un algoritmo tiene complejidad exponencial O(2^n), ni con todos los supercomputadores de Industrias Stark terminaría de calcular en la vida del universo.",
    "¿Sabías que las arañas saltarinas no usan músculos para estirar las patas, sino un sistema hidráulico de presión sanguínea? Por eso saltan 50 veces su longitud corporal.",
    "Curiosidad de laboratorio: el primer 'bug' informático de la historia fue literalmente una polilla real atrapada en el relé del ordenador Mark II en 1947.",
    "La ley de conservación del momento lineal es lo único que evita que me estrelle contra un muro cada vez que suelto una red a 80 km/h por Queens.",
    "¿Sabías que el grafeno es un alótropo del carbono de un solo átomo de espesor, pero es 200 veces más resistente que el acero estructural?",
    "Dato biofísico: un solo gramo de ADN puede almacenar teóricamente hasta 215 petabytes de información... Tony Stark sigue intentando superarlo en su torre.",
    "Los tardígrados pueden sobrevivir al vacío del espacio exterior, a presiones extremas y a temperaturas cercanas al cero absoluto mediante criptobiosis. Esos bichos sí son héroes.",
    "¿Sabías que la luz tarda aproximadamente 8 minutos y 20 segundos en viajar desde el Sol hasta tu pantalla? Cuando miras el amanecer, ves el pasado.",
    "En física cuántica, el entrelazamiento cuántico permite que dos partículas conectadas cambien de estado al instante sin importar la distancia. Einstein lo llamaba 'acción fantasmal a distancia'."
]

# ==============================================================================
# LAB PARTNER & PATROL BANTER
# ==============================================================================
PATROL_BANTER: List[str] = [
    "Patrulla de escritorio tranquila... Ni rastro del Duende Verde ni de los secuaces de Kingpin por tus carpetas.",
    "Aquí sigo haciendo guardia en tu barra de tareas por si asoma algún bug rebelde o un supervillano cibernético.",
    "Tranquilo, socio. Si se cuela algún malware en este sector, lo dejo envuelto en una red de polímeros antes de que toque la CPU.",
    "Tengo el sentido arácnido en reposo total. Buen momento para seguir picando código o tomarnos un respiro.",
    "¿Has probado compilar a las 3 de la mañana con tía May recordándote la cena? Te aseguro que eso sí es presión.",
    "Si Jameson viera que paso la tarde patrullando tu pantalla en lugar de sacarme fotos, me bajaba el sueldo... si es que me pagara algo decente.",
    "Tu escritorio está más ordenado que mi laboratorio en la Universidad Empire State. Buen trabajo manteniendo el orden, compañero.",
    "Me encanta esta vista desde aquí arriba. Mucho mejor que esquivar taxis amarillos por la Quinta Avenida."
]


_LAST_PICKED: Optional[str] = None


def get_spontaneous_chatter() -> str:
    """
    Selects a highly contextual, in-character spoken line based on current machine state.
    """
    global _LAST_PICKED

    now = datetime.datetime.now()
    hour = now.hour

    # 1. Late night check (between 1:00 AM and 5:30 AM)
    if (hour >= 1 and hour < 6) and random.random() < 0.65:
        late_lines = [
            f"Oye socio, son las {now.strftime('%H:%M')} de la madrugada... Hasta los Vengadores duermen para recargar cartuchos.",
            "Mi sentido arácnido me dice que llevas demasiadas horas frente a la pantalla esta noche. ¿Qué tal un buen descanso?",
            "¿Compilando a estas horas? Tía May ya nos habría apagado los plomos del taller. No te desveles demasiado, colega."
        ]
        return random.choice(late_lines)

    # 2. Real-time media listening check
    try:
        media = get_now_playing()
        if media.get("playing") and media.get("title") and random.random() < 0.55:
            track = media["title"]
            artist = f" de {media['artist']}" if media.get("artist") else ""
            music_lines = [
                f"Ese tema que tienes sonando ('{track}'{artist}) tiene un ritmo genial para balancearse por los tejados.",
                f"Buena elección de música en el laboratorio ('{track}'). Ayuda a concentrarse en los cálculos.",
                f"Viendo tu lista de reproducción ('{track}')... veo que tienes buen gusto para amenizar la guardia."
            ]
            return random.choice(music_lines)
    except Exception:
        pass

    # 3. Hardware load alerts
    try:
        specs = get_hardware_specs()
        ram_pct = specs["ram"]["usage_pct"]
        if ram_pct > 80.0 and random.random() < 0.60:
            return f"Oye socio, la memoria RAM está al {ram_pct}% de carga. Asegúrate de cerrar procesos pesados si notas tirones."

        uptime_str = specs.get("uptime", "")
        if "12h" in uptime_str or "18h" in uptime_str or "24h" in uptime_str:
            if random.random() < 0.40:
                return f"Llevamos {uptime_str} de sesión continua con el equipo. ¡Vaya maratón científico nos estamos pegando hoy!"
    except Exception:
        pass

    # 4. Alternating between Science Trivia and Patrol Banter
    pool = SCIENCE_TRIVIA if random.random() < 0.50 else PATROL_BANTER
    candidates = [line for line in pool if line != _LAST_PICKED]
    picked = random.choice(candidates) if candidates else pool[0]
    _LAST_PICKED = picked
    return picked
