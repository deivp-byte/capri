"""
SpiderCommandsDialog: Modern Cyberpunk GUI for Custom Commands & Macros Management.
Allows users to create, list, execute, and delete persistent multi-step action commands.
"""
from __future__ import annotations

from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QMessageBox,
)

from abilities.custom_commands import (
    list_commands,
    save_command,
    delete_command,
)
from PySide6.QtWidgets import QApplication


class SpiderCommandsDialog(QDialog):
    """
    Styled Dialog for creating, viewing, executing, and deleting
    persistent custom desktop commands and macros.
    """

    command_executed = Signal(str)  # Emits action text to be executed by Spidey

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Prevent secondary dialog close from terminating the main pet process
        app = QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(False)

        self.setWindowTitle("⚡ Comandas Personalizadas (Macros) - Capri")
        self.setFixedSize(580, 520)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowTitleHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self._setup_style()
        self._init_ui()
        self._refresh_list()

    def closeEvent(self, event) -> None:
        """Hides dialog gracefully without quitting the application or active conversation."""
        event.ignore()
        self.hide()

    def _setup_style(self) -> None:
        """Applies dark cyberpunk neon styling consistent with SpiderWindow."""
        self.setStyleSheet("""
            QDialog {
                background-color: #12101a;
                color: #f5f0fa;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #f5f0fa;
            }
            QLineEdit {
                background-color: #1c1829;
                color: #00ffcc;
                border: 1px solid #3d3159;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                selection-background-color: #ff2e70;
            }
            QLineEdit:focus {
                border: 1px solid #ff2e70;
                background-color: #231e33;
            }
            QPushButton {
                background-color: #241d38;
                color: #ffffff;
                border: 1px solid #ff2e70;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #ff2e70;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #d61856;
            }
            QPushButton#btnSave {
                background-color: #ff2e70;
                color: #ffffff;
                border: none;
                padding: 9px 18px;
                font-size: 13px;
            }
            QPushButton#btnSave:hover {
                background-color: #ff4785;
            }
            QPushButton#btnRun {
                background-color: #16362d;
                color: #00ffcc;
                border: 1px solid #00ffcc;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton#btnRun:hover {
                background-color: #00ffcc;
                color: #0d1e19;
            }
            QPushButton#btnDelete {
                background-color: #381d24;
                color: #ff5c77;
                border: 1px solid #ff5c77;
                padding: 5px 10px;
                font-size: 11px;
            }
            QPushButton#btnDelete:hover {
                background-color: #ff3355;
                color: #ffffff;
            }
            QScrollArea {
                border: 1px solid #2d2445;
                background-color: #161321;
                border-radius: 6px;
            }
            QScrollBar:vertical {
                background: #161321;
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #ff2e70;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

    def _init_ui(self) -> None:
        """Constructs layout and widgets."""
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        # 1. Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(3)
        title_lbl = QLabel("🕷️ Comandas Personalizadas (Macros)")
        title_lbl.setFont(QFont("Segoe UI", 15, QFont.Bold))
        title_lbl.setStyleSheet("color: #ff2e70;")
        header_layout.addWidget(title_lbl)

        sub_lbl = QLabel(
            "Crea accesos directos con tu propio nombre para ejecutar varias acciones automáticas.\n"
            "Ejemplo: 'modo juego' -> abre Discord y Spotify. Se guardan para siempre en tu PC."
        )
        sub_lbl.setStyleSheet("color: #a89bc2; font-size: 11px;")
        sub_lbl.setWordWrap(True)
        header_layout.addWidget(sub_lbl)
        root.addLayout(header_layout)

        # 2. Section: Create New Command Form
        form_frame = QFrame()
        form_frame.setStyleSheet("background-color: #1a1626; border-radius: 8px; padding: 6px;")
        form_layout = QVBoxLayout(form_frame)
        form_layout.setSpacing(8)

        form_title = QLabel("➕ Añadir Nueva Comanda")
        form_title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        form_title.setStyleSheet("color: #00ffcc;")
        form_layout.addWidget(form_title)

        inputs_layout = QHBoxLayout()
        inputs_layout.setSpacing(8)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nombre (ej: modo juego)")
        self.name_input.setFixedWidth(160)
        inputs_layout.addWidget(self.name_input)

        self.actions_input = QLineEdit()
        self.actions_input.setPlaceholderText("Acciones (ej: abre discord y abre spotify)")
        inputs_layout.addWidget(self.actions_input)

        self.save_btn = QPushButton("Guardar")
        self.save_btn.setObjectName("btnSave")
        self.save_btn.clicked.connect(self._handle_save)
        inputs_layout.addWidget(self.save_btn)

        form_layout.addLayout(inputs_layout)
        root.addWidget(form_frame)

        # 3. Section: Saved Commands List
        list_lbl = QLabel("📋 Comandas Guardadas en el Sistema:")
        list_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        root.addWidget(list_lbl)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_layout.setSpacing(8)
        self.scroll_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)
        root.addWidget(self.scroll_area, stretch=1)

        # 4. Footer buttons
        footer_layout = QHBoxLayout()
        hint_lbl = QLabel("💡 Tip: También puedes activar cualquier comanda hablándole a Spider-Man.")
        hint_lbl.setStyleSheet("color: #796c94; font-size: 11px;")
        footer_layout.addWidget(hint_lbl)
        footer_layout.addStretch()

        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.hide)
        footer_layout.addWidget(close_btn)
        root.addLayout(footer_layout)

    def _refresh_list(self) -> None:
        """Clears and re-populates the list of custom commands."""
        # Clear existing items in scroll layout
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        commands = list_commands()
        if not commands:
            empty_lbl = QLabel("No hay comandas guardadas aún. ¡Crea la primera arriba!")
            empty_lbl.setStyleSheet("color: #796c94; font-style: italic; padding: 20px;")
            empty_lbl.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(empty_lbl)
            return

        for cmd in commands:
            cmd_card = self._create_command_card(cmd)
            self.scroll_layout.addWidget(cmd_card)

    def _create_command_card(self, cmd: dict) -> QWidget:
        """Builds a visual card representing a saved command."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #1e192e;
                border: 1px solid #34284d;
                border-radius: 6px;
                padding: 6px 10px;
            }
            QFrame:hover {
                border: 1px solid #ff2e70;
            }
        """)
        h_layout = QHBoxLayout(card)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(10)

        # Info column
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_lbl = QLabel(f"⚡ {cmd['name'].upper()}")
        name_lbl.setFont(QFont("Segoe UI", 11, QFont.Bold))
        name_lbl.setStyleSheet("color: #00ffcc;")
        info_layout.addWidget(name_lbl)

        raw_acts = cmd.get("actions", [])
        if isinstance(raw_acts, str):
            raw_acts = [raw_acts]
        actions_str = "  ➔  ".join(raw_acts)
        actions_lbl = QLabel(actions_str)
        actions_lbl.setStyleSheet("color: #dfd7ef; font-size: 11px;")
        actions_lbl.setWordWrap(True)
        info_layout.addWidget(actions_lbl)

        h_layout.addLayout(info_layout, stretch=1)

        # Actions buttons
        run_btn = QPushButton("▶ Probar")
        run_btn.setObjectName("btnRun")
        run_btn.setToolTip("Ejecutar esta comanda inmediatamente")
        cmd_name = cmd["name"]
        run_btn.clicked.connect(lambda _, n=cmd_name: self._handle_run(n))
        h_layout.addWidget(run_btn)

        del_btn = QPushButton("🗑️ Borrar")
        del_btn.setObjectName("btnDelete")
        del_btn.setToolTip("Eliminar esta comanda permanentemente")
        del_btn.clicked.connect(lambda _, n=cmd_name: self._handle_delete(n))
        h_layout.addWidget(del_btn)

        return card

    def _handle_save(self) -> None:
        """Validates and saves a new command."""
        name = self.name_input.text().strip()
        actions = self.actions_input.text().strip()

        if not name:
            QMessageBox.warning(self, "Atención", "Por favor introduce un nombre para la comanda (ej: 'modo juego').")
            self.name_input.setFocus()
            return

        if not actions:
            QMessageBox.warning(self, "Atención", "Por favor indica al menos una acción (ej: 'abre discord y abre spotify').")
            self.actions_input.setFocus()
            return

        res = save_command(name, actions)
        if res:
            self.name_input.clear()
            self.actions_input.clear()
            self._refresh_list()
        else:
            QMessageBox.critical(self, "Error", "No se pudo guardar la comanda. Revisa los datos.")

    def _handle_run(self, cmd_name: str) -> None:
        """Emits signal to run the command through Capri."""
        self.command_executed.emit(cmd_name)

    def _handle_delete(self, cmd_name: str) -> None:
        """Confirms and deletes the specified command."""
        ans = QMessageBox.question(
            self,
            "Eliminar Comanda",
            f"¿Estás seguro de que deseas eliminar la comanda '{cmd_name}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans == QMessageBox.Yes:
            delete_command(cmd_name)
            self._refresh_list()
