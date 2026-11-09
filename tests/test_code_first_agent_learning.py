import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
test_code_first_agent_learning.py - Comprehensive verification suite for:
1. Code-First Hybrid Routing (A donde no llega el modelo, llega el código).
2. Developer Assistant & Code Intelligence (inspect_project, analyze_code, brainstorm_ideas, run_code_check).
3. Full File Lifecycle Management (create_file, create_folder, edit_file, delete_file_safely with safe trash).
4. Adaptive Pattern Learning (learn_pattern, list_learned_patterns, habit tracking, rule matching).
"""

import sys
import shutil
from pathlib import Path
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from abilities.file_explorer import (
    create_file,
    create_folder,
    edit_file,
    delete_file_safely,
    read_file_preview,
    TRASH_DIR,
)
from abilities.dev_assistant import (
    inspect_project,
    analyze_code,
    brainstorm_project_ideas,
    run_code_check,
)
from abilities.pattern_learning import (
    get_pattern_learner,
    learn_pattern,
    list_learned_patterns,
)
from abilities.smart_intent import (
    parse_file_or_folder_request,
    parse_developer_and_pattern_request,
)
from brain import _detect_action_intent


def test_file_lifecycle_operations():
    print("\n[1] Testing Full File Lifecycle Operations (Create, Edit, Delete safely)...")
    test_file_path = Path("test_sandbox_dummy.txt")
    test_folder_path = Path("test_sandbox_dummy_folder")

    # Clean up if leftover
    if test_file_path.exists():
        test_file_path.unlink()
    if test_folder_path.exists():
        shutil.rmtree(test_folder_path)

    # 1. Create file
    create_res = create_file(str(test_file_path), content="line 1: initial content\nline 2: dev code")
    assert "creado con éxito" in create_res, f"Failed create_file: {create_res}"
    assert test_file_path.exists(), "test_file_path does not exist on disk"
    print("  create_file: OK")

    # 2. Create folder
    create_dir_res = create_folder(str(test_folder_path))
    assert "creada con éxito" in create_dir_res, f"Failed create_folder: {create_dir_res}"
    assert test_folder_path.exists() and test_folder_path.is_dir(), "folder does not exist"
    print("  create_folder: OK")

    # 3. Edit file (append)
    edit_res = edit_file(str(test_file_path), append_text="line 3: appended via code")
    assert "modificado correctamente" in edit_res, f"Failed edit_file: {edit_res}"
    content = test_file_path.read_text(encoding="utf-8")
    assert "appended via code" in content, "Append text missing from file"
    assert test_file_path.with_suffix(".txt.bak").exists(), "Backup file not created"
    print("  edit_file (append + backup): OK")

    # 4. Safe deletion to Capri Trash
    del_res = delete_file_safely(str(test_file_path))
    assert "movido con éxito a la papelera segura" in del_res, f"Failed delete_file_safely: {del_res}"
    assert not test_file_path.exists(), "File still exists after safe deletion"
    assert TRASH_DIR.exists(), "Trash dir missing"
    print("  delete_file_safely (quarantined in .capri_trash): OK")

    # Clean up test artifacts
    bak = test_file_path.with_suffix(".txt.bak")
    if bak.exists():
        bak.unlink()
    if test_folder_path.exists():
        delete_file_safely(str(test_folder_path))


def test_developer_assistant():
    print("\n[2] Testing Developer Assistant & Code Intelligence Engine...")
    
    # 1. Project inspection
    insp = inspect_project("capri")
    assert "Inspección de proyecto completada" in insp, f"Failed inspect_project: {insp}"
    assert "Python" in insp, "Python language missing from inspection"
    print("  inspect_project: OK")

    # 2. AST Code Analysis
    ast_res = analyze_code("persona.py")
    assert "Análisis de código para 'persona.py'" in ast_res, f"Failed analyze_code: {ast_res}"
    assert "sintaxis válida" in ast_res, "Expected syntax to be valid"
    print("  analyze_code (AST parsing & symbol extraction): OK")

    # 3. Project Brainstorm Ideas
    ideas = brainstorm_project_ideas("capri", query="arquitectura y estabilidad")
    assert "Ideas de desarrollo y arquitectura" in ideas, f"Failed brainstorm_ideas: {ideas}"
    assert "enrutamiento determinista" in ideas.lower(), "Expected architecture suggestions"
    print("  brainstorm_project_ideas: OK")

    # 4. Run Code Check / Syntax verification
    check_res = run_code_check("persona.py")
    assert "100% válida" in check_res, f"Syntax check failed: {check_res}"
    print("  run_code_check: OK")


def test_pattern_learning_engine():
    print("\n[3] Testing Adaptive Pattern Learning Engine...")
    learner = get_pattern_learner()

    # 1. Learn project location
    res_proj = learn_pattern(kind="project", name="test_repo", value=str(Path.cwd()))
    assert "Patrón aprendido" in res_proj, f"Failed learn project: {res_proj}"
    resolved = learner.resolve_project_path("test_repo")
    assert resolved == Path.cwd().resolve(), f"Resolved path mismatch: {resolved}"
    print("  learn_project_path: OK")

    # 2. Learn preference
    res_pref = learn_pattern(kind="preference", name="code_style", value="Strict typing & Clean Architecture")
    assert "Preferencia aprendida" in res_pref, f"Failed learn preference: {res_pref}"
    val = learner.get_preference("code_style")
    assert "Strict typing" in val
    print("  learn_preference: OK")

    # 3. Learn rule
    res_rule = learner.learn_rule(trigger_phrase="modo hackear", target_action="inspect_project", target_params={"target": "capri"})
    assert "Regla aprendida con éxito" in res_rule, f"Failed learn rule: {res_rule}"
    matched = learner.match_learned_rule("modo hackear")
    assert matched is not None and matched[0] == "inspect_project"
    print("  learn_rule: OK")

    # 4. Habit recording
    learner.record_usage("inspect_project")
    habits = learner.get_top_habits()
    assert len(habits) > 0
    print("  record_usage & get_top_habits: OK")

    # 5. Summary
    summ = list_learned_patterns()
    assert "Resumen de aprendizaje de Capri" in summ
    print("  list_learned_patterns: OK")


def test_smart_intent_routing():
    print("\n[4] Testing Deterministic Fast-Path Intent Routing...")

    # Developer intents
    c1 = _detect_action_intent("analiza el proyecto capri")
    assert c1 is not None and c1.function.name == "inspect_project", f"Unexpected: {c1}"
    print("  'analiza el proyecto capri' -> inspect_project OK")

    c2 = _detect_action_intent("inspecciona el proyecto")
    assert c2 is not None and c2.function.name == "inspect_project", f"Unexpected: {c2}"
    print("  'inspecciona el proyecto' -> inspect_project OK")

    c3 = _detect_action_intent("analiza el código de persona.py")
    assert c3 is not None and c3.function.name == "analyze_code", f"Unexpected: {c3}"
    print("  'analiza el código de persona.py' -> analyze_code OK")

    c4 = _detect_action_intent("qué hace config.py")
    assert c4 is not None and c4.function.name == "analyze_code", f"Unexpected: {c4}"
    print("  'qué hace config.py' -> analyze_code OK")

    c5 = _detect_action_intent("dame ideas para el proyecto")
    assert c5 is not None and c5.function.name == "brainstorm_project_ideas", f"Unexpected: {c5}"
    print("  'dame ideas para el proyecto' -> brainstorm_project_ideas OK")

    c6 = _detect_action_intent("comprueba el código")
    assert c6 is not None and c6.function.name == "run_code_check", f"Unexpected: {c6}"
    print("  'comprueba el código' -> run_code_check OK")

    # Pattern learning intents
    c7 = _detect_action_intent("qué patrones has aprendido")
    assert c7 is not None and c7.function.name == "list_learned_patterns", f"Unexpected: {c7}"
    print("  'qué patrones has aprendido' -> list_learned_patterns OK")

    c8 = _detect_action_intent("recuerda que mi proyecto web está en C:/proyectos/web")
    assert c8 is not None and c8.function.name == "learn_pattern", f"Unexpected: {c8}"
    print("  'recuerda que mi proyecto web está en C:/proyectos/web' -> learn_pattern OK")

    # File lifecycle intents
    c9 = _detect_action_intent("crea un archivo llamado notas.txt con el texto hola mundo")
    assert c9 is not None and c9.function.name == "create_file", f"Unexpected: {c9}"
    print("  'crea un archivo llamado notas.txt con el texto hola mundo' -> create_file OK")

    c10 = _detect_action_intent("crea la carpeta test_dev")
    assert c10 is not None and c10.function.name == "create_folder", f"Unexpected: {c10}"
    print("  'crea la carpeta test_dev' -> create_folder OK")

    c11 = _detect_action_intent("edita el archivo notas.txt y añade más tareas")
    assert c11 is not None and c11.function.name == "edit_file", f"Unexpected: {c11}"
    print("  'edita el archivo notas.txt y añade más tareas' -> edit_file OK")

    # Exact user query cases verification
    c13 = _detect_action_intent("dime que patrones has analizado")
    assert c13 is not None and c13.function.name == "list_learned_patterns", f"Unexpected: {c13}"
    print("  'dime que patrones has analizado' -> list_learned_patterns OK")

    c14 = _detect_action_intent('crea un archivo .txt diciendo hola en esta direccion "C:\\Archivos\\Nueva carpeta"')
    assert c14 is not None and c14.function.name == "create_file", f"Unexpected: {c14}"
    assert "C:\\Archivos\\Nueva carpeta" in c14.function.arguments["target"]
    assert c14.function.arguments["content"] == "hola"
    print("  'crea un archivo .txt diciendo hola en esta direccion \"C:\\Archivos\\Nueva carpeta\"' -> create_file OK")


if __name__ == "__main__":
    test_file_lifecycle_operations()
    test_developer_assistant()
    test_pattern_learning_engine()
    test_smart_intent_routing()
    print("\n=======================================================")
    print("  >>> ALL HYBRID AGENT & LEARNING TESTS PASSED 100%! <<<")
    print("=======================================================")
