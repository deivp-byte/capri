"""
tests/test_conversational_continuity.py - Comprehensive Multi-Turn Continuity & Semantic Flexibility Tests
Verifies that:
1. Pronouns, clitics, deictic references, and ellipses are resolved accurately across turns.
2. Natural, colloquial Spanish phrasings (without rigid keywords) are understood smoothly.
3. Spider-Man maintains context across weather, files, projects, and folders.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from abilities.universal_intent_pipeline import (
    ConversationContext,
    contextualize_query,
    resolve_universal_work_order,
    extract_slots,
)
from brain import _detect_action_intent


class TestConversationalContinuity(unittest.TestCase):
    """Tests multi-turn context tracking, anaphora resolution, and flexible phrasing."""

    def setUp(self):
        self.context = ConversationContext()

    def test_weather_multi_turn_continuity(self):
        """
        Turn 1: 'dime el tiempo actual en vic'
        Turn 2: '¿y lloverá allí?' (locative deictic 'allí' -> Vic)
        Turn 3: '¿y en Madrid?' (prepositional ellipsis -> weather Madrid)
        """
        # Turn 1
        t1 = "dime el tiempo actual en vic"
        order1 = resolve_universal_work_order(t1, self.context)
        self.assertIsNotNone(order1)
        self.assertEqual(order1["action"], "get_weather")
        self.assertEqual(order1["params"]["city"].lower(), "vic")

        # Simulate turn 1 execution updating context
        self.context.update_from_work_order(
            "get_weather",
            {"city": "Vic"},
            "Status: Tiempo meteorológico real en Vic: 14°C, Nublado, Probabilidad de lluvia: 15%."
        )
        self.assertEqual(self.context.active_city, "Vic")
        self.assertEqual(self.context.active_topic, "weather")

        # Turn 2: '¿y lloverá allí?'
        t2 = "¿y lloverá allí?"
        rewritten_t2, meta2 = contextualize_query(t2, self.context)
        self.assertIn("vic", rewritten_t2.lower())
        order2 = resolve_universal_work_order(t2, self.context)
        self.assertIsNotNone(order2)
        self.assertEqual(order2["action"], "get_weather")
        self.assertEqual(order2["params"]["city"].lower(), "vic")

        # Turn 3: '¿y en Madrid?'
        t3 = "¿y en Madrid?"
        rewritten_t3, meta3 = contextualize_query(t3, self.context)
        self.assertIn("madrid", rewritten_t3.lower())
        order3 = resolve_universal_work_order(t3, self.context)
        self.assertIsNotNone(order3)
        self.assertEqual(order3["action"], "get_weather")
        self.assertEqual(order3["params"]["city"].lower(), "madrid")

    def test_file_multi_turn_clitics(self):
        """
        Turn 1: 'crea un archivo notas.txt con el texto hola mundo'
        Turn 2: 'bórralo' (clitic '-lo' -> notas.txt)
        """
        # Turn 1
        t1 = "crea un archivo notas.txt con el texto hola mundo"
        order1 = resolve_universal_work_order(t1, self.context)
        self.assertIsNotNone(order1)
        self.assertEqual(order1["action"], "create_file")
        self.assertIn("notas.txt", order1["params"]["target"])

        # Simulate execution
        self.context.update_from_work_order(
            "create_file",
            {"target": "notas.txt"},
            "Status: File 'notas.txt' created successfully."
        )
        self.assertEqual(self.context.active_file, "notas.txt")
        self.assertEqual(self.context.active_topic, "file")

        # Turn 2: 'bórralo'
        t2 = "bórralo"
        rewritten_t2, meta2 = contextualize_query(t2, self.context)
        self.assertIn("notas.txt", rewritten_t2)
        order2 = resolve_universal_work_order(t2, self.context)
        self.assertIsNotNone(order2)
        self.assertEqual(order2["action"], "delete_file_safely")
        self.assertIn("notas.txt", order2["params"]["target"])

    def test_file_read_and_edit_clitics(self):
        """
        Tests 'léelo' and 'edítalo y pon terminar tarea' with active_file.
        """
        self.context.active_file = "C:\\Archivos\\tarea.txt"
        self.context.active_topic = "file"

        # Read clitic
        order_read = resolve_universal_work_order("léelo", self.context)
        self.assertIsNotNone(order_read)
        self.assertEqual(order_read["action"], "read_file")
        self.assertEqual(order_read["params"]["target"], "C:\\Archivos\\tarea.txt")

        # Edit clitic
        order_edit = resolve_universal_work_order("edítalo y pon terminar tarea", self.context)
        self.assertIsNotNone(order_edit)
        self.assertEqual(order_edit["action"], "edit_file")
        self.assertEqual(order_edit["params"]["target"], "C:\\Archivos\\tarea.txt")
        self.assertIn("terminar tarea", order_edit["params"]["append_text"])

    def test_project_multi_turn_continuity(self):
        """
        Turn 1: 'analiza el proyecto capri'
        Turn 2: '¿cómo lo mejorarías?' (references capri)
        Turn 3: 'pasa los tests'
        """
        # Turn 1
        t1 = "analiza el proyecto capri"
        order1 = resolve_universal_work_order(t1, self.context)
        self.assertIsNotNone(order1)
        self.assertEqual(order1["action"], "inspect_project")
        self.assertEqual(order1["params"]["target"], "capri")

        # Simulate execution
        self.context.update_from_work_order(
            "inspect_project",
            {"target": "capri"},
            "Status: Project capri scanned: 25 files, architecture OK."
        )
        self.assertEqual(self.context.active_project, "capri")
        self.assertEqual(self.context.active_topic, "project")

        # Turn 2: '¿cómo lo mejorarías?'
        t2 = "¿cómo lo mejorarías?"
        rewritten_t2, meta2 = contextualize_query(t2, self.context)
        self.assertIn("capri", rewritten_t2)
        order2 = resolve_universal_work_order(t2, self.context)
        self.assertIsNotNone(order2)
        self.assertEqual(order2["action"], "brainstorm_project_ideas")
        self.assertEqual(order2["params"]["target"], "capri")

        # Turn 3: 'pasa los tests'
        t3 = "pasa los tests"
        order3 = resolve_universal_work_order(t3, self.context)
        self.assertIsNotNone(order3)
        self.assertEqual(order3["action"], "run_code_check")

    def test_folder_multi_turn_continuity(self):
        """
        Turn 1: 'abre la carpeta descargas'
        Turn 2: '¿qué hay dentro?'
        """
        t1 = "abre la carpeta descargas"
        self.context.update_from_work_order(
            "open_folder",
            {"target": "descargas"},
            "Status: Folder descargas opened."
        )
        self.assertEqual(self.context.active_folder, "descargas")

        t2 = "¿qué hay dentro?"
        rewritten_t2, meta2 = contextualize_query(t2, self.context)
        self.assertIn("descargas", rewritten_t2)
        order2 = resolve_universal_work_order(t2, self.context)
        self.assertIsNotNone(order2)
        self.assertEqual(order2["action"], "list_folder")

    def test_flexible_natural_phrasing(self):
        """
        Tests colloquial and varied phrasings without rigid keywords.
        """
        # Weather variations
        order_w1 = resolve_universal_work_order("qué tal el cielo en vic")
        self.assertIsNotNone(order_w1)
        self.assertEqual(order_w1["action"], "get_weather")
        self.assertEqual(order_w1["params"]["city"].lower(), "vic")

        order_w2 = resolve_universal_work_order("hace frío en barcelona")
        self.assertIsNotNone(order_w2)
        self.assertEqual(order_w2["action"], "get_weather")
        self.assertEqual(order_w2["params"]["city"].lower(), "barcelona")

        # File create variation: 'tírame un archivo llamado test.txt con ok'
        order_f1 = resolve_universal_work_order("tírame un archivo llamado test.txt con el texto ok")
        self.assertIsNotNone(order_f1)
        self.assertEqual(order_f1["action"], "create_file")

        # Safe delete variation: 'cárgate el archivo temp.txt'
        order_f2 = resolve_universal_work_order("cárgate el archivo temp.txt")
        self.assertIsNotNone(order_f2)
        self.assertEqual(order_f2["action"], "delete_file_safely")
        self.assertEqual(order_f2["params"]["target"], "temp.txt")

        # Project inspection variation: 'échale un ojo al proyecto capri'
        order_p1 = resolve_universal_work_order("échale un ojo al proyecto capri")
        self.assertIsNotNone(order_p1)
        self.assertEqual(order_p1["action"], "inspect_project")
        self.assertEqual(order_p1["params"]["target"], "capri")

        # Real-time web research & live news queries
        order_n1 = resolve_universal_work_order("dime que noticias importantes han habido hoy en el mundo")
        self.assertIsNotNone(order_n1)
        self.assertEqual(order_n1["action"], "get_live_news")

        order_n2 = resolve_universal_work_order("que sabes sobre la reciente caida de Nvidia?")
        self.assertIsNotNone(order_n2)
        self.assertEqual(order_n2["action"], "smart_web_research")
        self.assertIn("nvidia", order_n2["params"]["query"].lower())


if __name__ == "__main__":
    unittest.main()
