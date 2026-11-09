"""
abilities/universal_intent_pipeline.py - Universal Semantic Slot Extraction Pipeline & Work Orders

Provides systematic, deterministic intent comprehension for all user requests.
Solves the fragility of rigid regexes by decomposing human requests into:
1. Universal Entity / Slot Extraction (Paths, files, extensions, contents, targets, values).
2. Domain Work Order Resolution (Files, Developer, Patterns, Assistant, System).
3. Direct Safe Execution (~0ms latency, zero SLM hallucinations).
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import BASE_DIR


@dataclass
class ConversationContext:
    """Tracks active multi-turn conversational state, entities, and deictic references."""
    active_topic: Optional[str] = None  # 'weather', 'file', 'folder', 'project', 'code', 'pattern', 'system'
    active_file: Optional[str] = None   # Path or filename of last referenced file
    active_folder: Optional[str] = None # Path or name of last referenced directory
    active_project: Optional[str] = None # Name or path of last project
    active_code_target: Optional[str] = None # Code filename (e.g. persona.py)
    active_city: Optional[str] = None   # Last city queried for weather
    last_action: Optional[str] = None   # Tool name executed in previous turn
    last_observation: Optional[str] = None # Output of previous tool execution
    last_user_query: Optional[str] = None
    last_assistant_reply: Optional[str] = None
    recent_entities: List[str] = field(default_factory=list)

    def update_from_work_order(self, action: str, params: Dict[str, Any], observation: str = "") -> None:
        """Updates conversational context when a tool / work order is executed."""
        self.last_action = action
        if observation:
            self.last_observation = (observation[:300] + "...") if len(observation) > 300 else observation

        # Update domain-specific entities
        if action == "get_weather":
            self.active_topic = "weather"
            city = params.get("city")
            if city:
                self.active_city = city
                self._record_entity(city)

        elif action in ("create_file", "edit_file", "read_file", "delete_file_safely"):
            self.active_topic = "file"
            target = params.get("target") or params.get("path")
            if target:
                self.active_file = str(target)
                self._record_entity(str(target))
                try:
                    p = Path(target)
                    if p.parent and str(p.parent) not in (".", ""):
                        self.active_folder = str(p.parent)
                except Exception:
                    pass

        elif action in ("open_folder", "list_folder", "create_folder"):
            self.active_topic = "folder"
            target = params.get("target")
            if target:
                self.active_folder = str(target)
                self._record_entity(str(target))

        elif action in ("inspect_project", "brainstorm_project_ideas", "run_code_check"):
            self.active_topic = "project"
            target = params.get("target") or "capri"
            self.active_project = str(target)
            self._record_entity(str(target))

        elif action == "analyze_code":
            self.active_topic = "code"
            target = params.get("target")
            if target:
                self.active_code_target = str(target)
                self._record_entity(str(target))

        elif action in ("list_learned_patterns", "learn_pattern"):
            self.active_topic = "pattern"

        elif action in ("get_live_news", "smart_web_research", "search_web_information"):
            self.active_topic = "web_research"
            q = params.get("query") or params.get("topic")
            if q:
                self._record_entity(str(q))

    def update_from_turn(self, user_msg: str, assistant_msg: str) -> None:
        """Updates conversational context with raw conversational turns."""
        self.last_user_query = user_msg
        self.last_assistant_reply = assistant_msg

    def _record_entity(self, ent: str) -> None:
        if ent and ent not in self.recent_entities:
            self.recent_entities.insert(0, ent)
            if len(self.recent_entities) > 8:
                self.recent_entities = self.recent_entities[:8]

    def get_context_prompt(self) -> str:
        """Produces a short, token-efficient summary of the active conversation context."""
        parts = []
        if self.active_topic:
            parts.append(f"Tema activo: {self.active_topic}")
        if self.active_city and self.active_topic == "weather":
            parts.append(f"Ciudad meteorológica: {self.active_city}")
        if self.active_file:
            parts.append(f"Archivo en foco: {self.active_file}")
        if self.active_folder:
            parts.append(f"Carpeta en foco: {self.active_folder}")
        if self.active_project:
            parts.append(f"Proyecto en desarrollo: {self.active_project}")
        if self.active_code_target:
            parts.append(f"Código en revisión: {self.active_code_target}")
        if self.last_action:
            parts.append(f"Última acción ejecutada: {self.last_action}")
        if self.last_observation:
            obs_preview = self.last_observation.replace("\n", " ").strip()
            if len(obs_preview) > 120:
                obs_preview = obs_preview[:120] + "..."
            parts.append(f"Último resultado: {obs_preview}")

        if not parts:
            return ""
        return f"\n[(Contexto conversacional previo activo: {'; '.join(parts)})]"

    def reset(self) -> None:
        self.active_topic = None
        self.active_file = None
        self.active_folder = None
        self.active_project = None
        self.active_code_target = None
        self.active_city = None
        self.last_action = None
        self.last_observation = None
        self.last_user_query = None
        self.last_assistant_reply = None
        self.recent_entities.clear()


@dataclass
class ExtractedSlots:
    """Structured slots extracted from natural human instructions."""
    raw_text: str
    clean_text: str
    quoted_strings: List[str] = field(default_factory=list)
    windows_paths: List[str] = field(default_factory=list)
    file_extensions: List[str] = field(default_factory=list)
    detected_filename: Optional[str] = None
    detected_directory: Optional[str] = None
    content_payload: Optional[str] = None
    action_verbs: List[str] = field(default_factory=list)
    target_domains: List[str] = field(default_factory=list)


def _strip_accents(s: str) -> str:
    """Normalizes string removing combining accents."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower()


def extract_slots(text: str) -> ExtractedSlots:
    """
    Universal entity and slot extractor.
    Breaks down any natural speech into structured parameters regardless of word order.
    """
    raw = (text or "").strip()
    clean = _strip_accents(raw)

    slots = ExtractedSlots(raw_text=raw, clean_text=clean)

    # 1. Quoted Strings Extraction (e.g. "C:\Archivos\Nueva carpeta", 'hola mundo')
    quotes = re.findall(r'["\']([^"\']+)["\']', raw)
    slots.quoted_strings = quotes

    # 2. Windows and Absolute Paths Extraction (e.g. C:\Archivos\Nueva carpeta, C:/proyectos/web)
    # Extracts paths with Windows drive letters, with or without quotes, with spaces
    path_pattern = r'(?:[a-zA-Z]:[\\/][^"\'\n\r\t]+?)(?=(?:\s+(?:que|con|diciendo|para|y|$)|["\']|$))'
    raw_paths = re.findall(path_pattern, raw)
    
    # Also include any quoted string that starts with a drive letter
    for q in quotes:
        if re.match(r'^[a-zA-Z]:[\\/]', q) and q not in raw_paths:
            raw_paths.append(q)

    # Clean up trailing punctuation from extracted paths
    cleaned_paths = []
    for p in raw_paths:
        clean_p = p.strip(" \"',;!?")
        if clean_p and clean_p not in cleaned_paths:
            cleaned_paths.append(clean_p)
    slots.windows_paths = cleaned_paths

    # 3. File Extensions Extraction (e.g. .txt, .py, .json, .md, .csv)
    exts = re.findall(r'(?:\s|^|\b)\.([a-zA-Z0-9]{1,5})\b', raw)
    slots.file_extensions = [f".{e.lower()}" for e in exts]

    # Explicit filenames (e.g. notas.txt, persona.py, config.json)
    filename_match = re.search(r'\b([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]{1,5})\b', raw)
    if filename_match:
        slots.detected_filename = filename_match.group(1).strip()
    elif slots.file_extensions:
        # Default name with requested extension if only extension was given (e.g. "un archivo .txt")
        slots.detected_filename = f"archivo{slots.file_extensions[0]}"

    # 4. Directory Path Extraction
    if cleaned_paths:
        first_path = Path(cleaned_paths[0])
        # If path has a suffix like .txt, directory is parent; otherwise whole path is directory
        if first_path.suffix:
            slots.detected_directory = str(first_path.parent)
            if not slots.detected_filename:
                slots.detected_filename = first_path.name
        else:
            slots.detected_directory = str(first_path)

    # Check for known folder mentions if no windows path
    if not slots.detected_directory:
        for known in ("descargas", "downloads", "documentos", "documents", "escritorio", "desktop", "imagenes", "fotos", "videos", "musica", "proyecto", "capri"):
            if re.search(rf'\b{known}\b', clean):
                slots.detected_directory = known
                break

    # 5. Content Payload Extraction (e.g. diciendo hola, que diga hola, con el texto "x", y pon "y")
    content_cand = ""
    # Look for content intro triggers
    m_content = re.search(r'(?:diciendo|que\s+diga|con\s+el\s+texto|con\s+el\s+contenido|que\s+ponga|con\s+contenido|diga|(?:y\s+)?(?:a[nñ]ade|agrega|pon|escribe))\s+["\']?([^"\']+)["\']?', raw, re.I)
    if m_content:
        raw_tail = m_content.group(1).strip()
        # If prepositions like "en esta direccion" or "en C:" follow, cut them off
        raw_cut = re.split(r'\s+(?:en\s+(?:esta\s+)?(?:direccion|carpeta|ruta|el|la)|en\s+[a-zA-Z]:)', raw_tail, flags=re.I)[0]
        content_cand = raw_cut.strip()
    elif quotes:
        # Check if one of the quotes is a text payload (not a path)
        for q in quotes:
            if not re.match(r'^[a-zA-Z]:[\\/]', q) and not any(q.endswith(ext) for ext in (".txt", ".py", ".json", ".md")):
                content_cand = q
                break

    slots.content_payload = content_cand

    # 6. Action Verbs (Strip paths and quoted strings first to prevent "Nueva carpeta" triggering "crear")
    verbs_scan_text = clean
    for p in slots.windows_paths:
        verbs_scan_text = verbs_scan_text.replace(_strip_accents(p), " ")
    for q in slots.quoted_strings:
        verbs_scan_text = verbs_scan_text.replace(_strip_accents(q), " ")

    verbs_map = {
        "borrar": ["borra", "borrar", "elimina", "eliminar", "suprime", "suprimir", "quita", "quitar", "papelera", "basura", "cargate", "cargatelo", "cárgatelo", "destruye", "deshazte"],
        "crear": ["crea", "crear", "creame", "créame", "haz", "hazme", "genera", "escribe", "escribeme", "escríbeme", "creacion", "creación", "tirame", "tírame", "ponme"],
        "editar": ["edita", "editar", "modifica", "modificar", "agrega", "anade", "añade"],
        "leer": ["lee", "leeme", "léeme", "leer", "muestra", "muestrame", "muéstramelo", "muéstrame", "ver", "que dice", "qué dice", "echa un vistazo", "enséñame", "enseñame"],
        "abrir": ["abre", "abrir", "entra", "inicia", "accede", "open"],
        "listar": ["lista", "listar", "que hay", "qué hay", "que tengo", "qué tengo", "contenido"],
        "buscar": ["busca", "buscar", "encuentra", "localiza", "donde esta", "dónde está"],
        "analizar": ["analiza", "analizar", "inspecciona", "inspeccionar", "explora", "revisa", "revisar", "escanea", "entiende", "explica", "échale un ojo", "echale un ojo"],
        "aprender": ["aprende", "aprender", "recuerda", "recordar", "guarda", "guardar", "memoriza"],
        "consultar": ["dime", "cuenta", "mostrar", "muestrame", "cuales", "cuáles", "que sabes", "qué sabes", "que patrones", "qué patrones", "habitos", "hábitos"],
    }
    for category, triggers in verbs_map.items():
        if any(re.search(rf'\b{t}\b', verbs_scan_text) for t in triggers):
            slots.action_verbs.append(category)

    # 7. Target Domains
    targets_map = {
        "archivo": ["archivo", "fichero", "nota", "documento", ".txt", ".py", ".json", ".md", ".csv"],
        "carpeta": ["carpeta", "directorio", "folder", "explorador"],
        "proyecto": ["proyecto", "repo", "repositorio", "workspace", "codigo", "código", "arquitectura"],
        "patron": ["patron", "patrones", "patron*", "habito", "habitos", "preferencia", "preferencias", "regla", "reglas"],
        "sistema": ["volumen", "musica", "cancion", "pantalla", "captura", "temperatura", "specs", "hardware"],
        "clima": ["tiempo", "clima", "temperatura", "llover", "llueve", "lluvia", "meteorologia", "meteorología", "frio", "frío", "calor", "grados", "cielo", "pronostico", "pronóstico", "prevision", "previsión"],
    }
    for domain, triggers in targets_map.items():
        if any(re.search(rf'\b{t}\b', clean) for t in triggers):
            slots.target_domains.append(domain)

    return slots


# ==============================================================================
# CONTEXTUAL QUERY REWRITER (MULTI-TURN CONTINUITY)
# ==============================================================================

def contextualize_query(text: str, context: Optional[ConversationContext] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Contextual Query Rewriter & Multi-Turn Resolver.
    Resolves pronouns, clitics, deictic references ('allí', 'bórralo', '¿cómo lo mejorarías?'),
    and conversational ellipses using the active ConversationContext.
    """
    raw = (text or "").strip()
    if not raw or not context:
        return raw, {}

    clean = _strip_accents(raw)
    meta: Dict[str, Any] = {}

    # 1. WEATHER CONTINUITY & ELLIPSIS
    # 1.1 Prepositional City Ellipsis: "¿y en Madrid?", "en Barcelona?", "y en París?", "¿qué tal en Sevilla?"
    m_prep_city = re.match(r'^(?:[¿?¡!]\s*)?(?:y\s+)?(?:en|para|de)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ]+)[.!?¿¡]*$', raw, re.I)
    if m_prep_city:
        cand_city = m_prep_city.group(1).strip()
        if cand_city.lower() not in ("hoy", "manana", "ayer", "ahora", "este", "esta", "mi", "tu", "aqui", "alli"):
            if context.active_topic == "weather" or context.active_city:
                meta = {"context_applied": "weather_city_ellipsis", "city": cand_city}
                return f"dime el tiempo actual en {cand_city}", meta
            elif context.active_topic == "folder":
                meta = {"context_applied": "folder_city_ellipsis", "folder": cand_city}
                return f"lista la carpeta {cand_city}", meta

    # 1.2 Deictic Weather Follow-ups: "¿y lloverá allí?", "¿lloverá ahí?", "¿hará frío allí?", "¿va a llover?", "¿qué temperatura hace allí?"
    weather_terms = ("llover", "llueve", "lluvia", "frio", "calor", "temperatura", "tiempo", "clima", "grados", "cielo")
    has_weather_term = any(w in clean for w in weather_terms)
    has_deictic_loc = any(w in clean for w in ("alli", "ahi", "en esa ciudad", "en este sitio", "por ahi", "por alli"))

    if (has_weather_term and (has_deictic_loc or not re.search(r'\b(?:en|para|de)\s+[a-zA-ZáéíóúñÁÉÍÓÚÑ]{3,}\b', raw, re.I))) and context.active_city:
        meta = {"context_applied": "weather_deictic_resolution", "city": context.active_city}
        return f"dime el tiempo actual y lluvia en {context.active_city}", meta

    # 2. FILE CONTINUITY & PRONOMINAL CLITICS
    # 2.1 File Deletion: "bórralo", "elimínalo", "suprímelo", "cárgatelo", "mándalo a la papelera", "borra ese archivo", "elimina ese archivo"
    m_del_clitic = re.search(r'^(?:[¿?¡!]\s*)?(?:por\s+favor\s+)?(?:borra|elimina|suprime|quita|cargate|mandalo\s+a\s+la\s+papelera|deshazte\s+de)\s*(?:lo|la|ese\s+archivo|este\s+archivo|el\s+archivo)?[.!?¿¡]*$', clean)
    if m_del_clitic and context.active_file:
        meta = {"context_applied": "file_delete_clitic", "target": context.active_file}
        return f"elimina el archivo {context.active_file}", meta

    # 2.2 File Open: "ábrelo", "abre ese archivo", "inícialo"
    m_open_clitic = re.search(r'^(?:[¿?¡!]\s*)?(?:por\s+favor\s+)?(?:abre|abrir|inicia)\s*(?:lo|ese\s+archivo|este\s+archivo)?[.!?¿¡]*$', clean)
    if m_open_clitic and context.active_file:
        meta = {"context_applied": "file_open_clitic", "target": context.active_file}
        return f"abre el archivo {context.active_file}", meta

    # 2.3 File Read: "léelo", "muéstramelo", "qué dice ese archivo", "qué pone", "léeme lo que tiene"
    m_read_clitic = re.search(r'^(?:[¿?¡!]\s*)?(?:por\s+favor\s+)?(?:lee|leeme|muestra|muestramelo|que\s+dice|que\s+pone|que\s+tiene)\s*(?:lo|ese\s+archivo|este\s+archivo|el\s+archivo)?[.!?¿¡]*$', clean)
    if m_read_clitic and context.active_file:
        meta = {"context_applied": "file_read_clitic", "target": context.active_file}
        return f"lee el archivo {context.active_file}", meta

    # 2.4 File Edit: "edítalo y añade...", "modifícalo y pon..."
    m_edit_clitic = re.search(r'^(?:[¿?¡!]\s*)?(?:por\s+favor\s+)?(?:edita|modifica)(?:lo|la|se)?(?:\s+(?:ese|este)\s+archivo)?\s*(?:y\s+(?:anade|agrega|pon|escribe)|con\s+el\s+texto)\s+(.+)$', clean)
    if m_edit_clitic and context.active_file:
        append_txt = m_edit_clitic.group(1).strip()
        meta = {"context_applied": "file_edit_clitic", "target": context.active_file, "payload": append_txt}
        return f"edita el archivo {context.active_file} y añade {append_txt}", meta

    # 3. PROJECT & DEVELOPER CONTINUITY
    # 3.1 Project Brainstorming / Improvements: "¿cómo lo mejorarías?", "¿qué ideas me das?", "dame ideas para mejorarlo", "¿qué sugerencias tienes?", "¿qué cambios harías?"
    m_proj_improve = re.search(r'(?:como\s+lo\s+mejorarias|que\s+ideas\s+(?:me\s+)?das|dame\s+ideas(?:\s+para\s+mejorarlo)?|que\s+sugerencias\s+tienes|que\s+cambios\s+harias|que\s+le\s+falta|como\s+mejorar\s+este\s+proyecto|que\s+opinas)', clean)
    if m_proj_improve and (context.active_project or context.active_topic == "project"):
        proj = context.active_project or "capri"
        meta = {"context_applied": "project_brainstorm_clitic", "project": proj}
        return f"dame ideas para el proyecto {proj}", meta

    # 3.2 Project Code Check / Tests: "comprueba el código", "pasa los tests", "ejecuta las pruebas", "verifica la sintaxis"
    m_tests = re.search(r'(?:pasa\s+los\s+tests|ejecuta\s+las\s+pruebas|comprueba\s+el\s+codigo|verifica\s+la\s+sintaxis)', clean)
    if m_tests:
        proj = context.active_project or "capri"
        meta = {"context_applied": "project_code_check", "project": proj}
        return f"comprueba el codigo del proyecto {proj}", meta

    # 3.3 Code File Review: "analízalo", "explícalo", "¿qué funciones tiene?"
    m_code_sym = re.search(r'^(?:[¿?¡!]\s*)?(?:analiza|explica|que\s+funciones\s+tiene)\s*(?:lo|el\s+codigo|el\s+archivo)?[.!?¿¡]*$', clean)
    if m_code_sym and context.active_code_target:
        meta = {"context_applied": "code_analysis_clitic", "target": context.active_code_target}
        return f"analiza el codigo de {context.active_code_target}", meta

    # 4. FOLDER CONTINUITY
    # 4.1 Folder Listing: "¿qué hay dentro?", "¿qué hay ahí?", "lístalos", "¿qué archivos hay?"
    m_folder_list = re.search(r'^(?:[¿?¡!]\s*)?(?:que\s+hay\s+(?:dentro|ahi|aqui)|que\s+archivos\s+hay|listalos|enumeralos|que\s+contiene)[.!?¿¡]*$', clean)
    if m_folder_list and context.active_folder:
        meta = {"context_applied": "folder_list_anaphora", "target": context.active_folder}
        return f"lista el contenido de la carpeta {context.active_folder}", meta

    return raw, meta


# ==============================================================================
# WORK ORDER DISPATCH RESOLVER
# ==============================================================================

def resolve_universal_work_order(text: str, context: Optional[ConversationContext] = None) -> Optional[Dict[str, Any]]:
    """
    Evaluates extracted slots and dispatches the exact tool instruction.
    100% resilient to word order variations, prepositions, quotes, colloquial Spanish,
    and multi-turn conversational coreference/anaphora resolution.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    # Step 1: Contextual Query Resolution
    resolved_query, ctx_meta = contextualize_query(raw, context)
    slots = extract_slots(resolved_query)
    clean = slots.clean_text

    # --------------------------------------------------------------------------
    # ORDER 0: LEARNED RULES (Explicit user customization)
    # --------------------------------------------------------------------------
    try:
        from abilities.pattern_learning import get_pattern_learner
        learner = get_pattern_learner()
        rule_match = learner.match_learned_rule(clean)
        if rule_match:
            act_name, params = rule_match
            return {"action": act_name, "params": params}
    except Exception:
        pass

    # --------------------------------------------------------------------------
    # ORDER 1: PATTERNS & LEARNING ("dime que patrones has analizado", etc.)
    # --------------------------------------------------------------------------
    has_pattern_word = any(w in clean for w in ("patron", "patrones", "aprendizaje", "aprendido", "analizado"))
    has_query_verb = any(v in slots.action_verbs for v in ("consultar", "leer")) or any(w in clean for w in ("dime", "cuales", "que has", "que sabes", "muestra", "resumen", "lista"))
    
    if has_pattern_word and has_query_verb:
        return {"action": "list_learned_patterns", "params": {}}

    # Learn project path (e.g. "recuerda que mi proyecto web está en C:/proyectos/web")
    if "aprender" in slots.action_verbs and "proyecto" in clean:
        m_proj = re.search(r'proyecto\s+([a-zA-Z0-9_-]+)', clean)
        alias = m_proj.group(1).strip() if m_proj else "proyecto"
        path_val = slots.windows_paths[0] if slots.windows_paths else (slots.quoted_strings[0] if slots.quoted_strings else "")
        if path_val:
            return {"action": "learn_pattern", "params": {"kind": "project", "name": alias, "value": path_val}}

    # Learn preference (e.g. "aprende que mi base de datos preferida es postgres")
    if "aprender" in slots.action_verbs and any(w in clean for w in ("preferencia", "preferido", "preferida", "estilo")):
        m_pref = re.search(r'(?:preferencia\s+(?:de\s+)?|preferid[oa]\s+es\s+)([a-zA-Z0-9_-]+)', clean)
        p_name = m_pref.group(1) if m_pref else "preferencia"
        return {"action": "learn_pattern", "params": {"kind": "preference", "name": p_name, "value": raw}}

    # --------------------------------------------------------------------------
    # ORDER 2: FILE & DIRECTORY LIFECYCLE (Create, Delete, Edit, Read, List)
    # --------------------------------------------------------------------------

    # 2.1 CREATE FILE (e.g. 'crea un archivo .txt diciendo hola en esta direccion "C:\\Archivos\\Nueva carpeta"')
    is_create = "crear" in slots.action_verbs
    is_file_target = "archivo" in slots.target_domains or bool(slots.file_extensions)

    if is_create and is_file_target:
        filename = slots.detected_filename or "archivo.txt"
        content = slots.content_payload or ""

        # Build full destination path
        if slots.detected_directory:
            dest_dir = Path(slots.detected_directory)
            target_path = str(dest_dir / filename)
        else:
            target_path = filename

        return {
            "action": "create_file",
            "params": {
                "target": target_path,
                "content": content,
            }
        }

    # 2.2 CREATE FOLDER (e.g. 'crea una carpeta llamada temp en C:\\Archivos')
    if is_create and "carpeta" in slots.target_domains:
        target_folder = slots.detected_directory or (slots.quoted_strings[0] if slots.quoted_strings else "")
        if not target_folder:
            # Check trailing name
            m_f = re.search(r'(?:carpeta|directorio|folder)\s+(?:llamada\s+|llamado\s+)?([a-zA-Z0-9_:\\/.-]+)', raw)
            if m_f:
                target_folder = m_f.group(1).strip()
        if target_folder:
            return {
                "action": "create_folder",
                "params": {"target": target_folder}
            }

    # 2.3 SAFE DELETE FILE / FOLDER (e.g. 'elimina el archivo temp.txt', 'borra la carpeta x', 'bórralo')
    if "borrar" in slots.action_verbs:
        target_item = ""
        if slots.windows_paths:
            target_item = slots.windows_paths[0]
        elif slots.detected_filename:
            target_item = slots.detected_filename
        elif slots.detected_directory:
            target_item = slots.detected_directory
        elif slots.quoted_strings:
            target_item = slots.quoted_strings[0]
        elif context and context.active_file:
            target_item = context.active_file
        else:
            # Trailing target extraction
            m_del = re.search(r'(?:borra|elimina|quita|suprime|cargate)\s+(?:el\s+|la\s+)?(?:archivo|carpeta|fichero)?\s*([a-zA-Z0-9_:\\/.-]+)', raw, re.I)
            if m_del:
                target_item = m_del.group(1).strip()

        if target_item and target_item.lower() not in ("app", "ventana", "musica", "pantalla", "volumen"):
            return {
                "action": "delete_file_safely",
                "params": {"target": target_item}
            }

    # 2.4 EDIT FILE (e.g. 'edita el archivo notas.txt y añade terminar la tarea', 'edítalo')
    if "editar" in slots.action_verbs:
        target_file = (slots.windows_paths[0] if slots.windows_paths else slots.detected_filename) or ""
        if not target_file and context and context.active_file:
            target_file = context.active_file
        if target_file:
            return {
                "action": "edit_file",
                "params": {
                    "target": target_file,
                    "append_text": slots.content_payload or ctx_meta.get("payload") or "",
                }
            }

    # 2.5 READ FILE
    if "leer" in slots.action_verbs:
        target_file = (slots.windows_paths[0] if slots.windows_paths else slots.detected_filename) or ""
        if not target_file and context and context.active_file:
            target_file = context.active_file
        if target_file:
            return {
                "action": "read_file",
                "params": {"target": target_file}
            }

    # 2.6 LIST FOLDER CONTENTS
    is_list_folder = (
        ("listar" in slots.action_verbs and ("carpeta" in slots.target_domains or slots.detected_directory or any(w in clean for w in ("carpeta", "directorio", "folder", "archivos"))))
        or (("leer" in slots.action_verbs or "consultar" in slots.action_verbs) and "carpeta" in slots.target_domains)
    )
    if is_list_folder and not any(w in clean for w in ("pantalla", "abierto", "musica", "cancion", "patron", "patrones", "hardware", "ram", "pc", "specs")):
        target_dir = slots.detected_directory or (slots.windows_paths[0] if slots.windows_paths else "")
        if not target_dir and context and context.active_folder:
            target_dir = context.active_folder
        if not target_dir:
            m_dir = re.search(r'(?:en|de)\s+(?:la\s+carpeta\s+|el\s+directorio\s+)?([a-zA-Z0-9_:\\/.-]+)', clean)
            if m_dir:
                target_dir = m_dir.group(1).strip()
        if target_dir or any(w in clean for w in ("carpeta", "directorio", "folder", "archivos", "descargas", "documentos")):
            return {
                "action": "list_folder",
                "params": {"target": target_dir or ""}
            }

    # 2.7 OPEN FOLDER / EXPLORER
    if "abrir" in slots.action_verbs and ("carpeta" in slots.target_domains or slots.detected_directory or "explorador" in clean):
        target_dir = slots.detected_directory or (slots.windows_paths[0] if slots.windows_paths else "")
        if not target_dir and context and context.active_folder:
            target_dir = context.active_folder
        return {
            "action": "open_folder",
            "params": {"target": target_dir or ""}
        }

    # 2.8 FIND FILES ON PC
    if "buscar" in slots.action_verbs and ("archivo" in slots.target_domains or slots.detected_filename or "pc" in clean or "ordenador" in clean):
        if not any(clean.endswith(web) for web in ("en google", "en youtube", "en internet", "en la web", "en brave", "en chrome")):
            query = slots.detected_filename or (slots.quoted_strings[0] if slots.quoted_strings else "")
            if not query:
                m_q = re.search(r'busca\s+(?:el\s+archivo\s+|la\s+carpeta\s+)?([a-zA-Z0-9_.-]+)', clean)
                if m_q:
                    query = m_q.group(1).strip()
            if query:
                return {
                    "action": "find_files",
                    "params": {"query": query}
                }

    # --------------------------------------------------------------------------
    # ORDER 3: DEVELOPER ASSISTANCE & CODE INTELLIGENCE
    # --------------------------------------------------------------------------

    # 3.1 INSPECT PROJECT (e.g. 'analiza el proyecto capri', 'inspecciona el proyecto')
    if "analizar" in slots.action_verbs and "proyecto" in clean:
        m_p = re.search(r'proyecto\s+([a-zA-Z0-9_-]+)', clean)
        proj_name = m_p.group(1).strip() if m_p else (context.active_project if context and context.active_project else "")
        return {
            "action": "inspect_project",
            "params": {"target": proj_name}
        }

    # 3.2 ANALYZE CODE FILE (e.g. 'analiza el código de persona.py', 'qué hace config.py')
    if ("analizar" in slots.action_verbs or "leer" in slots.action_verbs or "que hace" in clean) and (slots.detected_filename or (context and context.active_code_target)):
        target_code = slots.detected_filename or (context.active_code_target if context else "")
        if any(target_code.endswith(ext) for ext in (".py", ".js", ".ts", ".html", ".css", ".rs", ".go", ".c", ".cpp", ".cs")):
            return {
                "action": "analyze_code",
                "params": {"target": target_code}
            }

    # 3.3 BRAINSTORM IDEAS & ARCHITECTURE (e.g. '¿cómo lo mejorarías?', 'dame ideas para el proyecto')
    if any(w in clean for w in ("ideas", "sugerencias", "como mejorar", "mejorar", "arquitectura")):
        m_p = re.search(r'proyecto\s+([a-zA-Z0-9_-]+)', clean)
        proj_name = m_p.group(1).strip() if m_p else (context.active_project if context and context.active_project else "")
        return {
            "action": "brainstorm_project_ideas",
            "params": {"target": proj_name}
        }

    # 3.4 RUN CODE CHECK & TESTS
    if any(w in clean for w in ("comprueba el codigo", "comprueba el código", "pasa los tests", "ejecuta las pruebas", "verifica la sintaxis", "haz test", "verifica el codigo")):
        proj_target = context.active_project if context and context.active_project else ""
        return {
            "action": "run_code_check",
            "params": {"target": proj_target}
        }

    # --------------------------------------------------------------------------
    # ORDER 4: REAL-TIME INTERNET & DESKTOP ASSISTANT
    # --------------------------------------------------------------------------

    # 4.1 LIVE WEATHER & METEOROLOGY (e.g. 'dime el tiempo de hoy', 'tiempo actual en vic', 'clima en barcelona', '¿y lloverá allí?')
    weather_triggers = (
        "tiempo", "clima", "temperatura", "llover", "llueve", "lluvia",
        "meteorologia", "meteorología", "frio", "frío", "calor", "grados",
        "pronostico", "pronóstico", "cielo", "prevision", "previsión"
    )
    if any(re.search(rf'\b{t}\b', clean) for t in weather_triggers) and not any(w in clean for w in ("hace mucho tiempo", "tiempo libre", "perder el tiempo", "al mismo tiempo")):
        from config import get_config
        cfg = get_config()
        default_city = cfg.get("default_city", "Vic")

        city_cand = ""
        # Search for pattern: "en <city>", "de <city>", "para <city>"
        m_city = re.search(r'\b(?:en|para|de)\s+([a-zA-ZáéíóúñÁÉÍÓÚÑ]+)\b', raw, re.I)
        if m_city:
            extracted = m_city.group(1).strip()
            # Ignore stop words or generic words like 'hoy', 'mi', 'el', 'la', 'alli', 'ahi'
            if extracted.lower() not in ("hoy", "manana", "ayer", "ahora", "mi", "el", "la", "este", "esta", "tiempo", "clima", "alli", "ahi"):
                city_cand = extracted

        # If no city parsed, check context
        if not city_cand and context and context.active_city:
            city_cand = context.active_city

        return {
            "action": "get_weather",
            "params": {"city": city_cand or default_city}
        }

    # --------------------------------------------------------------------------
    # ORDER 5: REAL-TIME WEB RESEARCH & LIVE NEWS
    # --------------------------------------------------------------------------

    # 5.1 LIVE BREAKING NEWS (e.g. 'dime que noticias importantes han habido hoy en el mundo', 'qué noticias hay hoy')
    is_news_query = any(re.search(rf'\b{w}\b', clean) for w in ("noticias", "noticia", "titulares", "actualidad", "ultimas noticias", "últimas noticias", "portadas"))
    if is_news_query or ("que pasa" in clean and any(w in clean for w in ("mundo", "hoy", "espana", "españa"))):
        m_topic = re.search(r'\b(?:de|sobre|acerca de)\s+([a-zA-Z0-9áéíóúñÁÉÍÓÚÑ\s]+?)(?:\s+(?:hoy|en el mundo|ahora)|$)', raw, re.I)
        news_topic = m_topic.group(1).strip() if m_topic else ""
        if news_topic.lower() in ("hoy", "mundo", "dia", "actualidad"):
            news_topic = ""
        return {
            "action": "get_live_news",
            "params": {"topic": news_topic}
        }

    # 5.2 REAL-TIME EVENT / ENTITY RESEARCH (e.g. 'qué sabes sobre la reciente caída de Nvidia?', 'qué pasó con X', 'investiga sobre Y')
    research_triggers = (
        r'(?:qu[eé]\s+(?:sabes|se\s+sabe|ha\s+pasado|pas[oó]|hay|ocurri[oó])\s+(?:sobre|de|con)|'
        r'cu[eé]ntame\s+(?:sobre|de)|busca\s+(?:en\s+internet|informaci[oó]n\s+(?:sobre|de))|'
        r'investiga\s+(?:sobre|acerca\s+de)?|averigua\s+(?:sobre)?)\s+(.+)$'
    )
    m_research = re.search(research_triggers, raw, re.I)
    if m_research:
        query_target = m_research.group(1).strip(" .!?¿¡")
        if query_target and not any(query_target.lower().startswith(skip) for skip in ("mi pantalla", "mi ordenador", "mis archivos", "este archivo", "este proyecto", "patrones", "mis patrones")):
            return {
                "action": "smart_web_research",
                "params": {"query": query_target}
            }

    # 5.3 RECENT EVENT CATCHER (e.g. 'la reciente caida de nvidia', 'el reciente desplome de X')
    if any(w in clean for w in ("reciente", "recientes")) and any(w in clean for w in ("caida", "caída", "bajada", "subida", "lanzamiento", "anuncio", "polemica", "polémica", "investigacion", "investigación", "desplome")):
        return {
            "action": "smart_web_research",
            "params": {"query": raw}
        }

    return None
