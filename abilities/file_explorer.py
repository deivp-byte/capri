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
