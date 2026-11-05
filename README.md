# Spider-Man Desktop Agent

Aplicación de escritorio que muestra un compañero virtual de Spider-Man sobre el
escritorio. El agente usa una interfaz gráfica transparente construida con
PySide6, conserva memoria local de las conversaciones y se conecta a un modelo
de lenguaje servido localmente por [Ollama](https://ollama.com/).

El agente puede conversar en español y ejecutar acciones de escritorio
compatibles con el sistema operativo, como abrir aplicaciones y gestionar
ventanas. Las respuestas se generan localmente: no se necesita una API key de
un proveedor externo.

## Requisitos

- Python 3.10 o superior.
- Ollama instalado y disponible en `http://localhost:11434`.
- El modelo `llama3.2:3b` descargado en Ollama.
- En Linux, una sesión gráfica X11 para las funciones de gestión de ventanas.
- En Windows, las funciones de gestión de ventanas usan las APIs nativas del
  sistema.

El modelo `llama3.2:3b` es el modelo configurado por defecto en
[`config.py`](./config.py). La configuración limita el contexto y la cantidad
de tokens para reducir el consumo de memoria y mantener respuestas breves,
adecuadas para la burbuja del personaje.

## Instalación

### 1. Instalar Ollama

Instala Ollama desde [ollama.com/download](https://ollama.com/download) y
comprueba que el comando esté disponible:

```powershell
ollama --version
```

En Linux, también puedes instalarlo con el instalador oficial:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Descargar el modelo requerido

Ejecuta exactamente:

```powershell
ollama pull llama3.2:3b
```

Comprueba que el modelo se haya instalado:

```powershell
ollama list
```

El nombre debe aparecer como `llama3.2:3b`. No es necesario ejecutar `ollama
run` de forma permanente; la aplicación usa la API local de Ollama y carga el
modelo cuando lo necesita.

### 3. Preparar el entorno Python

Desde la carpeta raíz del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

En Linux o macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Las dependencias principales son:

- `PySide6`: interfaz gráfica y ventana transparente.
- `ollama`: cliente Python para la API local de Ollama.
- `python-xlib`: soporte de gestión de ventanas en Linux/X11.

## Ejecución

1. Inicia el servicio de Ollama si no está activo:

   ```powershell
   ollama serve
   ```

   En muchas instalaciones de Windows Ollama ya se ejecuta como servicio; en
   ese caso, este paso puede no ser necesario.

2. En otra terminal, activa el entorno virtual y ejecuta la interfaz:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python body.py
   ```

   En Linux o macOS:

   ```bash
   source .venv/bin/activate
   python body.py
   ```

La aplicación mostrará a Spider-Man sobre el escritorio. Escribe en la
interfaz para conversar con él. Para cerrar la aplicación, utiliza la opción
de salida de la ventana o interrumpe el proceso con `Ctrl+C` desde la terminal.

## Modo de consola

Para probar el motor de conversación sin iniciar la interfaz gráfica:

```powershell
python brain.py
```

El modo de consola solicita texto y finaliza cuando se introduce `exit`,
`quit` o `q`.

## Configuración

Al iniciar por primera vez se crea `data/config.json` a partir de los valores
predeterminados. Entre los ajustes disponibles están:

```json
{
    "user_name": "Deivid",
    "language": "es",
    "ollama": {
        "host": "http://localhost:11434",
        "model": "llama3.2:3b",
        "keep_alive": "5m",
        "num_ctx": 2048,
        "temperature": 0.7,
        "max_tokens": 90
    }
}
```

Puedes editar `data/config.json` para cambiar el nombre, el idioma o los
parámetros de Ollama. Si cambias el modelo, primero debes descargarlo con
`ollama pull <modelo>` y después actualizar el campo `ollama.model`.

## Estructura principal

```text
body.py              Interfaz gráfica, animaciones y ventana del personaje
brain.py             Motor de conversación, Ollama y herramientas de escritorio
config.py            Configuración persistente y valores predeterminados
memory.py            Memoria local de conversaciones
persona.py           Personalidad y reglas de respuesta de Spider-Man
spiderman_lore.py    Contexto y lore del personaje
bubble.py            Burbuja de diálogo
abilities/           Funciones de interacción con ventanas y sistema
assets/              Sprites y recursos visuales
data/                Configuración y memoria generadas en ejecución
```

## Solución de problemas

### No se puede conectar con Ollama

Comprueba que el servicio esté activo y que responda en el puerto
predeterminado:

```powershell
ollama serve
ollama list
```

Si el modelo no aparece, vuelve a descargarlo:

```powershell
ollama pull llama3.2:3b
```

Si has cambiado el host o el puerto de Ollama, actualiza
`ollama.host` en `data/config.json`.

### El comando `python` no se reconoce

Instala Python, habilita la opción **Add Python to PATH** durante la
instalación y vuelve a crear el entorno virtual siguiendo los pasos anteriores.

### Linux no puede gestionar ventanas

`python-xlib` requiere una sesión X11. En Wayland, algunas funciones de
ventanas pueden no estar disponibles o depender de la compatibilidad XWayland.

## Privacidad y seguridad

Las inferencias se realizan contra el servidor local de Ollama. La aplicación
guarda configuración y memoria en la carpeta `data/`. Las herramientas del
agente interactúan con el sistema operativo, por lo que conviene revisar las
acciones solicitadas antes de ejecutarlas.
