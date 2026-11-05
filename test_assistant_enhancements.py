"""
test_assistant_enhancements.py - Verification suite for:
1. Deep file system navigation (open_folder, list_folder, find_files, read_file).
2. Proactive Care & Activity Advisor (CareAdvisor, ergonomics, system stress, window context).
3. Natural Spanish intent routing for assistant commands.
"""

import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from abilities.file_explorer import (
    resolve_path,
    open_folder,
    list_folder_contents,
    find_files,
    search_and_format_files,
    read_file_preview,
)
from abilities.care_advisor import get_proactive_advice, CareAdvisor
from abilities.smart_intent import parse_file_or_folder_request
from brain import _detect_action_intent


def test_file_explorer_capabilities():
    print("[1] Testing file explorer resolution and capabilities...")
    # Known folders
    down_path = resolve_path("descargas")
    assert down_path is not None and down_path.exists(), "Failed to resolve 'descargas'"
    print(f"  Resolved 'descargas': {down_path} OK")

    proj_path = resolve_path("proyecto")
    assert proj_path is not None and proj_path.exists(), "Failed to resolve 'proyecto'"
    print(f"  Resolved 'proyecto': {proj_path} OK")

    # List folder
    list_res = list_folder_contents("descargas", limit=5)
    assert "Status: Contenido de 'Downloads'" in list_res, f"Unexpected list result: {list_res}"
    print("  list_folder_contents: OK")

    # Find files
    search_res = find_files("config.json", max_results=3)
    assert search_res["count"] > 0, "Failed to find config.json"
    assert any("config.json" in m for m in search_res["matches"])
    print(f"  find_files found: {search_res['matches'][0]} OK")

    # Read file
    read_res = read_file_preview("data/config.json", max_chars=100)
    assert "Status: Contenido de 'config.json'" in read_res
    print("  read_file_preview: OK")


def test_care_advisor():
    print("[2] Testing proactive care & activity advisor...")
    advisor = CareAdvisor()
    # Forced advice
    adv = advisor.get_proactive_observation(force=True)
    assert adv is not None and len(adv) > 10, "Failed to get proactive advice"
    print(f"  Proactive advice generated: '{adv[:60]}...' OK")

    # Stress checks
    hw_stress = advisor._check_hardware_stress()
    print(f"  Hardware stress check ran safely (returned: {hw_stress is not None}) OK")


def test_assistant_semantic_intent_matching():
    print("[3] Testing natural language semantic intent matching for assistant tasks...")
    cases = [
        ("abre la carpeta descargas", "open_folder"),
        ("abre descargas", "open_folder"),
        ("abre el explorador de archivos", "open_folder"),
        ("abre la carpeta del proyecto", "open_folder"),
        ("qué hay en descargas", "list_folder"),
        ("qué tengo en documentos", "list_folder"),
        ("lista los archivos de descargas", "list_folder"),
        ("busca el archivo notas.txt en el ordenador", "find_files"),
        ("dónde está config.json", "find_files"),
        ("léeme el archivo config.json", "read_file"),
        ("dame un consejo", "care_advice"),
        ("cómo me ves", "care_advice"),
    ]

    for user_input, expected_act in cases:
        parsed = parse_file_or_folder_request(user_input)
        assert parsed is not None, f"Failed to parse '{user_input}'"
        assert parsed["action"] == expected_act, f"Expected {expected_act}, got {parsed['action']} for '{user_input}'"

        intent = _detect_action_intent(user_input)
        assert intent is not None, f"brain._detect_action_intent failed for '{user_input}'"
        print(f"  '{user_input}' -> {intent.function.name} OK")


if __name__ == "__main__":
    test_file_explorer_capabilities()
    test_care_advisor()
    test_assistant_semantic_intent_matching()
    print("\n[ALL ASSISTANT ENHANCEMENT TESTS PASSED 100%!]")
