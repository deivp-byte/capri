"""
abilities/file_explorer.py - Deep Windows File System Navigator & Finder
Inspired by capri-desktop-main FileFinder.cs & Files.cs architecture:
- Resolves known Windows folders (Downloads, Documents, Desktop, Pictures, Videos, Music, C:/Archivos, etc.)
- Opens folders directly in Windows File Explorer
- Reveals and highlights specific files using 'explorer.exe /select,"<path>"'
- Scans and lists folder contents with human-readable file sizes and types
- Performs fast, non-blocking breadth-first file searching across user libraries
- Safely reads file contents for AI analysis and summarization
"""

from __future__ import annotations

import os
import sys
import json
import subprocess
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ==============================================================================
# KNOWN SYSTEM FOLDERS & SPANISH ALIASES
# ==============================================================================

HOME_DIR = Path.home()
WORKSPACE_DIR = Path.cwd().resolve()

KNOWN_FOLDERS: Dict[str, Path] = {
    "downloads": HOME_DIR / "Downloads",
    "descargas": HOME_DIR / "Downloads",
    "desktop": HOME_DIR / "Desktop",
    "escritorio": HOME_DIR / "Desktop",
    "documents": HOME_DIR / "Documents",
    "documentos": HOME_DIR / "Documents",
    "mis documentos": HOME_DIR / "Documents",
    "pictures": HOME_DIR / "Pictures",
    "imagenes": HOME_DIR / "Pictures",
    "imágenes": HOME_DIR / "Pictures",
    "fotos": HOME_DIR / "Pictures",
    "videos": HOME_DIR / "Videos",
    "vídeos": HOME_DIR / "Videos",
    "musica": HOME_DIR / "Music",
    "música": HOME_DIR / "Music",
    "music": HOME_DIR / "Music",
    "home": HOME_DIR,
    "usuario": HOME_DIR,
    "user": HOME_DIR,
    "capri": WORKSPACE_DIR,
    "proyecto": WORKSPACE_DIR,
    "workspace": WORKSPACE_DIR,
    "archivos": Path("C:/Archivos") if Path("C:/Archivos").exists() else WORKSPACE_DIR.parent,
    "c": Path("C:/"),
}

# Directories to strictly skip during recursive search to avoid lags and permission errors
SKIP_DIRECTORIES = {
    "windows", "winsxs", "node_modules", "bower_components", ".git", ".svn",
    ".hg", ".cache", ".nuget", ".npm", ".pnpm-store", "__pycache__", ".venv",
    "venv", "$recycle.bin", "system volume information", "recovery", "config.msi",
    "temp", "cache", "caches", "code cache", "gpucache", "inetcache", "crashdumps"
}


def resolve_path(target: str) -> Optional[Path]:
    """
    Intelligently resolves a user query, folder alias, or raw path to a concrete Path object.
    Supports names like 'descargas', 'fotos', 'C:\\Archivos', '~/Documents', relative paths, etc.
    """
    clean = (target or "").strip().strip("\"'").lower()
    if not clean:
        return None

    # 1. Check known folder alias dictionary
    if clean in KNOWN_FOLDERS:
        candidate = KNOWN_FOLDERS[clean]
        if candidate.exists():
            return candidate

    # Strip prefixes like "carpeta de", "carpeta", "folder"
    for prefix in ("carpeta de ", "carpeta ", "folder de ", "folder ", "directorio de ", "directorio "):
        if clean.startswith(prefix):
            clean_sub = clean[len(prefix):].strip()
            if clean_sub in KNOWN_FOLDERS:
                candidate = KNOWN_FOLDERS[clean_sub]
                if candidate.exists():
                    return candidate

    # 2. Check direct path string (e.g. C:\Archivos, C:/Users/Omen/Desktop)
    try:
        raw_path = Path(os.path.expandvars(target.strip("\"'"))).expanduser()
        if raw_path.exists():
            return raw_path.resolve()
    except Exception:
        pass

    # 3. Check relative to current workspace or user home
    try:
        ws_candidate = (WORKSPACE_DIR / clean).resolve()
        if ws_candidate.exists():
            return ws_candidate
        home_candidate = (HOME_DIR / clean).resolve()
        if home_candidate.exists():
            return home_candidate
    except Exception:
        pass

    return None


def open_folder(target: str = "") -> str:
    """
    Opens a folder directly in Windows File Explorer, or reveals and selects a file.
    Args:
        target: Name or path of the folder (e.g. 'descargas', 'escritorio', 'C:/Archivos', 'proyecto').
    """
    if not target or target.strip().lower() in ("explorer", "explorador", "archivos"):
        # Open default explorer at user home or PC
        try:
            subprocess.Popen(["explorer.exe"], start_new_session=True)
            return "Status: Explorador de archivos de Windows abierto con éxito."
        except Exception as e:
            return f"Status: Error al abrir el Explorador: {e}"

    resolved = resolve_path(target)
    if not resolved:
        # If not directly resolved, try finding it
        search_res = find_files(target, max_results=1)
        if search_res and search_res.get("matches"):
            resolved = Path(search_res["matches"][0])

    if not resolved or not resolved.exists():
        return f"Status: Error - No se ha podido encontrar la carpeta o archivo '{target}' en el equipo."

    try:
        from abilities.window_manager import ensure_app_windowed
        if resolved.is_dir():
            # Open folder in windowed explorer
            subprocess.Popen(["explorer.exe", str(resolved)], start_new_session=True)
            ensure_app_windowed("explorer")
            return f"Status: Carpeta '{resolved.name}' ({resolved}) abierta con éxito en el Explorador de Windows."
        else:
            # Reveal and highlight file in Explorer
            subprocess.Popen(["explorer.exe", f"/select,{str(resolved)}"], start_new_session=True)
            ensure_app_windowed("explorer")
            return f"Status: Archivo '{resolved.name}' seleccionado y mostrado en el Explorador de Windows."
    except Exception as err:
        return f"Status: Fallo al abrir '{resolved}' ({err})."


def list_folder_contents(target: str = "", limit: int = 30) -> str:
    """
    Inspects and lists files and subdirectories inside the requested folder.
    Args:
        target: Target directory alias or path (e.g. 'descargas', 'documentos', 'capri').
        limit: Maximum number of entries to return.
    """
    resolved = resolve_path(target) if target else WORKSPACE_DIR
    if not resolved or not resolved.exists():
        return f"Status: Error - La carpeta '{target}' no existe o no se puede acceder a ella."

    if not resolved.is_dir():
        return f"Status: '{resolved.name}' es un archivo, no una carpeta. Su tamaño es {_format_size(resolved.stat().st_size)}."

    try:
        dirs: List[str] = []
        files: List[str] = []

        for entry in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if entry.name.startswith((".", "$")):
                continue
            if entry.is_dir():
                dirs.append(f"[CARPETA] {entry.name}/")
            else:
                size_str = _format_size(entry.stat().st_size)
                files.append(f"[ARCHIVO] {entry.name} ({size_str})")

        total_dirs = len(dirs)
        total_files = len(files)
        total_items = total_dirs + total_files

        sample_entries = (dirs + files)[:limit]
        header = f"Contenido de '{resolved.name}' ({resolved}) - {total_dirs} carpetas, {total_files} archivos:"
        body = "\n".join(sample_entries)
        if total_items > limit:
            body += f"\n... y {total_items - limit} elementos más."

        return f"Status: {header}\n{body}"
    except PermissionError:
        return f"Status: Permiso denegado para leer el contenido de la carpeta '{resolved}'."
    except Exception as err:
        return f"Status: Error al listar '{resolved}' ({err})."


def find_files(query: str, root_hint: str = "", max_results: int = 6) -> dict:
    """
    Fast breadth-first file search across user libraries.
    Args:
        query: Words or filename to look for (e.g. 'notas.txt', 'factura', 'python', 'spiderman').
        root_hint: Optional root directory to limit or prioritize the search.
        max_results: Maximum top matches to return.
    """
    clean_q = (query or "").strip().lower()
    if not clean_q:
        return {"query": query, "matches": [], "message": "No se indicó qué buscar."}

    # Determine starting roots
    roots: List[Path] = []
    if root_hint:
        hint_path = resolve_path(root_hint)
        if hint_path and hint_path.is_dir():
            roots.append(hint_path)

    if not roots:
        # Default priority places (same strategy as FileFinder.cs Places)
        default_places = [
            WORKSPACE_DIR,
            HOME_DIR / "Desktop",
            HOME_DIR / "Downloads",
            HOME_DIR / "Documents",
            HOME_DIR / "Pictures",
            Path("C:/Archivos") if Path("C:/Archivos").exists() else None,
        ]
        roots = [p for p in default_places if p and p.exists()]

    terms = [t for t in clean_q.replace(".", " .").split() if len(t) > 0]
    matches: List[Tuple[int, Path]] = []
    visited_dirs = set()

    for root in roots:
        # Breadth-first level queue
        current_level = [root]
        depth = 0
        max_depth = 4

        while current_level and depth <= max_depth and len(matches) < max_results * 2:
            next_level = []
            for folder in current_level:
                try:
                    f_resolved = str(folder.resolve()).lower()
                    if f_resolved in visited_dirs:
                        continue
                    visited_dirs.add(f_resolved)

                    for entry in folder.iterdir():
                        e_name = entry.name
                        e_low = e_name.lower()

                        if e_low in SKIP_DIRECTORIES or e_low.startswith((".", "$")):
                            continue

                        # Score match
                        score = 0
                        if clean_q == e_low:
                            score = 1000
                        elif clean_q in e_low:
                            score = 500
                        elif all(term in e_low for term in terms):
                            score = 250
                        elif any(term in e_low for term in terms if len(term) >= 3):
                            score = 100

                        if score > 0:
                            matches.append((score, entry))

                        if entry.is_dir() and depth < max_depth:
                            next_level.append(entry)

                except (PermissionError, OSError):
                    continue

            current_level = next_level
            depth += 1

    # Sort descending by score
    matches.sort(key=lambda item: item[0], reverse=True)
    unique_paths = []
    seen = set()
    for _, path in matches:
        p_str = str(path)
        if p_str not in seen:
            seen.add(p_str)
            unique_paths.append(p_str)
        if len(unique_paths) >= max_results:
            break

    return {
        "query": query,
        "matches": unique_paths,
        "count": len(unique_paths),
    }


def search_and_format_files(query: str, root_hint: str = "") -> str:
    """Wrapper that returns a formatted string message ready for Spidey's speech."""
    res = find_files(query, root_hint)
    matches = res["matches"]
    if not matches:
        return f"Status: No he encontrado ningún archivo o carpeta con el nombre '{query}' en tus carpetas habituales."

    first_name = Path(matches[0]).name
    lines = [f"Status: He encontrado {len(matches)} coincidencias para '{query}' (mejor coincidencia: '{first_name}'):"]
    for m in matches:
        p = Path(m)
        kind = "[CARPETA]" if p.is_dir() else f"[ARCHIVO] ({_format_size(p.stat().st_size)})"
        lines.append(f"- {kind} {m}")

    lines.append(f"\nPuedes pedirme 'abre la carpeta {first_name}' o 'enséñame {first_name}' para abrirlo en el Explorador.")
    return "\n".join(lines)


def read_file_preview(target: str, max_chars: int = 2500) -> str:
    """Safely reads text-based files for analysis."""
    resolved = resolve_path(target)
    if not resolved:
        search = find_files(target, max_results=1)
        if search["matches"]:
            resolved = Path(search["matches"][0])

    if not resolved or not resolved.exists():
        return f"Status: Error - El archivo '{target}' no existe."

    if resolved.is_dir():
        return list_folder_contents(str(resolved))

    # Supported text extensions
    text_exts = {".txt", ".md", ".json", ".py", ".csv", ".log", ".ini", ".cfg", ".yaml", ".yml", ".html", ".css", ".js", ".ts", ".xml"}
    if resolved.suffix.lower() not in text_exts and resolved.stat().st_size > 1024 * 1024:
        return f"Status: El archivo '{resolved.name}' ({_format_size(resolved.stat().st_size)}) es un archivo binario o muy grande para lectura directa."

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")[:max_chars]
        return f"Status: Contenido de '{resolved.name}' ({len(content)} caracteres leídos):\n{content}"
    except Exception as err:
        return f"Status: Error al leer '{resolved.name}' ({err})."


def _format_size(size_bytes: int) -> str:
    """Formats bytes into human-readable B, KB, MB, GB string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ==============================================================================
# SAFE FILE CREATION, EDITING & DELETION (RECYCLE / TRASH)
# ==============================================================================

TRASH_DIR = HOME_DIR / ".capri_trash"


def is_safe_operation_path(p: Path) -> Tuple[bool, str]:
    """
    Validates that a path is safe for modification/deletion:
    - Must be within user home or workspace / personal projects.
    - Cannot be system roots (C:/, Windows, Program Files, user root directory itself).
    """
    try:
        resolved = p.resolve()
        
        # Blacklist critical system directories
        critical = [
            Path("C:/"), Path("C:/Windows"), Path("C:/Program Files"),
            Path("C:/Program Files (x86)"), HOME_DIR, WORKSPACE_DIR.anchor
        ]
        if resolved in critical or str(resolved).lower().startswith("c:\\windows"):
            return False, f"Operación denegada por seguridad: '{resolved}' es una ruta crítica del sistema."

        # Whitelist safe root spaces
        allowed_roots = [HOME_DIR, WORKSPACE_DIR]
        if Path("C:/Archivos").exists():
            allowed_roots.append(Path("C:/Archivos").resolve())

        is_allowed = any(root == resolved or root in resolved.parents for root in allowed_roots)
        if not is_allowed:
            return False, f"Operación denegada: '{resolved}' está fuera de los directorios permitidos de usuario."

        return True, "OK"
    except Exception as e:
        return False, f"Ruta inválida: {e}"


def create_file(target: str, content: str = "") -> str:
    """
    Safely creates a new file with the specified content.
    """
    clean = (target or "").strip()
    if not clean:
        return "Status: Error - No se proporcionó el nombre o ruta del archivo a crear."

    # If relative, anchor to workspace
    p = Path(clean)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p

    safe, reason = is_safe_operation_path(p)
    if not safe:
        return f"Status: Error - {reason}"

    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Status: Archivo '{p.name}' creado con éxito en '{p.parent}' ({len(content)} caracteres)."
    except Exception as err:
        return f"Status: Error al crear '{p.name}': {err}"


def create_folder(target: str) -> str:
    """
    Safely creates a new folder.
    """
    clean = (target or "").strip()
    if not clean:
        return "Status: Error - No se proporcionó el nombre o ruta de la carpeta."

    p = Path(clean)
    if not p.is_absolute():
        p = WORKSPACE_DIR / p

    safe, reason = is_safe_operation_path(p)
    if not safe:
        return f"Status: Error - {reason}"

    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"Status: Carpeta '{p.name}' creada con éxito en '{p.parent}'."
    except Exception as err:
        return f"Status: Error al crear carpeta '{p.name}': {err}"


def edit_file(
    target: str,
    find_text: str = "",
    replace_text: str = "",
    append_text: str = "",
    content: str = "",
    overwrite: bool = False
) -> str:
    """
    Safely edits an existing file with automatic backup.
    Supports:
    1. Replacement of a specific text block.
    2. Appending text to the end.
    3. Overwriting full content if requested.
    """
    resolved = resolve_path(target)
    if not resolved:
        search = find_files(target, max_results=1)
        if search["matches"]:
            resolved = Path(search["matches"][0])

    if not resolved or not resolved.exists():
        return f"Status: Error - El archivo '{target}' no existe para editarlo."

    if resolved.is_dir():
        return f"Status: Error - '{resolved.name}' es una carpeta, no un archivo de texto."

    safe, reason = is_safe_operation_path(resolved)
    if not safe:
        return f"Status: Error - {reason}"

    try:
        original = resolved.read_text(encoding="utf-8", errors="replace")
        
        # Create lightweight backup file (.bak)
        bak_file = resolved.with_suffix(resolved.suffix + ".bak")
        bak_file.write_text(original, encoding="utf-8")

        new_content = original

        if overwrite and content:
            new_content = content
        elif find_text:
            if find_text not in original:
                return f"Status: Advertencia - No se encontró el texto indicado para reemplazar en '{resolved.name}'."
            new_content = original.replace(find_text, replace_text)
        elif append_text:
            new_content = original + ("\n" if not original.endswith("\n") else "") + append_text
        elif content and not overwrite:
            # Default to append if content is passed without find_text
            new_content = original + ("\n" if not original.endswith("\n") else "") + content
        else:
            return "Status: Error - No se indicó qué modificar (find_text, append_text o content)."

        resolved.write_text(new_content, encoding="utf-8")
        return f"Status: Archivo '{resolved.name}' modificado correctamente (Copia de respaldo creada en '{bak_file.name}')."
    except Exception as err:
        return f"Status: Error al editar '{resolved.name}': {err}"


def delete_file_safely(target: str, force: bool = False) -> str:
    """
    Safely moves a file or directory to Capri's safe quarantine / trash vault (~/.capri_trash),
    allowing full reversibility and preventing accidental loss of data.
    """
    resolved = resolve_path(target)
    if not resolved:
        search = find_files(target, max_results=1)
        if search["matches"]:
            resolved = Path(search["matches"][0])

    if not resolved or not resolved.exists():
        return f"Status: Error - El archivo o carpeta '{target}' no existe."

    safe, reason = is_safe_operation_path(resolved)
    if not safe:
        return f"Status: Error - {reason}"

    # Do not allow deleting current working directory
    if resolved == WORKSPACE_DIR:
        return "Status: Operación rechazada: no puedes eliminar el directorio activo del proyecto."

    try:
        # Destination in safe quarantine
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        trash_dir = TRASH_DIR / timestamp
        trash_dir.mkdir(parents=True, exist_ok=True)

        dest = trash_dir / resolved.name
        shutil.move(str(resolved), str(dest))

        # Save metadata record for reversibility
        manifest = {
            "original_path": str(resolved),
            "trash_path": str(dest),
            "deleted_at": time.time(),
            "kind": "dir" if dest.is_dir() else "file",
        }
        manifest_file = trash_dir / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        kind_str = "Carpeta" if manifest["kind"] == "dir" else "Archivo"
        return (
            f"Status: {kind_str} '{resolved.name}' movido con éxito a la papelera segura de Capri.\n"
            f"Ubicación de respaldo: {dest} (Totalmente recuperable)."
        )
    except Exception as err:
        return f"Status: Error al eliminar/mover '{resolved.name}': {err}"

