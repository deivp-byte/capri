"""
abilities/dev_assistant.py - Developer Assistant & Code Intelligence Engine for Capri

Provides high-speed local code comprehension, project exploration, architectural brainstorming,
and syntax verification for software development workflows.
Works completely offline without external APIs, designed to keep token consumption minimal
for local SLMs while delivering deep deterministic code insights.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import BASE_DIR
from abilities.pattern_learning import get_pattern_learner


# Common ignore directories for repo scanning
IGNORED_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", ".idea",
    ".vscode", "dist", "build", ".pytest_cache", ".mypy_cache", ".tox",
    "coverage", ".next", ".nuxt", "bin", "obj", ".cargo", "target"
}

# Recognized programming languages by extension
EXT_LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React JSX",
    ".tsx": "React TSX",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".rs": "Rust",
    ".go": "Go",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".java": "Java",
    ".kt": "Kotlin",
    ".php": "PHP",
    ".rb": "Ruby",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
}


def _resolve_target_project(target: str = "") -> Path:
    """Resolves target string to a project directory using pattern memory or filesystem."""
    clean = (target or "").strip()
    learner = get_pattern_learner()

    if not clean or clean.lower() in ("actual", "aqui", "este", "capri", "workspace"):
        return BASE_DIR

    # 1. Check learned project locations
    resolved = learner.resolve_project_path(clean)
    if resolved and resolved.exists():
        return resolved

    # 2. Check direct path
    p = Path(clean).expanduser().resolve()
    if p.exists() and p.is_dir():
        return p

    # 3. Check sibling in Personal_Projects or parent
    if BASE_DIR.parent.exists():
        cand = BASE_DIR.parent / clean
        if cand.exists() and cand.is_dir():
            return cand.resolve()

    return BASE_DIR


def inspect_project(target: str = "", max_depth: int = 2) -> str:
    """
    Inspects a project repository: detects languages, frameworks, entrypoints,
    git status, and builds a concise architectural file map.

    Args:
        target: Project name, alias, or path. Defaults to current project.
        max_depth: Maximum directory tree depth to display.
    """
    proj_dir = _resolve_target_project(target)
    if not proj_dir.exists():
        return f"Status: Error - No se encontró el proyecto en '{target}'."

    proj_name = proj_dir.name
    lang_counts: Dict[str, int] = {}
    total_files = 0
    frameworks_detected = []
    entrypoints = []

    # 1. Detect Frameworks & Tools
    has_git = (proj_dir / ".git").exists()
    has_reqs = (proj_dir / "requirements.txt").exists()
    has_pyproj = (proj_dir / "pyproject.toml").exists()
    has_pkg = (proj_dir / "package.json").exists()
    has_cargo = (proj_dir / "Cargo.toml").exists()

    if (proj_dir / "package.json").exists():
        try:
            pkg_data = json.loads((proj_dir / "package.json").read_text(encoding="utf-8", errors="ignore"))
            deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            if "react" in deps: frameworks_detected.append("React")
            if "next" in deps: frameworks_detected.append("Next.js")
            if "vue" in deps: frameworks_detected.append("Vue")
            if "electron" in deps: frameworks_detected.append("Electron")
            if "express" in deps: frameworks_detected.append("Express")
        except Exception:
            pass

    # Scan python dependencies
    if has_reqs:
        try:
            req_text = (proj_dir / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
            if "fastapi" in req_text: frameworks_detected.append("FastAPI")
            if "flask" in req_text: frameworks_detected.append("Flask")
            if "django" in req_text: frameworks_detected.append("Django")
            if "pyside6" in req_text or "pyqt" in req_text: frameworks_detected.append("PySide/Qt GUI")
            if "ollama" in req_text: frameworks_detected.append("Ollama AI")
            if "torch" in req_text: frameworks_detected.append("PyTorch")
        except Exception:
            pass

    # 2. Build Tree and Count Files
    tree_lines = []

    def scan_tree(current_dir: Path, depth: int, prefix: str = ""):
        nonlocal total_files
        if depth > max_depth:
            return

        try:
            entries = sorted(current_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return

        visible = [e for e in entries if e.name not in IGNORED_DIRS and not e.name.startswith(".")]

        for idx, entry in enumerate(visible):
            is_last = (idx == len(visible) - 1)
            connector = "\\-- " if is_last else "|-- "
            new_prefix = prefix + ("    " if is_last else "|   ")

            if entry.is_dir():
                tree_lines.append(f"{prefix}{connector}{entry.name}/")
                scan_tree(entry, depth + 1, new_prefix)
            else:
                total_files += 1
                ext = entry.suffix.lower()
                lang = EXT_LANG_MAP.get(ext, "Otro")
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

                # Check if entrypoint
                if entry.name.lower() in ("main.py", "app.py", "body.py", "index.js", "index.ts", "server.js"):
                    entrypoints.append(entry.name)

                if depth <= 1:
                    tree_lines.append(f"{prefix}{connector}{entry.name}")

    scan_tree(proj_dir, 0)

    # 3. Format Output
    top_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_langs_str = ", ".join([f"{l} ({c} archivos)" for l, c in top_langs]) if top_langs else "Sin archivos de código"
    frameworks_str = ", ".join(frameworks_detected) if frameworks_detected else "Estándar / Vanilla"
    entries_str = ", ".join(entrypoints) if entrypoints else "No detectado"

    report = [
        f"Status: Inspección de proyecto completada para '{proj_name}' ({proj_dir}):",
        f"- Lenguajes principales: {top_langs_str}",
        f"- Frameworks/Librerías clave: {frameworks_str}",
        f"- Puntos de entrada: {entries_str}",
        f"- Repositorio Git: {'Sí' if has_git else 'No'}",
        f"- Total archivos escaneados: {total_files}",
        f"\nEstructura de directorios principales:\n" + "\n".join(tree_lines[:25]),
    ]
    if len(tree_lines) > 25:
        report.append(f"... y {len(tree_lines) - 25} elementos más.")

    return "\n".join(report)


def analyze_code(target: str = "", symbol: str = "") -> str:
    """
    Reads a code file and extracts high-level structural intelligence:
    classes, methods, functions, docstrings, imports, lines count, and syntax validation.

    Args:
        target: Path or filename of the code file to analyze.
        symbol: Optional specific function or class name to inspect in detail.
    """
    clean_target = (target or "").strip()
    if not clean_target:
        return "Status: Error - No se indicó el archivo a analizar."

    # Resolve file path
    file_path = Path(clean_target).expanduser().resolve()
    if not file_path.exists():
        # Try finding in current workspace
        cand = BASE_DIR / clean_target
        if cand.exists():
            file_path = cand
        else:
            from abilities.file_explorer import find_files
            search = find_files(clean_target, max_results=1)
            if search.get("matches"):
                file_path = Path(search["matches"][0])

    if not file_path.exists() or file_path.is_dir():
        return f"Status: Error - El archivo '{clean_target}' no existe o es un directorio."

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Status: Error al leer '{file_path.name}': {e}"

    lines = content.splitlines()
    total_lines = len(lines)
    ext = file_path.suffix.lower()

    # Python AST Analysis
    if ext == ".py":
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError as syn_err:
            return (
                f"Status: ⚠️ Error de sintaxis detectado en '{file_path.name}':\n"
                f"- Línea {syn_err.lineno}: {syn_err.msg}\n"
                f"- Texto: {syn_err.text.strip() if syn_err.text else 'N/A'}"
            )

        classes: List[str] = []
        functions: List[str] = []
        imports: List[str] = []
        selected_symbol_detail: Optional[str] = None

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or "Sin docstring"
                methods = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                c_str = f"Clase `{node.name}` ({len(methods)} métodos: {', '.join(methods[:5])})"
                classes.append(c_str)
                if symbol and symbol.lower() == node.name.lower():
                    selected_symbol_detail = f"Clase `{node.name}`\nDocstring: {doc}\nMétodos: {', '.join(methods)}"

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node) or ""
                args = [a.arg for a in node.args.args]
                sig = f"{node.name}({', '.join(args)})"
                functions.append(sig)
                if symbol and symbol.lower() == node.name.lower():
                    selected_symbol_detail = f"Función `{sig}`\nDocstring: {doc or 'Sin docstring'}"

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                imports.append(mod)

        if selected_symbol_detail:
            return f"Status: Detalle del símbolo solicitado en '{file_path.name}':\n{selected_symbol_detail}"

        unique_imports = sorted(list(set(imports)))[:10]
        report = [
            f"Status: Análisis de código para '{file_path.name}' ({total_lines} líneas de Python, sintaxis válida):",
            f"- Módulos importados ({len(unique_imports)}): {', '.join(unique_imports) if unique_imports else 'Ninguno'}",
            f"- Clases detectadas ({len(classes)}): {'; '.join(classes[:5]) if classes else 'Ninguna'}",
            f"- Funciones principales ({len(functions)}): {'; '.join(functions[:8]) if functions else 'Ninguna'}",
        ]
        return "\n".join(report)

    else:
        # Non-python generic regex summary
        func_matches = re.findall(r'(?:function|def|fn|pub fn|func)\s+([a-zA-Z0-9_]+)\s*\(', content)
        class_matches = re.findall(r'(?:class|struct|interface|type)\s+([a-zA-Z0-9_]+)', content)
        report = [
            f"Status: Archivo '{file_path.name}' ({EXT_LANG_MAP.get(ext, 'Texto')}, {total_lines} líneas):",
            f"- Clases/Estructuras: {', '.join(class_matches[:6]) if class_matches else 'No detectadas'}",
            f"- Funciones detectadas: {', '.join(func_matches[:8]) if func_matches else 'No detectadas'}",
            f"\nPrimeras 20 líneas:\n" + "\n".join(lines[:20])
        ]
        return "\n".join(report)


def brainstorm_project_ideas(target: str = "", query: str = "") -> str:
    """
    Generates intelligent architecture, refactoring, and feature ideas for projects.
    Combines project inspection with developer best practices.
    """
    proj_dir = _resolve_target_project(target)
    proj_name = proj_dir.name
    learner = get_pattern_learner()

    # Inspect context
    insp = inspect_project(str(proj_dir), max_depth=1)
    user_prefs = learner.data.get("preferences", {})
    clean_q = (query or "").strip().lower()

    ideas = [
        f"Status: Ideas de desarrollo y arquitectura para el proyecto '{proj_name}':",
        "",
        "1. [Arquitectura y Estabilidad]:",
        "   - Capa de enrutamiento determinista: asegurar que acciones críticas (archivos, llamadas al SO, atajos) se ejecuten en código directo (~0ms) para garantizar 100% de fiabilidad sin depender de la inferencia del modelo.",
        "   - Aislamiento de capas: mantener la interfaz gráfica (UI), los sensores del sistema y el motor de intents en módulos desacoplados con contratos tipados (dataclasses / pydantic).",
        "",
        "2. [Rendimiento y Optimización para Modelos Locales]:",
        "   - Ephemeral Context Ingestion: pasar al SLM únicamente fragmentos sintetizados y relevantes (evitando pasar archivos enteros para no saturar el contexto de 2048 tokens).",
        "   - Caché y Vault de Patrones: almacenar en JSON local las rutas habituales, estilos de código y respuestas a problemas recurrentes para reusarlos al instante.",
        "",
        "3. [Nuevas Capacidades de Agente Desarrollador]:",
        "   - Verificación estática antes de ejecutar: compilar con `py_compile` o `ast.parse` cualquier código generado para corregir errores antes de que el usuario los note.",
        "   - Safe Trash Lifecycle: nunca borrar archivos de raíz; enviar a papelera reversible con log de trazabilidad.",
        "   - Soporte para ejecución de tests automáticos en un click cuando el usuario guarde cambios.",
    ]

    if clean_q:
        ideas.append(f"\n[Enfoque específico solicitado sobre '{query}']:\n"
                     f"- Sugerencia adaptada: Crear una función auxiliar modular en `abilities/` con tests dedicados en `test_*.py`.")

    return "\n".join(ideas)


def run_code_check(target: str = "") -> str:
    """
    Compiles Python code or runs tests to verify code integrity without crashing.
    """
    clean_target = (target or "").strip()
    target_path = BASE_DIR / clean_target if clean_target else BASE_DIR

    if target_path.is_file() and target_path.suffix == ".py":
        # Check single file syntax
        try:
            import py_compile
            py_compile.compile(str(target_path), doraise=True)
            return f"Status: Sintaxis de '{target_path.name}' 100% válida. Sin errores de compilación."
        except py_compile.PyCompileError as e:
            return f"Status: ⚠️ Error de sintaxis en '{target_path.name}': {e.msg}"

    # Run quick unittest discover
    try:
        venv_py = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        cmd = [str(venv_py) if venv_py.exists() else sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
        res = subprocess.run(cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=12)
        output = (res.stdout + "\n" + res.stderr).strip()
        last_lines = "\n".join(output.splitlines()[-4:])
        if res.returncode == 0:
            return f"Status: Tests ejecutados con éxito:\n{last_lines}"
        else:
            return f"Status: Resultado de tests (código {res.returncode}):\n{last_lines}"
    except subprocess.TimeoutExpired:
        return "Status: Advertencia - La ejecución de tests tardó más de 12 segundos y fue detenida."
    except Exception as err:
        return f"Status: Error al ejecutar pruebas: {err}"
