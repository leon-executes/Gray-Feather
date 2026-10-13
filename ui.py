"""Native Gray Feather workspace. The service owns credentials, data and audio."""
from __future__ import annotations

from safe_speech import mask as safe_mask

import copy
import datetime as dt
import threading
import time
import uuid
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, QSize, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence, QIcon, QPainter, QPen, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDockWidget,
    QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter, QStatusBar,
    QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QLayout,
    QGraphicsOpacityEffect, QStyle, QStyleOptionButton, QButtonGroup,
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def provider_label(code: str) -> str:
    return {"google_web": "Google Translate", "bing_web": "Microsoft Bing",
            "mymemory": "MyMemory", "lingva": "Lingva", "azure": "Microsoft Azure",
            "google": "Google Cloud", "deepl": "DeepL", "original": "Original text",
            "offline": "Offline recognition", "hy_mt_local": "Hy-MT · retired engine",
            "gemma_local": "Gemma · retired engine", "index_local": "Index · retired offline engine", "omnilingual": "Omnilingual · offline recognition", "index_web": "Index Translate · free AI", "reinforced": "Reinforced translation"}.get(str(code), str(code))


_INFORMATIONAL_CHECKS = {"independent_review", "backtranslation", "fallback", "review_conditions", "dictation_advisory", "reinforcement_applied"}
_ADVISORY_CHECKS = {"review_failed", "review_unavailable", "backtranslation_failed", "negation"}


def review_messages(turn: dict | None, *, playback: bool = False) -> list[str]:
    """Keep route/comparison provenance out of attention and playback warnings."""
    turn = turn or {}
    excluded = _INFORMATIONAL_CHECKS | (_ADVISORY_CHECKS if playback else set())
    checks = turn.get("checks") or turn.get("metadata", {}).get("checks") or []
    by_message = {str(item.get("message", "")): str(item.get("code", ""))
                  for item in checks if isinstance(item, dict)}
    messages = []
    for item in turn.get("warnings", []):
        message = str(item.get("message", "")) if isinstance(item, dict) else str(item)
        code = str(item.get("code", "")) if isinstance(item, dict) else by_message.get(message, "")
        if message and code not in excluded:
            messages.append(message)
    return messages


def needs_review(turn: dict | None) -> bool:
    return bool(review_messages(turn))


def button(text: str, name: str = "", primary: bool = False) -> QPushButton:
    value = QPushButton(text)
    value.setAccessibleName(name or text)
    value.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        value.setProperty("kind", "primary")
    return value


def label(text: str, kind: str = "") -> QLabel:
    value = QLabel(text)
    value.setWordWrap(True)
    if kind:
        value.setProperty("kind", kind)
    return value


def direction(editor: QPlainTextEdit, rtl: bool) -> None:
    value = Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight
    editor.setLayoutDirection(value)
    option = editor.document().defaultTextOption()
    option.setTextDirection(value)
    option.setAlignment(Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft)
    editor.document().setDefaultTextOption(option)


class CheckBox(QCheckBox):
    """Keep a visible tick when the theme supplies a custom indicator border."""
    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not self.isChecked():
            return
        option = QStyleOptionButton()
        self.initStyleOption(option)
        rect = self.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, self)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(self.foregroundRole()), 1.8))
        painter.drawLine(rect.left() + 4, rect.center().y(), rect.left() + 7, rect.bottom() - 4)
        painter.drawLine(rect.left() + 7, rect.bottom() - 4, rect.right() - 3, rect.top() + 4)
        painter.end()


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()
    preview = Signal(object)


class Worker(QRunnable):
    def __init__(self, operation: Callable[[], Any]):
        super().__init__()
        self.operation = operation
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.result.emit(self.operation())
        except Exception as exc:
            self.signals.error.emit(str(exc) or "The operation could not be completed.")
        finally:
            self.signals.finished.emit()


def line_icon(kind: str, color: str = "#bdc9c3") -> QIcon:
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.6))
    if kind == "copy":
        painter.drawRoundedRect(6, 6, 10, 12, 1.5, 1.5)
        painter.drawLine(3, 13, 3, 2)
        painter.drawLine(3, 2, 12, 2)
    elif kind == "record":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 6, 8, 8)
    elif kind == "listen":
        painter.drawLine(5, 4, 5, 16)
        painter.drawLine(5, 4, 15, 10)
        painter.drawLine(15, 10, 5, 16)
    elif kind == "close":
        painter.setPen(QPen(QColor(color), 1.2))
        painter.drawLine(3, 3, 17, 17)
        painter.drawLine(17, 3, 3, 17)
    painter.end()
    return QIcon(pixmap)


class SpeakerPanel(QFrame):
    translate_requested = Signal(str)
    record_requested = Signal(str)
    listen_requested = Signal(str)
    review_requested = Signal(str)
    language_changed = Signal(str)
    draft_changed = Signal()

    def __init__(self, number: str, languages: list[dict]):
        super().__init__()
        self.number = number
        self.languages = {x["code"]: x for x in languages}
        self.received_turn = None
        self.preview_active = False
        self.setObjectName("speakerPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        heading = QHBoxLayout()
        heading.addWidget(label(f"Speaker {number}", "speaker"))
        self.language = QComboBox()
        self.language.setAccessibleName(f"Speaker {number} language")
        self.language.setMinimumWidth(140)
        self.language.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.language.setMinimumContentsLength(14)
        self.language.setMaxVisibleItems(18)
        for entry in languages:
            native, name = entry.get("native", ""), entry.get("name", entry["code"])
            self.language.addItem(name if name == native else f"{name} · {native}", entry["code"])
        heading.addStretch()
        heading.addWidget(self.language, 1)
        layout.addLayout(heading)

        self.source_box = QFrame()
        self.source_box.setObjectName("editorBox")
        source_layout = QVBoxLayout(self.source_box)
        source_layout.setContentsMargins(9, 5, 9, 9)
        source_layout.setSpacing(3)
        top = QHBoxLayout()
        top.addStretch()
        self.source_copy = button("", f"Copy speaker {number} source text")
        self.source_copy.setObjectName("iconButton")
        self.source_copy.setFixedSize(30, 27)
        self.source_copy.setToolTip("Copy source text")
        self.source_copy.setIcon(line_icon("copy"))
        top.addWidget(self.source_copy)
        source_layout.addLayout(top)
        self.source = QPlainTextEdit()
        self.source.setObjectName("sourceEditor")
        self.source.setAccessibleName(f"Speaker {number} original text to translate")
        self.source.setPlaceholderText("Type here, or record your words…")
        self.source.setMinimumHeight(94)
        self.source.setTabChangesFocus(True)
        source_layout.addWidget(self.source, 1)
        self.dictation_preview = QPlainTextEdit()
        self.dictation_preview.setObjectName("dictationPreview")
        self.dictation_preview.setReadOnly(True)
        self.dictation_preview.setMinimumHeight(72)
        self.dictation_preview.setMaximumHeight(100)
        self.dictation_preview.setAccessibleName(f"Speaker {number} provisional recognition, not saved")
        self.dictation_preview.hide()
        source_layout.addWidget(self.dictation_preview)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.record_button = button("Record Speech", f"Record speaker {number}")
        self.record_button.setProperty("kind", "record")
        self.record_button.setIcon(line_icon("record", "#89968f"))
        self.record_button.setToolTip("Speak, then Stop. Final words are translated automatically.")
        self.translate_button = button("Translate →", f"Translate speaker {number}", True)
        self.translate_button.setToolTip("Translate this turn. Ctrl+Enter in the text field.")
        controls.addWidget(self.record_button)
        controls.addWidget(self.translate_button)
        controls.addStretch()
        source_layout.addLayout(controls)
        layout.addWidget(self.source_box, 1)
        self.count = label("0 characters", "muted")
        self.count.hide()
        self.capability_note = label("", "muted")
        self.capability_note.setMinimumHeight(16)
        layout.addWidget(self.capability_note)

        self.received_label = label("Translation", "eyebrow")
        layout.addWidget(self.received_label)
        self.received_box = QFrame()
        self.received_box.setObjectName("editorBox")
        translated_layout = QVBoxLayout(self.received_box)
        translated_layout.setContentsMargins(9, 9, 9, 9)
        translated_layout.setSpacing(7)
        self.received = QPlainTextEdit()
        self.received.setObjectName("receivedEditor")
        self.received.setReadOnly(True)
        self.received.setAccessibleName(f"Translation of speaker {number}'s source")
        self.received.setPlaceholderText("Your translation will appear here.")
        self.received.setMinimumHeight(95)
        self.received.setTabChangesFocus(True)
        translated_layout.addWidget(self.received, 1)
        self.translation_preview_label = label("Live translation · provisional · not saved or spoken", "preview")
        self.translation_preview_label.hide()
        translated_layout.addWidget(self.translation_preview_label)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.listen_button = button("Listen", f"Read speaker {number} translation")
        self.listen_button.setIcon(line_icon("listen"))
        self.copy_button = button("", f"Copy speaker {number} translation")
        self.copy_button.setObjectName("iconButton")
        self.copy_button.setIcon(line_icon("copy"))
        self.copy_button.setToolTip("Copy translation")
        self.copy_button.setFixedWidth(36)
        self.review_button = button("Review", f"Review speaker {number} translation")
        for control in (self.listen_button, self.copy_button, self.review_button):
            control.setEnabled(False)
            actions.addWidget(control)
        actions.addStretch()
        translated_layout.addLayout(actions)
        layout.addWidget(self.received_box, 1)
        self.received_warning = label("", "warning")
        self.received_warning.hide()
        layout.addWidget(self.received_warning)
        self.record_opacity = QGraphicsOpacityEffect(self.record_button)
        self.record_button.setGraphicsEffect(self.record_opacity)
        self.record_pulse = QPropertyAnimation(self.record_opacity, b"opacity", self)
        self.record_pulse.setDuration(1100)
        self.record_pulse.setStartValue(1.0)
        self.record_pulse.setKeyValueAt(0.5, 0.55)
        self.record_pulse.setEndValue(1.0)
        self.record_pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.record_pulse.setLoopCount(-1)
        self.source.textChanged.connect(self._changed)
        self.language.currentIndexChanged.connect(self._language_changed)
        self.translate_button.clicked.connect(lambda: self.translate_requested.emit(self.number))
        self.record_button.clicked.connect(lambda: self.record_requested.emit(self.number))
        self.listen_button.clicked.connect(lambda: self.listen_requested.emit(self.number))
        self.review_button.clicked.connect(lambda: self.review_requested.emit(self.number))
        self.copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.received.toPlainText()))
        self.source_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.source.toPlainText()))
        self._language_changed()

    def code(self) -> str:
        return str(self.language.currentData() or "en")

    def set_code(self, code: str) -> None:
        index = self.language.findData(code)
        if index >= 0:
            self.language.setCurrentIndex(index)

    def _changed(self) -> None:
        self.count.setText(f"{len(self.source.toPlainText()):,} characters")
        self.draft_changed.emit()

    def _language_changed(self) -> None:
        direction(self.source, bool(self.languages.get(self.code(), {}).get("rtl")))
        self.language_changed.emit(self.number)

    def set_recording(self, state: str | None) -> None:
        active = state == "recording"
        self.record_button.setProperty("recording", active)
        self.record_button.style().unpolish(self.record_button)
        self.record_button.style().polish(self.record_button)
        self.record_button.setIcon(line_icon("record", "#f6d2d0" if active else "#89968f"))
        self.record_button.setText("Stop Recording" if active else "Transcribing…" if state == "transcribing" else "Record Speech")
        if active:
            if self.record_pulse.state() != QPropertyAnimation.State.Running:
                self.record_pulse.start()
        else:
            self.record_pulse.stop()
            self.record_opacity.setOpacity(1.0)

    def clear_preview(self) -> None:
        self.preview_active = False
        self.dictation_preview.hide()
        self.translation_preview_label.hide()

    def show_preview(self, text: str, translated: str | None = None) -> None:
        self.preview_active = True
        self._preview_translation = translated or ""
        self.dictation_preview.setPlainText("Live words · provisional\n" + text)
        self.dictation_preview.show()
        self.received_turn = None
        self.received.setPlainText(safe_mask(translated or "", getattr(self, "safe_speech", True)))
        self.translation_preview_label.setText("Live translation · provisional · not saved or spoken" if translated else "Live translation pending · provisional")
        self.translation_preview_label.show()
        self.received_label.setText("Live translation")
        for control in (self.listen_button, self.copy_button, self.review_button):
            control.setEnabled(False)
        self.received_warning.hide()

    def show_received(self, turn: dict | None) -> None:
        self.clear_preview()
        self.received_turn = turn
        text = str((turn or {}).get("translated_text", ""))
        self.received.setPlainText(safe_mask(text, getattr(self, "safe_speech", True)))
        target = (turn or {}).get("target_lang", "")
        direction(self.received, bool(self.languages.get(target, {}).get("rtl")))
        for control in (self.copy_button, self.listen_button, self.review_button):
            control.setEnabled(bool(text))
        provider = str((turn or {}).get("provider", ""))
        self.received_label.setText("Translation" + (f" · {provider_label(provider)}" if provider else ""))
        warnings = review_messages(turn)
        self.received_warning.setVisible(bool(warnings))
        self.received_warning.setText("Review before use: " + " · ".join(str(x) for x in warnings[:2]))


class SettingsPane(QWidget):
    saved = Signal(dict)
    reset_requested = Signal()
    check_voices_requested = Signal()

    def __init__(self, settings: dict):
        super().__init__()
        self.original = copy.deepcopy(settings)
        self.ready = False
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(500)
        self.debounce.timeout.connect(self._save)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(10)
        appearance = QFormLayout()
        appearance.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        layout.addWidget(label("Appearance", "section"))
        self.theme = QComboBox()
        self.theme.setAccessibleName("Appearance theme")
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Day", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.get("theme", "dark"))))
        appearance.addRow("Theme", self.theme)
        self.text_size = QSpinBox()
        self.text_size.setAccessibleName("Reading text size")
        self.text_size.setRange(10, 24)
        self.text_size.setSuffix(" pt")
        self.text_size.setValue(int(settings.get("text_size", 12)))
        appearance.addRow("Text size", self.text_size)
        layout.addLayout(appearance)
        self.reset = button("Reset preferences", "Reset appearance and service preferences; keep history and saved credentials")
        self.reset.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset)
        self._separator(layout)
        layout.addWidget(label("Services", "section"))
        services = QFormLayout()
        services.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.provider = QComboBox()
        self.provider.setAccessibleName("Translation provider")
        for name, value in (("Automatic · reinforced free engines", "auto"), ("Reinforced · compare and repair", "reinforced"), ("Index Translate · free AI", "index_web"), ("Google Translate · free", "google_web"), ("Microsoft Bing · free", "bing_web"), ("MyMemory · free", "mymemory"), ("Azure · optional API", "azure"), ("Google Cloud · optional API", "google"), ("DeepL · optional API", "deepl")):
            self.provider.addItem(name, value)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.get("provider", "auto"))))
        services.addRow("Translation", self.provider)
        self.speech_provider = QComboBox()
        self.speech_provider.setAccessibleName("Speech recognition service")
        self.speech_provider.setToolTip("Automatic uses measured language-specific routing with bundled local reserves. Omnilingual covers ten tested language routes; short clips can still be misidentified.")
        for name, value in (("Automatic · no key", "auto"), ("Google speech · free online", "google_web"), ("Whisper · offline recognition", "offline"), ("Omnilingual · offline multilingual", "omnilingual"), ("Azure Speech · optional API", "azure"), ("Google Cloud Speech · optional API", "google")):
            self.speech_provider.addItem(name, value)
        self.speech_provider.setCurrentIndex(max(0, self.speech_provider.findData(settings.get("speech_provider", "auto"))))
        services.addRow("Dictation", self.speech_provider)
        self.voice_provider = QComboBox()
        self.voice_provider.setAccessibleName("Voice playback service")
        for name, value in (("Automatic · free voices", "auto"), ("Offline · bundled and Windows voices", "offline"), ("Basic · offline robotic voice", "basic"), ("Microsoft voices · free", "edge_free"), ("Google voice · free", "google_web"), ("Installed Windows voices", "windows"), ("Azure Speech · optional API", "azure")):
            self.voice_provider.addItem(name, value)
        self.voice_provider.setCurrentIndex(max(0, self.voice_provider.findData(settings.get("voice_provider", "auto"))))
        services.addRow("Voice playback", self.voice_provider)
        layout.addLayout(services)
        layout.addWidget(label("Free services require no account. Online services receive the text or audio they process. Unsupported languages remain available as text.", "muted"))
        self.free_fallback = CheckBox("Try another free translation engine if needed")
        self.free_fallback.setChecked(bool(settings.get("free_fallback", True)))
        layout.addWidget(self.free_fallback)
        self.auto_speak = CheckBox("Voice enabled · read completed translations automatically")
        self.auto_speak.setChecked(bool(settings.get("voice_enabled", settings.get("auto_speak", True))))
        self.auto_speak.setToolTip("Turns with actionable checks require review before playback.")
        layout.addWidget(self.auto_speak)
        self.check_voices = button("Check Windows voices", "Check installed exact-language Windows voices")
        self.check_voices.clicked.connect(self.check_voices_requested.emit)
        layout.addWidget(self.check_voices)
        self.voice_feedback = label("", "muted")
        self.voice_feedback.hide()
        layout.addWidget(self.voice_feedback)
        self._separator(layout)
        layout.addWidget(label("Translation review", "section"))
        self.reinforce = CheckBox("Improve final translation automatically")
        self.reinforce.setChecked(bool(settings.get("reinforce", True)))
        self.reinforce.setToolTip("Compare complete translations and repair verifiable conflicts against the source. Earlier wording remains in Review.")
        self.backtranslate = CheckBox("Show advisory back translation")
        self.backtranslate.setChecked(bool(settings.get("backtranslate", True)))
        self.backtranslate.setToolTip("Round-trip wording is advisory and never measures accuracy.")
        layout.addWidget(self.reinforce)
        layout.addWidget(self.backtranslate)
        layout.addWidget(label("Numbers, references, links and measurements are checked. Review meaning and terminology before relying on a translation.", "muted"))
        self.context_toggle = button("Approved context · DeepL only", "Expand optional DeepL translation context")
        self.context_toggle.setCheckable(True)
        layout.addWidget(self.context_toggle)
        self.context = QPlainTextEdit(str(settings.get("context", "")))
        self.context.setAccessibleName("Approved translation context, used by DeepL only")
        self.context.setPlaceholderText("Optional subject or approved terminology.")
        self.context.setMaximumHeight(100)
        self.context.setVisible(bool(settings.get("context")))
        self.context_toggle.setChecked(bool(settings.get("context")))
        self.context_toggle.toggled.connect(self.context.setVisible)
        layout.addWidget(self.context)
        self._separator(layout)
        self.keys, self.removals = {}, {}
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName("Translation provider credentials")
        providers = settings.get("providers", {})
        for name, title in (("azure", "Azure"), ("google", "Google"), ("deepl", "DeepL")):
            page = QWidget()
            fields = QFormLayout(page)
            fields.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
            key = QLineEdit()
            key.setEchoMode(QLineEdit.EchoMode.Password)
            key.setAccessibleName(f"{title} API key")
            configured = bool(providers.get(name, {}).get("key") or providers.get(name, {}).get("configured"))
            key.setPlaceholderText("Saved · leave blank to keep" if configured else "Optional API key")
            self.keys[name] = key
            fields.addRow("API key", key)
            self.removals[name] = CheckBox("Remove saved key")
            self.removals[name].setAccessibleName(f"Remove saved {title} key")
            fields.addRow(self.removals[name])
            if name == "azure":
                self.region = QLineEdit(str(providers.get(name, {}).get("region", "")))
                self.region.setAccessibleName("Azure Translator region")
                fields.addRow("Resource region", self.region)
                self.azure_endpoint = QLineEdit(str(providers.get(name, {}).get("endpoint", "")))
                self.azure_endpoint.setAccessibleName("Azure Translator endpoint")
                fields.addRow("Endpoint · optional", self.azure_endpoint)
            if name == "deepl":
                self.deepl_free = CheckBox("DeepL API Free account")
                self.deepl_free.setChecked(bool(providers.get(name, {}).get("free", True)))
                fields.addRow(self.deepl_free)
                self.deepl_glossary = QLineEdit(str(providers.get(name, {}).get("glossary_id", "")))
                self.deepl_glossary.setAccessibleName("DeepL glossary identifier")
                fields.addRow("Glossary ID · optional", self.deepl_glossary)
            self.tabs.addTab(page, title)
        self.credentials_toggle = button("Optional API accounts", "Show optional translation API credentials")
        self.credentials_toggle.setCheckable(True)
        self.credentials_toggle.toggled.connect(self.tabs.setVisible)
        self.tabs.hide()
        layout.addWidget(self.credentials_toggle)
        layout.addWidget(self.tabs)
        self.speech_accounts = QWidget()
        speech_fields = QFormLayout(self.speech_accounts)
        speech_fields.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.speech_key = QLineEdit()
        self.speech_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.speech_key.setAccessibleName("Speech resource API key")
        self.speech_key.setPlaceholderText("Saved · leave blank to keep" if settings.get("speech_key") or settings.get("speech_configured") else "Optional speech API key")
        speech_fields.addRow("Speech API key", self.speech_key)
        self.remove_speech = CheckBox("Remove saved speech key")
        speech_fields.addRow(self.remove_speech)
        self.speech_region = QLineEdit(str(settings.get("speech_region", "")))
        self.speech_region.setAccessibleName("Azure Speech region")
        speech_fields.addRow("Azure Speech region", self.speech_region)
        layout.addWidget(self.speech_accounts)
        self._speech_changed()
        self.feedback = label("Changes apply automatically", "muted")
        layout.addWidget(self.feedback)
        # Kept as a callable compatibility action for keyboard/tests; no Save step.
        self.apply = button("Apply preferences")
        self.apply.hide()
        self.apply.clicked.connect(self._save)
        layout.addStretch()
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.speech_provider.currentIndexChanged.connect(self._speech_changed)
        self.voice_provider.currentIndexChanged.connect(self._speech_changed)
        for control in (self.provider, self.speech_provider, self.voice_provider, self.theme):
            control.currentIndexChanged.connect(self._save)
        self.text_size.valueChanged.connect(self._save)
        for control in (self.free_fallback, self.auto_speak, self.reinforce, self.backtranslate, self.deepl_free, self.remove_speech, *self.removals.values()):
            control.toggled.connect(self._save)
        for control in (*self.keys.values(), self.region, self.azure_endpoint, self.deepl_glossary, self.speech_key, self.speech_region):
            control.textEdited.connect(lambda: self.debounce.start())
            control.editingFinished.connect(self._save)
        self.context.textChanged.connect(lambda: self.debounce.start())
        self.ready = True

    @staticmethod
    def _separator(layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setContentsMargins(35, 8, 35, 8)
        line = QFrame()
        line.setObjectName("settingsSeparator")
        line.setFixedHeight(1)
        row.addWidget(line)
        layout.addLayout(row)

    def _provider_changed(self) -> None:
        chosen = self.provider.currentData()
        if chosen in ("azure", "google", "deepl"):
            self.credentials_toggle.setChecked(True)
            self.tabs.setCurrentIndex({"azure": 0, "google": 1, "deepl": 2}[chosen])

    def _speech_changed(self) -> None:
        chosen = self.speech_provider.currentData()
        voice_api = self.voice_provider.currentData() == "azure"
        optional = chosen in ("azure", "google") or voice_api
        self.speech_accounts.setVisible(optional)
        self.speech_key.setEnabled(optional)
        self.remove_speech.setEnabled(optional)
        self.speech_region.setEnabled(chosen == "azure" or voice_api)

    def _save(self, *_: Any) -> None:
        if not self.ready:
            return
        self.debounce.stop()
        result = copy.deepcopy(self.original)
        result.update(provider=self.provider.currentData(), reinforce=self.reinforce.isChecked(), free_fallback=self.free_fallback.isChecked(),
                      backtranslate=self.backtranslate.isChecked(), voice_enabled=self.auto_speak.isChecked(), auto_speak=self.auto_speak.isChecked(),
                      theme=self.theme.currentData(), text_size=self.text_size.value(), voice_provider=self.voice_provider.currentData(),
                      speech_provider=self.speech_provider.currentData(), speech_region=self.speech_region.text().strip(), context=self.context.toPlainText().strip())
        providers = result.setdefault("providers", {})
        for name, key in self.keys.items():
            entry = providers.setdefault(name, {})
            if self.removals[name].isChecked():
                entry["key"] = ""
            elif key.text().strip():
                entry["key"] = key.text().strip()
        providers["azure"].update(region=self.region.text().strip(), endpoint=self.azure_endpoint.text().strip())
        providers["deepl"].update(free=self.deepl_free.isChecked(), glossary_id=self.deepl_glossary.text().strip())
        if self.remove_speech.isChecked():
            result["speech_key"] = ""
        elif self.speech_key.text().strip():
            result["speech_key"] = self.speech_key.text().strip()
        self.saved.emit(result)


class TurnDialog(QDialog):
    def __init__(self, turn: dict, parent: QWidget, languages: dict):
        super().__init__(parent)
        self.turn = turn
        self.host = parent
        self.opinion_events = []
        self.used_providers = [str(turn.get("provider", "")), str(turn.get("review_provider", ""))]
        self.setWindowTitle("Review translation · Gray Feather")
        self.resize(790, 760)
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            self.resize(min(790, screen.availableGeometry().width() - 40), min(760, screen.availableGeometry().height() - 70))
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = self.content_layout
        self._opinion("Primary translation", str(turn.get("translated_text", "")), str(turn.get("provider", "")), languages, True)
        if turn.get("review_text"):
            self._opinion("Second opinion", str(turn["review_text"]), str(turn.get("review_provider", "")), languages, True)
        for number, opinion in enumerate(turn.get("extra_opinions", []), 3):
            self.used_providers.append(str(opinion.get("provider", "")))
            self._opinion(f"Opinion {number}", str(opinion.get("text", "")), str(opinion.get("provider", "")), languages, False)
        self.opinion_slot = QVBoxLayout()
        layout.addLayout(self.opinion_slot)
        self.add_opinion_button = button("Add another opinion", "Request another distinct translation engine opinion")
        self.add_opinion_button.clicked.connect(lambda: self._add_opinion(languages))
        layout.addWidget(self.add_opinion_button)
        self.opinion_feedback = label("", "muted")
        layout.addWidget(self.opinion_feedback)
        self._opinion_availability()
        if turn.get("backtranslation"):
            back = self._fold("Advisory back translation · " + provider_label(str(turn.get("backtranslation_provider", ""))), str(turn["backtranslation"]), False)
            direction(back, bool(languages.get(turn.get("source_lang"), {}).get("rtl")))
        warnings = [str(x.get("message", "")) if isinstance(x, dict) else str(x) for x in turn.get("warnings", [])]
        if warnings:
            self._fold("Checks and notes", "\n\n".join(warnings), True)
        capture = turn.get("dictation", {})
        if capture:
            description = ["Final recognition · " + provider_label(str(capture.get("provider", ""))),
                           "Recording duration: " + str(round(float(capture.get("duration_ms", 0)) / 1000, 1)) + " seconds",
                           "Complete recording" if capture.get("complete", True) and not capture.get("limit_reached") else "Recording may be incomplete"]
            description.extend(str(x) for x in capture.get("warnings", []))
            description.extend(str(x) for x in capture.get("trace", []))
            self._fold("Dictation details · " + provider_label(str(capture.get("provider", ""))), "\n\n".join(description), False)
        original = self._fold("Original words · preserved", str(turn.get("raw_source", "")), False)
        direction(original, bool(languages.get(turn.get("source_lang"), {}).get("rtl")))
        self.reviewed = self._section("Reviewed source", str(turn.get("reviewed_source", turn.get("raw_source", ""))), "reviewed_source", languages, False)
        layout.addWidget(label("An opinion is another translation, not a certificate of accuracy. Editing the reviewed source preserves your original words.", "muted"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        if turn.get("review_text"):
            self.copy_second_opinion = buttons.addButton("Copy second opinion", QDialogButtonBox.ButtonRole.ActionRole)
            self.copy_second_opinion.setAccessibleName("Copy full second engine translation")
            self.copy_second_opinion.clicked.connect(lambda: QApplication.clipboard().setText(safe_mask(str(turn["review_text"]), self.host.preferences.get("safe_speech", True))))
        buttons.addButton("Retranslate reviewed source", QDialogButtonBox.ButtonRole.AcceptRole).setProperty("kind", "primary")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _section(self, title: str, text: str, key: str, languages: dict, readonly: bool) -> QPlainTextEdit:
        self.content_layout.addWidget(label(title, "section"))
        editor = QPlainTextEdit(text)
        editor.setAccessibleName(title)
        editor.setReadOnly(readonly)
        editor.setMinimumHeight(85)
        editor.setMaximumHeight(145)
        direction(editor, bool(languages.get(self.turn.get("target_lang" if key == "translated_text" else "source_lang"), {}).get("rtl")))
        self.content_layout.addWidget(editor)
        return editor

    def _fold(self, title: str, text: str, expanded: bool, slot: QVBoxLayout | None = None) -> QPlainTextEdit:
        slot = slot or self.content_layout
        toggle = button(("▾ " if expanded else "▸ ") + title, title)
        toggle.setProperty("kind", "fold")
        toggle.setCheckable(True)
        toggle.setChecked(expanded)
        editor = QPlainTextEdit(safe_mask(text, self.host.preferences.get("safe_speech", True)))
        editor.setAccessibleName(title)
        editor.setReadOnly(True)
        editor.setMinimumHeight(100)
        editor.setMaximumHeight(250)
        editor.setVisible(expanded)
        toggle.toggled.connect(editor.setVisible)
        toggle.toggled.connect(lambda checked: toggle.setText(("▾ " if checked else "▸ ") + title))
        slot.addWidget(toggle)
        slot.addWidget(editor)
        return editor

    def _opinion(self, title: str, text: str, provider: str, languages: dict, expanded: bool, slot: QVBoxLayout | None = None) -> None:
        provenance = " · mixed sources; not independent" if provider == "mymemory" else ""
        editor = self._fold(title + " · " + provider_label(provider) + provenance, text, expanded, slot)
        direction(editor, bool(languages.get(self.turn.get("target_lang"), {}).get("rtl")))

    def _opinion_availability(self) -> None:
        service = getattr(self.host, "service", None)
        available = ()
        if hasattr(service, "available_opinion_providers"):
            try:
                available = service.available_opinion_providers(self.turn.get("source_lang"), self.turn.get("target_lang"), self.used_providers)
            except Exception as exc:
                self.opinion_feedback.setText(str(exc))
        self.add_opinion_button.setEnabled(bool(available) and len([x for x in self.used_providers if x]) < 4)
        if not available:
            self.opinion_feedback.setText("No additional distinct free engine is available for this language pair.")

    def _add_opinion(self, languages: dict) -> None:
        service = getattr(self.host, "service", None)
        if not hasattr(service, "add_opinion"):
            return
        if self.reviewed.toPlainText() != str(self.turn.get("reviewed_source", self.turn.get("raw_source", ""))):
            self.opinion_feedback.setText("Retranslate your edited source first so opinions refer to the same words.")
            return
        event = threading.Event()
        self.opinion_events.append(event)
        self.add_opinion_button.setEnabled(False)
        self.opinion_feedback.setText("Requesting another distinct engine…")
        def ready(value: Any) -> None:
            if event.is_set():
                return
            result = dict(value)
            provider, text = str(result.get("provider", "")), str(result.get("text", ""))
            if not text.strip() or provider in self.used_providers:
                failed(str(result.get("reason", "No distinct complete opinion was returned.")))
                return
            self.used_providers.append(provider)
            self.turn.setdefault("extra_opinions", []).append(result)
            self._opinion(f"Opinion {len([x for x in self.used_providers if x])}", text, provider, languages, True, self.opinion_slot)
            self.host._save()
            self.host._refresh_turns(select_id=self.turn["id"])
            self.opinion_feedback.setText("Opinion added · " + provider_label(provider))
            self._opinion_availability()
        def failed(message: str) -> None:
            if event.is_set():
                return
            self.opinion_feedback.setText("Opinion unavailable: " + message)
            self._opinion_availability()
        self.host._run(lambda: service.add_opinion(self.turn.get("reviewed_source", self.turn.get("raw_source", "")), self.turn["source_lang"], self.turn["target_lang"], list(self.used_providers), event), ready, failed, event=event)

    def done(self, result: int) -> None:
        for event in self.opinion_events:
            event.set()
        super().done(result)


class MainWindow(QMainWindow):
    def __init__(self, service: Any):
        super().__init__()
        self.service = service
        self.preferences = dict(service.settings())
        self.languages = list(service.languages)
        self.language_by_code = {x["code"]: x for x in self.languages}
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.jobs: dict[str, tuple[Worker, threading.Event]] = {}
        self.cancelled_tokens: set[str] = set()
        self.translation_token = self.recording_token = self.voice_token = None
        self.recording_side = None
        self.record_context = None
        self.preview_token = None
        self.preview_generation = 0
        self.preview_signals = WorkerSignals(self)
        self.preview_signals.preview.connect(self._recording_preview, Qt.ConnectionType.QueuedConnection)
        self.voice_signals = WorkerSignals(self)
        self.voice_signals.preview.connect(self._voice_prepared, Qt.ConnectionType.QueuedConnection)
        self.voice_event = None
        self.draft_versions = {"1": 0, "2": 0}
        self.draft_snapshots = {"1": "", "2": ""}
        self.conversation = self._empty_conversation()
        self.loading = self.unsaved = self.closed = False
        self.undo_snapshot = None
        self.setWindowTitle("Gray Feather")
        self.setAccessibleName("Gray Feather translation workspace")
        self.setMinimumSize(780, 720)
        self.resize(1180, 1000)
        self._build()
        self._shortcuts()
        self.draft_timer = QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.setInterval(350)
        self.draft_timer.timeout.connect(self._save)
        self.recording_timer = QTimer(self)
        self.recording_timer.setInterval(250)
        self.recording_timer.timeout.connect(self._recording_tick)
        self.recording_phase = None
        self.recording_started = 0.0
        self.loading = True
        self.panels["1"].set_code(str(self.preferences.get("source1", "en")))
        self.panels["2"].set_code(str(self.preferences.get("source2", "fr")))
        self.loading = False
        self._apply_theme()
        self._refresh_capabilities()
        self._refresh_history()
        self._refresh_turns()
        self._load_last_draft()
        self._set_status("Ready", "Free translation · Record then Stop to dictate · Saved on this PC")
        self._fit_to_screen(center=True)
        if self.preferences.get("notice"):
            self.notice.setText(self.preferences["notice"])
            self.notice.show()

    def _fit_to_screen(self, center: bool = False) -> None:
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        width = max(360, available.width() - 32)
        height = max(300, available.height() - 48)
        self.setMinimumSize(min(780, width), min(620, height))
        self.resize(min(self.width(), width), min(self.height(), height))
        frame = self.frameGeometry()
        if center:
            frame.moveCenter(available.center())
        else:
            frame.moveLeft(max(available.left(), min(frame.left(), available.right() - frame.width() + 1)))
            frame.moveTop(max(available.top(), min(frame.top(), available.bottom() - frame.height() + 1)))
        self.move(frame.topLeft())

    @staticmethod
    def _empty_conversation() -> dict:
        return {"id": uuid.uuid4().hex, "title": "Conversation", "created_at": now(), "turns": [], "drafts": {"1": "", "2": ""}}

    def _build(self) -> None:
        central = QWidget()
        self.central_scroll = QScrollArea()
        self.central_scroll.setAccessibleName("Scrollable translation workspace")
        self.central_scroll.setWidgetResizable(True)
        self.central_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.central_scroll.setWidget(central)
        self.setCentralWidget(self.central_scroll)
        layout = QVBoxLayout(central)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(22, 20, 22, 12)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(label("Gray Feather", "brand"))
        header.addStretch()
        credits = QVBoxLayout()
        credits.setSpacing(1)
        self.credit_links = []
        for before, linked, after, url in (("By ", "Forumark", "’s Creators", "https://forumark.com"), ("Check ", "GitHub", " for more", "https://github.com/leon-executes")):
            credit = label(f'{before}<a href="{url}">{linked}</a>{after}', "credit")
            credit.setOpenExternalLinks(True)
            credit.setWordWrap(False)
            credit.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            credit.setAlignment(Qt.AlignmentFlag.AlignRight)
            credits.addWidget(credit)
            self.credit_links.append((credit, before, linked, after, url))
        header.addLayout(credits)
        layout.addLayout(header)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.new_button = button("Clear Session", "Start a clear session; keep this session in saved history")
        self.new_button.clicked.connect(self.new_conversation)
        self.stop_voice_button = button("Halt Voice", "Stop voice playback")
        self.stop_voice_button.setEnabled(False)
        self.stop_voice_button.clicked.connect(self._stop_voice)
        self.export_button = button("Export", "Export this conversation")
        self.export_button.clicked.connect(self.export_conversation)
        for control in (self.new_button, self.stop_voice_button, self.export_button):
            toolbar.addWidget(control)
        self.cancel_button = button("Cancel Task", "Cancel current translation or dictation without committing")
        self.cancel_button.hide()
        self.cancel_button.clicked.connect(self.cancel_jobs)
        toolbar.addWidget(self.cancel_button)
        toolbar.addStretch()
        self.voice_button = button("Enabled", "Enable automatic voice playback")
        self.voice_button.setCheckable(True)
        self.voice_button.setObjectName("voiceToggle")
        self.voice_button.setChecked(bool(self.preferences.get("voice_enabled", self.preferences.get("auto_speak", True))))
        self.voice_button.clicked.connect(lambda: self._toggle_voice(True))
        self.voice_disabled_button = button("Disabled", "Disable automatic voice playback and halt current voice")
        self.voice_disabled_button.setCheckable(True)
        self.voice_disabled_button.setObjectName("voiceDisabled")
        self.voice_group = QButtonGroup(self)
        self.voice_group.setExclusive(True)
        self.voice_group.addButton(self.voice_button)
        self.voice_group.addButton(self.voice_disabled_button)
        self.voice_disabled_button.setChecked(not self.voice_button.isChecked())
        self.voice_disabled_button.clicked.connect(lambda: self._toggle_voice(False))
        self.settings_button = button("Settings", "Open application settings and manual")
        self.settings_button.setObjectName("settingsToggle")
        self.settings_button.clicked.connect(lambda: self._show_settings())
        split = QFrame()
        split.setObjectName("splitControl")
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(6, 6, 6, 6)
        split_layout.setSpacing(0)
        voice_label = label("Voice")
        voice_label.setProperty("kind", "toggleLabel")
        split_layout.addWidget(voice_label)
        split_layout.addWidget(self.voice_button)
        split_layout.addWidget(self.voice_disabled_button)
        safe_split = QFrame()
        safe_split.setObjectName("splitControl")
        safe_layout = QHBoxLayout(safe_split)
        safe_layout.setContentsMargins(6, 6, 6, 6)
        safe_layout.setSpacing(0)
        safe_label = label("Safe Speech")
        safe_label.setProperty("kind", "toggleLabel")
        safe_layout.addWidget(safe_label)
        self.safe_on = button("On", "Mask profanity and slurs in translations and speech")
        self.safe_off = button("Off", "Show and speak the original translation without masking")
        self.safe_on.setObjectName("voiceToggle")
        self.safe_off.setObjectName("voiceDisabled")
        self.safe_group = QButtonGroup(self)
        self.safe_group.setExclusive(True)
        for control in (self.safe_on, self.safe_off):
            control.setCheckable(True)
            self.safe_group.addButton(control)
            safe_layout.addWidget(control)
        self.safe_on.clicked.connect(lambda: self._toggle_safe_speech(True))
        self.safe_off.clicked.connect(lambda: self._toggle_safe_speech(False))
        safe_split.setToolTip("Local profanity/slur masking. Neutral medical and safeguarding terms remain. Original history is preserved; this is not a comprehensive content classifier.")
        toolbar.addWidget(safe_split)
        toolbar.addWidget(split)
        toolbar.addWidget(self.settings_button)
        layout.addLayout(toolbar)
        # Session titles remain persisted and editable from Saved history.
        self.title_edit = QLineEdit("Conversation", self)
        self.title_edit.setMaxLength(160)
        self.title_edit.hide()
        self.save_label = label("Saved automatically", "muted")
        self.save_label.hide()
        self.notice = label("", "notice")
        self.notice.hide()
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.notice)
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.setChildrenCollapsible(False)
        self.speaker_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.speaker_splitter.setChildrenCollapsible(False)
        self.panels = {number: SpeakerPanel(number, self.languages) for number in ("1", "2")}
        for panel in self.panels.values():
            panel.translate_requested.connect(self.translate_side)
            panel.record_requested.connect(self.record_side)
            panel.listen_requested.connect(self.listen_side)
            panel.review_requested.connect(self.review_side)
            panel.language_changed.connect(self._language_changed)
            panel.draft_changed.connect(self._draft_changed)
            self.speaker_splitter.addWidget(panel)
        self.speaker_splitter.setSizes([500, 500])
        self.speaker_scroll = QScrollArea()
        self.speaker_scroll.setAccessibleName("Scrollable speaker workspace")
        self.speaker_scroll.setWidgetResizable(True)
        self.speaker_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.speaker_scroll.setMinimumHeight(240)
        self.speaker_scroll.setWidget(self.speaker_splitter)
        self.main_splitter.addWidget(self.speaker_scroll)
        self.lower_tabs = QTabWidget()
        self.lower_tabs.setAccessibleName("Conversation turns and saved history")
        page = QWidget()
        turns_layout = QVBoxLayout(page)
        turns_layout.setContentsMargins(12, 12, 12, 12)
        self.turn_table = QTableWidget(0, 5)
        self.turn_table.setHorizontalHeaderLabels(["Time", "Speaker", "Original", "Translation", "Review"])
        self.turn_table.setAccessibleName("Conversation turns, double-click to review")
        self.turn_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.turn_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.turn_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.turn_table.setShowGrid(False)
        self.turn_table.setWordWrap(False)
        self.turn_table.verticalHeader().hide()
        self.turn_table.verticalHeader().setDefaultSectionSize(40)
        self.turn_table.setAlternatingRowColors(True)
        header_view = self.turn_table.horizontalHeader()
        # Content autosizing rescans the full table on each insertion and makes
        # large histories quadratic. These short columns have practical widths;
        # users can still resize them, while the two text columns share the rest.
        for index, width in ((0, 72), (1, 64), (4, 132)):
            header_view.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            self.turn_table.setColumnWidth(index, 148 if index == 4 else width)
        for index in (2, 3):
            header_view.setSectionResizeMode(index, QHeaderView.ResizeMode.Stretch)
        self.turn_table.cellDoubleClicked.connect(lambda *_: self.review_selected_turn())
        turns_layout.addWidget(self.turn_table)
        actions = QHBoxLayout()
        self.review_button = button("Review turn", "Review or revise selected turn")
        self.review_button.clicked.connect(self.review_selected_turn)
        self.copy_turn_button = button("Copy turn", "Copy selected original and translation")
        self.copy_turn_button.clicked.connect(self.copy_selected_turn)
        self.delete_turn_button = button("Remove turn", "Remove selected turn with undo")
        self.delete_turn_button.clicked.connect(self.remove_selected_turn)
        self.undo_button = button("Undo removal", "Undo removed or cleared turns")
        self.undo_button.hide()
        self.undo_button.clicked.connect(self.undo_removal)
        self.clear_button = button("Clear turns", "Clear conversation turns with confirmation and undo")
        self.clear_button.clicked.connect(self.clear_turns)
        for value in (self.review_button, self.copy_turn_button, self.delete_turn_button, self.undo_button):
            actions.addWidget(value)
        actions.addStretch()
        actions.addWidget(self.clear_button)
        turns_layout.addLayout(actions)
        self.lower_tabs.addTab(page, "Conversation · 0 turns")
        history = QWidget()
        history_layout = QVBoxLayout(history)
        history_layout.setContentsMargins(12, 12, 12, 12)
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText("Find a saved conversation")
        self.history_search.setAccessibleName("Filter saved conversation titles")
        self.history_search.textChanged.connect(self._filter_history)
        history_layout.addWidget(self.history_search)
        self.history_list = QListWidget()
        self.history_list.setAccessibleName("Saved conversations. Check boxes to delete several; double-click a title to reopen.")
        self.history_list.itemChanged.connect(self._history_check_changed)
        self.history_list.itemDoubleClicked.connect(lambda *_: self.open_history())
        history_layout.addWidget(self.history_list)
        history_actions = QHBoxLayout()
        for text, handler in (("Open", self.open_history), ("Rename", self.rename_history)):
            value = button(text, text + " selected saved conversation")
            value.clicked.connect(handler)
            history_actions.addWidget(value)
        self.delete_history_button = button("Delete selected", "Delete checked sessions, including checked sessions hidden by search")
        self.delete_history_button.setEnabled(False)
        self.delete_history_button.clicked.connect(self.delete_history)
        history_actions.addWidget(self.delete_history_button)
        self.shred_history_button = button("Shred History", "Purge all sessions and the app's automatic history backups")
        self.shred_history_button.setProperty("kind", "destructive")
        self.shred_history_button.clicked.connect(self.shred_history)
        history_actions.addWidget(self.shred_history_button)
        history_actions.addStretch()
        self.backup_button = button("Back up history", "Back up all saved conversations to a SQLite archive")
        self.backup_button.clicked.connect(self.backup_history)
        history_actions.addWidget(self.backup_button)
        history_layout.addLayout(history_actions)
        self.lower_tabs.addTab(history, "Saved sessions")
        self.main_splitter.addWidget(self.lower_tabs)
        self.main_splitter.setSizes([525, 240])
        layout.addWidget(self.main_splitter, 1)
        footer = QHBoxLayout()
        footer.addWidget(label("Ctrl+Enter translate  ·  Alt+1 / Alt+2 focus  ·  Esc stop", "muted"))
        footer.addStretch()
        footer.addWidget(label("Originals preserved", "muted"))
        layout.addLayout(footer)
        self.status = QStatusBar()
        self.status.setSizeGripEnabled(True)
        self.setStatusBar(self.status)
        self.status_heading, self.status_detail = label("Ready", "status"), label("", "muted")
        self.status.addWidget(self.status_heading)
        self.status.addWidget(self.status_detail, 1)
        self.settings_dock = QDockWidget("Settings", self)
        self.settings_dock.setAccessibleName("Application settings drawer")
        self.settings_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.settings_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.settings_dock.setMinimumWidth(340)
        empty_title = QWidget(self.settings_dock)
        empty_title.setFixedHeight(0)
        self.settings_dock.setTitleBarWidget(empty_title)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.settings_dock)
        self.settings_dock.hide()
        self._replace_settings_pane()

    def _replace_settings_pane(self) -> None:
        self.settings_pane = SettingsPane(self.preferences)
        self.settings_pane.saved.connect(self._save_settings)
        self.settings_pane.reset_requested.connect(self._reset_settings)
        self.settings_pane.check_voices_requested.connect(self._check_native_voices)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.settings_pane)
        container = QTabWidget()
        container.setAccessibleName("Settings and manual")
        self.settings_close_button = button("", "Close settings and manual")
        self.settings_close_button.setObjectName("settingsClose")
        self.settings_close_button.setToolTip("Close settings and manual")
        self.settings_close_button.setFixedSize(36, 34)
        self.settings_close_button.setIconSize(QSize(24, 24))
        self.settings_close_button.setIcon(line_icon("close", "#566b61" if self.preferences.get("theme") == "light" else "#adbac2"))
        self.settings_close_button.clicked.connect(self.settings_dock.hide)
        corner = QWidget()
        corner_layout = QHBoxLayout(corner)
        corner_layout.setContentsMargins(0, 0, 8, 0)
        corner_layout.addWidget(self.settings_close_button)
        container.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        container.addTab(scroll, "Settings")
        manual = QScrollArea()
        manual.setWidgetResizable(True)
        manual.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        guide = QVBoxLayout(content)
        guide.setContentsMargins(16, 12, 16, 16)
        for title, explanation in (
            ("Speak or type", "Choose each speaker's language. Record Speech starts a turn. Stop Recording commits the recognized words, translates them and reads the final result when Voice is enabled. Recordings stop at 50 seconds."),
            ("Live previews", "Live words and translations are provisional. They are never saved or spoken. Final recognition uses the completed recording. Review unusual names, quantities and terminology."),
            ("Automatic improvement", "Complete engine outputs are compared before the final result appears. Source-based checks repair supported calendar and critical-detail conflicts automatically. Accurate controls are preserved; engine agreement alone is not treated as proof."),
            ("Online translation, local speech", "Text translation needs internet. Supported bundled recognition and voice routes can run locally. If Index is unavailable, Automatic keeps eligible Google/Bing results and local source-detail checks; AI rewriting waits for the service to recover."),
            ("Review a translation", "Review opens the preserved source, the full engine opinions and advisory back translation. Additional distinct engines appear only when available. MyMemory uses mixed sources and is not an independent opinion."),
            ("Safe Speech", "On masks known profanity and slurs in displayed translations and playback. Off restores unmasked output. Neutral clinical and safeguarding terms are retained. Original history and exports remain unmodified; the filter is not universal."),
            ("Voice controls", "Voice Enabled reads completed translations automatically. Halt Voice stops current playback. Listen plays a final translation again. Flagged turns need your review before playback."),
            ("Your saved work", "Original words remain unchanged. A reviewed source is stored separately. Clear Session opens a fresh session and keeps earlier work in Saved sessions. Removed turns can be restored with Undo."),
            ("Free services and privacy", "Free translation and supported voices need no key. Online routes receive the text or audio they process and can become unavailable. Bundled dictation supports selected languages, including Persian. Basic voices can sound robotic; Dari uses approximate Persian pronunciation. Optional API accounts are available in Settings."),
            ("Useful keys", "Ctrl+Enter translates the focused speaker. Alt+1 and Alt+2 focus a source. Ctrl+N starts a fresh session. Ctrl+S saves. Ctrl+Shift+E exports. Ctrl+, opens Settings. Escape cancels the active task and stops voice."),
            ("Recovery", "Export saves a Word document, readable text, CSV or JSON. Back up history creates a consistent database copy. Move the whole Portable folder to keep the app, bundled models and portable data together."),
        ):
            guide.addWidget(label(title, "section"))
            guide.addWidget(label(explanation, "manual"))
            SettingsPane._separator(guide)
        guide.addStretch()
        manual.setWidget(content)
        container.addTab(manual, "Manual")
        old = self.settings_dock.widget()
        self.settings_dock.setWidget(container)
        if old is not None:
            old.deleteLater()

    def _reset_settings(self) -> None:
        if hasattr(self.service, "reset_settings"):
            try:
                value = self.service.reset_settings()
                self.preferences = dict(value or self.service.settings())
                self._apply_theme()
                self._refresh_capabilities()
                self._replace_settings_pane()
                self._set_status("Preferences reset", "Saved history and credentials are preserved.")
            except Exception as exc:
                self._show_error("Preferences could not be reset: " + str(exc))
        else:
            value = copy.deepcopy(self.preferences)
            value.update(theme="dark", text_size=12, provider="auto", speech_provider="auto", voice_provider="auto", voice_enabled=True, auto_speak=True, safe_speech=True, reinforce=True, backtranslate=True, free_fallback=True)
            self._save_settings(value)
            self._replace_settings_pane()

    def _toggle_safe_speech(self, enabled: bool) -> None:
        self._stop_voice()
        value = copy.deepcopy(self.preferences)
        value['safe_speech'] = enabled
        self.preferences['safe_speech'] = enabled
        self.settings_pane.original['safe_speech'] = enabled
        self._save_settings(value)
        self._apply_theme()
        self._refresh_turns()

    def _toggle_voice(self, enabled: bool) -> None:
        if not enabled:
            self._stop_voice()
        value = copy.deepcopy(self.preferences)
        value.update(voice_enabled=enabled, auto_speak=enabled)
        # Voice intent takes effect even if a disk error prevents persistence.
        self.preferences.update(voice_enabled=enabled, auto_speak=enabled)
        self.settings_pane.original.update(voice_enabled=enabled, auto_speak=enabled)
        self._save_settings(value)
        self.settings_pane.auto_speak.blockSignals(True)
        self.settings_pane.auto_speak.setChecked(enabled)
        self.settings_pane.auto_speak.blockSignals(False)

    def _show_settings(self, force: bool = False) -> None:
        self.settings_dock.setVisible(force or not self.settings_dock.isVisible())
        if self.settings_dock.isVisible():
            self.settings_pane.theme.setFocus()
        self._fit_to_screen()
        QTimer.singleShot(0, self._fit_to_screen)

    def _shortcuts(self) -> None:
        for key, operation in (("Ctrl+Return", self.translate_focused), ("Ctrl+Enter", self.translate_focused),
                               ("Ctrl+N", self.new_conversation), ("Ctrl+S", self._save),
                               ("Ctrl+Shift+E", self.export_conversation), ("Ctrl+,", self._show_settings),
                               ("Escape", self.stop_everything),
                               ("Alt+1", lambda: self.panels["1"].source.setFocus()),
                               ("Alt+2", lambda: self.panels["2"].source.setFocus())):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(operation)
            self.addAction(action)

    def _apply_theme(self) -> None:
        c = ({"bg": "#11161b", "panel": "#1a2229", "field": "#12191f", "line": "#35424b", "text": "#edf2ef", "muted": "#adbac2", "accent": "#c4d7b6", "accentink": "#1d3127", "hover": "#29363e", "warn": "#ebcc99", "notice": "#25352f", "selection": "#354d43"} if self.preferences.get("theme", "dark") != "light" else
             {"bg": "#f2f4ef", "panel": "#ffffff", "field": "#f8faf6", "line": "#c8d2c9", "text": "#20332d", "muted": "#566b61", "accent": "#315745", "accentink": "#ffffff", "hover": "#e7eee5", "warn": "#765020", "notice": "#e7efe3", "selection": "#d7e5d3"})
        c.update({"housing": "#272d32", "segment": "#41484e", "segmentHover": "#515b63", "segmentChecked": "#59665f", "segmentLine": "#667078"} if self.preferences.get("theme", "dark") != "light" else
                 {"housing": "#d9dedd", "segment": "#f0f2f1", "segmentHover": "#ffffff", "segmentChecked": "#c4d4c7", "segmentLine": "#9aa7a0"})
        c["reading"] = str(round(int(self.preferences.get("text_size", 12)) * 4 / 3))
        self.setStyleSheet("""
          QMainWindow, QDialog, QDockWidget, QWidget { background: %(bg)s; color: %(text)s; }
          QWidget { font-family: 'Segoe UI'; font-size: 13px; }
          QLabel { background: transparent; }
          QLabel[kind="brand"] { font-size: 30px; font-weight: 600; }
          QLabel[kind="speaker"] { font-size: 20px; font-weight: 600; }
          QLabel[kind="preview"] { color: %(warn)s; font-size: 12px; padding: 5px; }
          QLabel[kind="credit"] { color: %(muted)s; font-size: 12px; }
          QLabel[kind="credit"] a { color: %(accent)s; text-decoration: underline; text-decoration-color: %(line)s; }
          QLabel[kind="manual"] { font-size: 13px; line-height: 1.4; }
          QLabel[kind="eyebrow"] { color: %(muted)s; font-size: 10px; font-weight: 600; }
          QLabel[kind="muted"] { color: %(muted)s; font-size: 11px; }
          QLabel[kind="section"] { font-size: 14px; font-weight: 600; padding-top: 6px; }
          QLabel[kind="warning"] { color: %(warn)s; font-size: 11px; }
          QLabel[kind="notice"] { background: %(notice)s; border: 1px solid %(line)s; border-radius: 6px; padding: 10px 12px; }
          QLabel[kind="status"] { font-weight: 600; padding: 3px; }
          QFrame#editorBox { background: %(field)s; border: 1px solid %(line)s; border-radius: 6px; }
          QFrame#settingsSeparator { background: %(line)s; }
          QFrame#speakerPanel { background: %(panel)s; border: 1px solid %(line)s; border-radius: 9px; }
          QLineEdit, QPlainTextEdit, QComboBox, QSpinBox { background: %(field)s; border: 1px solid %(line)s; border-radius: 5px; padding: 8px; selection-background-color: %(selection)s; color: %(text)s; }
          QPlainTextEdit { padding: 12px; }
          QPlainTextEdit#sourceEditor, QPlainTextEdit#receivedEditor { font-size: %(reading)spx; border: none; padding: 4px; background: transparent; }
          QPlainTextEdit#dictationPreview { border: none; color: %(warn)s; background: transparent; padding: 4px; font-size: 12px; }
          QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid %(accent)s; }
          QLineEdit#conversationTitle { font-size: 15px; font-weight: 600; padding: 7px 10px; }
          QComboBox::drop-down { border: none; width: 24px; }
          QComboBox QAbstractItemView { background: %(panel)s; selection-background-color: %(selection)s; color: %(text)s; border: 1px solid %(line)s; }
          QPushButton { background: %(panel)s; border: 1px solid %(line)s; border-radius: 5px; padding: 8px 12px; min-height: 16px; color: %(text)s; }
          QPushButton#settingsClose { padding: 0; border: none; background: transparent; color: %(muted)s; }
          QPushButton#settingsClose:hover { background: %(hover)s; color: %(text)s; }
          QPushButton:hover { background: %(hover)s; border-color: %(accent)s; }
          QPushButton:focus { border: 2px solid %(accent)s; padding: 7px 11px; }
          QPushButton:disabled { color: %(muted)s; border-color: %(line)s; }
          QPushButton[kind="primary"] { background: %(accent)s; border-color: %(accent)s; color: %(accentink)s; font-weight: 600; }
          QPushButton#iconButton { padding: 4px; border: none; background: transparent; }
          QPushButton[kind="record"] { background: %(hover)s; border-color: %(line)s; }
          QPushButton[kind="record"][recording="true"] { background: #843c3c; color: #fff1ed; border-color: #c77a73; }
          QPushButton[kind="fold"] { text-align: left; font-weight: 600; }
          QPushButton:checked { border: 1px solid %(accent)s; background: %(selection)s; }
          QFrame#splitControl { background: %(housing)s; border: 1px solid %(line)s; border-radius: 9px; }
          QLabel[kind="toggleLabel"] { background: transparent; color: %(text)s; border: none; padding: 0px 10px 0px 4px; font-weight: 600; }
          QPushButton#voiceToggle, QPushButton#voiceDisabled { background: %(segment)s; border: 1px solid %(segmentLine)s; padding: 4px 10px; min-height: 16px; color: %(text)s; }
          QPushButton#voiceToggle { border-top-left-radius: 5px; border-bottom-left-radius: 5px; border-top-right-radius: 0; border-bottom-right-radius: 0; }
          QPushButton#voiceDisabled { border-top-left-radius: 0; border-bottom-left-radius: 0; border-top-right-radius: 5px; border-bottom-right-radius: 5px; }
          QPushButton#voiceToggle:hover, QPushButton#voiceDisabled:hover { background: %(segmentHover)s; border-color: %(accent)s; }
          QPushButton#voiceToggle:checked, QPushButton#voiceDisabled:checked { background: %(segmentChecked)s; border-color: %(accent)s; color: %(text)s; }
          QPushButton#voiceToggle:focus, QPushButton#voiceDisabled:focus { border: 2px solid %(accent)s; padding: 3px 9px; }
          QPushButton#voiceToggle:pressed, QPushButton#voiceDisabled:pressed { background: %(selection)s; }
          QPushButton[kind="primary"]:disabled { background: %(hover)s; color: %(muted)s; }
          QTabWidget::pane { border: 1px solid %(line)s; border-radius: 7px; background: %(panel)s; }
          QTabBar::tab { background: transparent; padding: 9px 14px; color: %(muted)s; border-bottom: 2px solid transparent; }
          QTabBar::tab:selected { color: %(text)s; border-bottom-color: %(accent)s; }
          QTabBar::tab:hover { background: %(hover)s; }
          QTableWidget, QListWidget { background: %(panel)s; border: none; selection-background-color: %(selection)s; outline: none; }
          QTableWidget::item, QListWidget::item { padding: 8px; border-bottom: 1px solid %(line)s; }
          QTableWidget::item:selected, QListWidget::item:selected { background: %(selection)s; color: %(text)s; }
          QHeaderView::section { background: %(panel)s; color: %(muted)s; border: none; border-bottom: 1px solid %(line)s; padding: 8px 6px; }
          QScrollBar:vertical { background: %(bg)s; width: 10px; margin: 0; }
          QScrollBar::handle:vertical { background: %(line)s; min-height: 25px; border-radius: 4px; }
          QScrollBar:horizontal { background: %(bg)s; height: 10px; }
          QScrollBar::handle:horizontal { background: %(line)s; min-width: 25px; border-radius: 4px; }
          QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
          QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
          QSplitter::handle { background: transparent; }
          QSplitter::handle:horizontal { width: 14px; }
          QSplitter::handle:vertical { height: 14px; }
          QPushButton[kind="destructive"] { color: %(warn)s; }
          QListWidget::indicator { width: 14px; height: 14px; border: 1px solid %(muted)s; border-radius: 3px; background: %(field)s; }
          QListWidget::indicator:checked { border: 2px solid %(accent)s; background: %(selection)s; }
          QCheckBox { spacing: 8px; background: transparent; }
          QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid %(muted)s; border-radius: 3px; background: %(field)s; }
          QCheckBox::indicator:checked { border: 2px solid %(accent)s; background: %(selection)s; }
          QStatusBar { border-top: 1px solid %(line)s; background: %(bg)s; padding: 5px 12px; }
          QStatusBar::item { border: none; }
          QDockWidget::title { background: %(panel)s; padding: 10px 14px; font-weight: 600; }
          QToolTip { color: %(text)s; background: %(panel)s; border: 1px solid %(line)s; padding: 6px; }
        """ % c)
        font = QFont("Segoe UI", int(self.preferences.get("text_size", 12)))
        for panel in self.panels.values():
            panel.source.setFont(font)
            panel.received.setFont(font)
            panel.setMinimumHeight(max(430, panel.minimumSizeHint().height()))
            ink = c["text"]
            for control, kind in ((panel.source_copy, "copy"), (panel.copy_button, "copy"), (panel.listen_button, "listen")):
                control.setIcon(line_icon(kind, ink))
        self.voice_button.blockSignals(True)
        enabled = bool(self.preferences.get("voice_enabled", self.preferences.get("auto_speak", True)))
        self.voice_button.setChecked(enabled)
        self.voice_disabled_button.setChecked(not enabled)
        self.voice_button.blockSignals(False)
        safe = bool(self.preferences.get('safe_speech', True))
        self.safe_on.setChecked(safe)
        self.safe_off.setChecked(not safe)
        for panel in self.panels.values():
            panel.safe_speech = safe
            if panel.preview_active:
                panel.received.setPlainText(safe_mask(getattr(panel, '_preview_translation', ''), safe))
        for credit, before, linked, after, url in self.credit_links:
            credit.setText(f'<span style="color: {c["muted"]};">{before}</span><a href="{url}" style="color: {c["accent"]}; text-decoration: underline; text-decoration-color: {c["line"]};">{linked}</a><span style="color: {c["muted"]};">{after}</span>')
        self.settings_close_button.setIcon(line_icon("close", c["muted"]))

    def _set_status(self, heading: str, detail: str = "") -> None:
        self.status_heading.setText(heading)
        self.status_detail.setText(detail)

    def _show_error(self, message: str) -> None:
        self.notice.setText(message)
        self.notice.show()
        self._set_status("Needs attention", "Your original text is preserved.")

    def _has_provider(self) -> bool:
        return any(x.get("key") or x.get("configured") for x in self.preferences.get("providers", {}).values())

    def _language_changed(self, _: str = "") -> None:
        if self.loading or not hasattr(self, "draft_timer"):
            return
        self.preferences.update(source1=self.panels["1"].code(), source2=self.panels["2"].code())
        self._refresh_capabilities()
        self._refresh_turns()
        try:
            self.service.save_settings(self.preferences)
        except Exception as exc:
            self._show_error("Language preferences could not be saved: " + str(exc))
        self._draft_changed()

    def _refresh_capabilities(self) -> None:
        for panel in self.panels.values():
            capability = {}
            if hasattr(self.service, "capabilities"):
                try:
                    capability = dict(self.service.capabilities(panel.code()))
                except Exception:
                    pass
            speech_provider = self.preferences.get("speech_provider", "auto")
            keyless = speech_provider in ("auto", "google_web", "offline", "omnilingual")
            fallback_ready = keyless and hasattr(self.service, "recognize")
            enabled = bool(capability.get("mic_enabled", fallback_ready or self.preferences.get("speech_key") or self.preferences.get("speech_configured")))
            speech_configured = bool(self.preferences.get("speech_key") or self.preferences.get("speech_configured"))
            missing_region = speech_configured and speech_provider == "azure" and not self.preferences.get("speech_region")
            if missing_region:
                enabled = False
            panel.record_button.setEnabled(enabled or self.recording_side == panel.number)
            reason = str(capability.get("reason", "Record one turn, then Stop to transcribe. No key is needed." if keyless and enabled else "Record one turn, up to 50 seconds. Stop to transcribe." if enabled else "Dictation is unavailable for this language. You can type this turn."))
            if missing_region:
                reason = "Add your Azure Speech resource region in Settings, or type this turn."
            elif speech_provider in ("azure", "google") and speech_configured and not enabled:
                provider_name = "Azure Speech" if speech_provider == "azure" else "Google Cloud Speech"
                reason = f"{provider_name} does not support this exact recognition locale. Type this turn."
            panel.record_button.setToolTip(reason)
            capture = (panel.received_turn or {}).get("dictation", {})
            panel.capability_note.setText("Recognized with " + provider_label(str(capture.get("provider", ""))) + " · Record Speech starts a new turn." if capture and enabled else reason)
            if panel.received.toPlainText():
                target_code = str((panel.received_turn or {}).get("target_lang", self.panels["2" if panel.number == "1" else "1"].code()))
                voice = capability
                if hasattr(self.service, "capabilities"):
                    try:
                        voice = dict(self.service.capabilities(target_code))
                    except Exception:
                        pass
                panel.listen_button.setEnabled(bool(panel.received_turn) and bool(voice.get("voice_enabled", True)))
                panel.listen_button.setToolTip(str(voice.get("voice_reason", "Read this translation aloud.")))

    def _save_settings(self, settings: dict) -> None:
        settings = dict(settings)
        settings.update(source1=self.panels["1"].code(), source2=self.panels["2"].code())
        selected = settings.get("provider", "auto")
        entry = settings.get("providers", {}).get(selected, {})
        missing_api_key = selected in ("azure", "google", "deepl") and not (entry.get("key") or entry.get("configured"))
        try:
            self.service.save_settings(settings)
            self.preferences = dict(self.service.settings())
            self._apply_theme()
            self._refresh_capabilities()
            self.settings_pane.original = copy.deepcopy(self.preferences)
            self.settings_pane.feedback.setText(f"{provider_label(selected)} selected. Add its optional API key, or choose a free translation service." if missing_api_key else "Changes applied")
            self.notice.hide()
            self._set_status("Settings saved", "Free services ready · Optional credentials protected for this Windows account.")
        except Exception as exc:
            self.settings_pane.feedback.setText("Could not apply: " + str(exc))
            self._show_error("Settings could not be saved: " + str(exc))

    def _check_native_voices(self) -> None:
        if not hasattr(self.service, "check_native_voices"):
            self._show_error("Installed voice discovery is unavailable. Configure a supported Azure Speech voice or continue with text.")
            return
        if len(self.jobs) >= 3:
            self._set_status("Finishing previous tasks", "Wait briefly before checking installed voices.")
            return
        self.settings_pane.check_voices.setEnabled(False)
        self.settings_pane.voice_feedback.setText("Checking installed voices…")
        self.settings_pane.voice_feedback.show()
        self._set_status("Checking Windows voices", "Voice discovery runs independently of your conversation.")
        def ready(value: Any) -> None:
            self.settings_pane.check_voices.setEnabled(True)
            self._refresh_capabilities()
            if isinstance(value, dict) and value.get("error"):
                self.settings_pane.voice_feedback.setText("Unavailable: " + str(value["error"]))
                self._show_error(str(value["error"]))
            else:
                count = len(value.get("voices", [])) if isinstance(value, dict) else len(value) if isinstance(value, (tuple, list)) else 0
                self.settings_pane.voice_feedback.setText(f"Checked · {count} installed voice(s) found." if count else "Checked · no exact-language Windows voice was reported.")
                self._set_status("Windows voices checked", "Only exact-language installed voices are available for playback.")
        def failed(message: str) -> None:
            self.settings_pane.check_voices.setEnabled(True)
            self.settings_pane.voice_feedback.setText("Unavailable: " + message)
        self._run(self.service.check_native_voices, ready, failed)

    def _draft_changed(self) -> None:
        if self.loading or not hasattr(self, "draft_timer"):
            return
        for side, panel in self.panels.items():
            value = panel.source.toPlainText()
            if value != self.draft_snapshots[side]:
                self.draft_versions[side] += 1
                self.draft_snapshots[side] = value
                shown = panel.received_turn
                if shown and value != str(shown.get("reviewed_source", shown.get("raw_source", ""))):
                    panel.show_received(None)
                if self.recording_side == side and panel.preview_active:
                    panel.clear_preview()
        self.unsaved = True
        self.save_label.setText("Saving…")
        self.draft_timer.start()

    def _save(self, refresh_history: bool = True) -> bool:
        self.draft_timer.stop()
        self.conversation.update(title=self.title_edit.text().strip() or "Conversation",
                                 drafts={side: panel.source.toPlainText() for side, panel in self.panels.items()},
                                 source1=self.panels["1"].code(), source2=self.panels["2"].code())
        if not self.conversation.get("revision") and not self.conversation.get("deleted_turn_ids") and not self.conversation.get("turns") and not any(self.conversation["drafts"].values()) and self.conversation["title"] == "Conversation":
            self.unsaved = False
            self.save_label.setText("Saved automatically")
            return True
        try:
            result = self.service.save_conversation(copy.deepcopy(self.conversation))
            if isinstance(result, dict) and result.get("id"):
                self.conversation["id"] = result["id"]
                for key in ("revision", "created_at", "updated_at"):
                    if key in result:
                        self.conversation[key] = result[key]
                saved_turns = {turn["id"]: turn for turn in result.get("turns", [])}
                for turn in self.conversation["turns"]:
                    saved = saved_turns.get(turn["id"], {})
                    for key in ("revision", "seq", "created_at", "updated_at"):
                        if key in saved:
                            turn[key] = saved[key]
                self.conversation.pop("deleted_turn_ids", None)
            self.unsaved = False
            self.save_label.setText("Saved on this PC")
            if refresh_history:
                self._refresh_history()
            return True
        except Exception as exc:
            self.unsaved = True
            self.save_label.setText("Not saved · retry Ctrl+S")
            self._show_error("Conversation could not be saved. Keep this window open and retry: " + str(exc))
            return False

    def _load_last_draft(self) -> None:
        try:
            entries = self.service.list_conversations()
            if entries and self.preferences.get("restore_last", True):
                value = self.service.load_conversation(entries[0]["id"])
                if value:
                    self._load_conversation(value)
        except Exception as exc:
            self._show_error("Saved conversations could not be read: " + str(exc))

    def _load_conversation(self, value: dict) -> None:
        self.cancel_jobs()
        self._stop_voice()
        self.loading = True
        self.conversation = copy.deepcopy(value)
        self.conversation.setdefault("turns", [])
        self.title_edit.setText(str(value.get("title", "Conversation")))
        for side, panel in self.panels.items():
            panel.language.setEnabled(not self.translation_token and not self.recording_token)
            panel.set_code(str(value.get("source" + side, self.preferences.get("source" + side, "en" if side == "1" else "fr"))))
            panel.source.setPlainText(str(value.get("drafts", {}).get(side, "")))
        self.loading = False
        self.unsaved = False
        self.undo_snapshot = None
        self.undo_button.hide()
        self.save_label.setText("Saved on this PC")
        self._refresh_turns()
        self._refresh_capabilities()
        self._set_status("Conversation opened", "All originals and reviewed sources are preserved.")

    def new_conversation(self) -> None:
        self.cancel_jobs()
        if not self._save():
            return
        self._load_conversation(self._empty_conversation())
        self.lower_tabs.setCurrentIndex(0)
        self.panels["1"].source.setFocus()
        self._set_status("New conversation", "Type in either speaker’s panel.")

    def _run(self, operation: Callable[[], Any], success: Callable[[Any], None], failure: Callable[[str], None] | None = None,
             event: threading.Event | None = None) -> str:
        token = uuid.uuid4().hex
        worker = Worker(operation)
        self.jobs[token] = (worker, event or threading.Event())
        worker.signals.result.connect(lambda result, t=token: self._deliver_callback(t, success, result, failure), Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(lambda message, t=token: self._deliver_callback(t, failure or self._show_error, message), Qt.ConnectionType.QueuedConnection)
        worker.signals.finished.connect(lambda t=token: self._job_finished(t), Qt.ConnectionType.QueuedConnection)
        self.pool.start(worker)
        return token

    def _deliver_callback(self, token: str, callback: Callable, value: Any, failure: Callable | None = None) -> None:
        if token not in self.jobs or token in self.cancelled_tokens or self.closed:
            return
        try:
            callback(value)
        except Exception as exc:
            message = "The result could not be completed safely: " + (str(exc) or type(exc).__name__)
            if failure is not None:
                try:
                    failure(message)
                    return
                except Exception as nested:
                    message += " · " + (str(nested) or type(nested).__name__)
            self._show_error(message)

    def _job_finished(self, token: str) -> None:
        self.jobs.pop(token, None)
        self.cancelled_tokens.discard(token)
        if self.translation_token == token:
            self.translation_token = None
        if self.recording_token == token:
            self.recording_timer.stop()
            self.recording_phase = None
            self.recording_token = self.recording_side = None
            self._stop_preview()
            QTimer.singleShot(0, self._commit_final_translation)
        if self.preview_token == token:
            self.preview_token = None
            QTimer.singleShot(0, self._launch_pending_preview)
        if self.voice_token == token:
            self.voice_token = None
            if self.voice_event is not None: self.voice_event.set()
            self.voice_event = None
            self.stop_voice_button.setEnabled(False)
        if not self.closed:
            self._update_busy()

    def _update_busy(self) -> None:
        self.cancel_button.setVisible(bool(self.translation_token or self.recording_token))
        for side, panel in self.panels.items():
            panel.language.setEnabled(not self.translation_token and not self.recording_token)
            panel.translate_button.setEnabled(not self.translation_token and not self.recording_token)
            panel.translate_button.setText("Translating…" if self.translation_token and side == getattr(self, "translating_side", "") else "Translate →")
            recording_here = side == self.recording_side
            panel.set_recording(self.recording_phase if recording_here else None)
            panel.record_button.setAccessibleName(f"Stop recording speaker {side}" if recording_here else f"Record speaker {side}")
            if self.recording_token:
                panel.record_button.setEnabled(recording_here and self.recording_phase != "transcribing")
                panel.listen_button.setEnabled(False)
        if not self.recording_token:
            self._refresh_capabilities()

    def translate_focused(self) -> None:
        focused = QApplication.focusWidget()
        side = "2" if focused and (focused is self.panels["2"].source or self.panels["2"].isAncestorOf(focused)) else "1"
        self.translate_side(side)

    def translate_side(self, side: str) -> None:
        if len(self.jobs) >= 3:
            self._set_status("Finishing previous tasks", "Wait briefly while cancelled services finish their current request.")
            return
        if self.translation_token or self.recording_token:
            self._set_status("A task is active", "Finish or cancel the current task first.")
            return
        panel = self.panels[side]
        source = panel.source.toPlainText()
        if not source.strip():
            panel.source.setFocus()
            self._set_status("Enter some text", "Type or record a turn before translating.")
            return
        if len(source) > 20000:
            self._show_error("This turn is over 20,000 characters. Divide it into smaller turns; your full draft is saved.")
            return
        target = "2" if side == "1" else "1"
        turn = {"id": uuid.uuid4().hex, "speaker": side,
                "source_lang": panel.code(), "target_lang": self.panels[target].code(),
                "raw_source": source, "reviewed_source": source, "translated_text": "",
                "provider": "", "warnings": [], "created_at": now(), "status": "pending", "ui_generation": 1}
        self.conversation["turns"].append(turn)
        if self.conversation["title"] == "Conversation" and self.title_edit.text() == "Conversation":
            preview = source.strip().splitlines()[0]
            self.title_edit.setText(preview[:65] + ("…" if len(preview) > 65 else ""))
        if not self._save():
            turn.update(status="failed", warnings=["Save failed. Translation did not start; retry saving first."])
            self._refresh_turns()
            return
        self._refresh_turns()
        capture = getattr(self, "pending_dictation", None)
        if capture and capture["side"] == side and capture["text"] == source:
            turn["dictation"] = copy.deepcopy(capture["capture"])
            self.pending_dictation = None
        self._translate_turn(turn, source, clear_draft=False)

    def _translate_turn(self, turn: dict, source: str, clear_draft: bool = False) -> None:
        self._stop_voice()
        conversation_id, turn_id, generation = self.conversation["id"], turn["id"], int(turn.get("ui_generation", 1))
        side = str(turn["speaker"])
        panel, target_side = self.panels[side], "2" if side == "1" else "1"
        event = threading.Event()
        self.translating_side = side
        self.notice.hide()
        self._set_status("Translating", "Original preserved. You can keep writing while this turn is translated.")
        provider = str(self.preferences.get("provider", "auto"))
        reinforce = bool(self.preferences.get("reinforce", True))
        context = str(self.preferences.get("context", "")) if provider == "deepl" else ""

        def current_turn() -> dict | None:
            if self.conversation["id"] != conversation_id:
                return None
            return next((x for x in self.conversation["turns"] if x["id"] == turn_id and int(x.get("ui_generation", 1)) == generation), None)

        def success(value: Any) -> None:
            current = current_turn()
            if event.is_set() or current is None:
                return
            result = dict(value) if isinstance(value, dict) else {"text": str(value)}
            text = str(result.get("text", ""))
            if not text.strip():
                failure("The service returned an empty translation. The turn is preserved for retry.")
                return
            current.update(translated_text=text, provider=str(result.get("provider", provider)),
                           warnings=[str(x) for x in result.get("warnings", [])], status="complete", elapsed_ms=result.get("elapsed_ms", 0))
            for key in ("review_text", "review_provider", "backtranslation", "backtranslation_provider", "trace", "checks"):
                if key in result:
                    current[key] = result[key]
            # dataclasses.asdict preserves engine tuples. The UI appends capture
            # notes, so normalize this sequence before extending it.
            current["checks"] = list(current.get("checks") or [])
            capture = current.get("dictation", {})
            capture_notes = [str(x) for x in capture.get("warnings", [])]
            for message in capture_notes:
                if message not in current["warnings"]:
                    current["warnings"].append(message)
                    current.setdefault("checks", []).append({"code": "dictation_advisory", "message": message})
            capture_notes = []
            if capture and (not capture.get("complete", True) or capture.get("limit_reached")):
                capture_notes.append("Dictation may be incomplete. Review the recognized words before relying on this turn.")
            for message in capture_notes:
                if message not in current["warnings"]:
                    current["warnings"].append(message)
                    current.setdefault("checks", []).append({"code": "dictation_review", "message": message})
            self._refresh_turns(select_id=turn_id)
            self.speaker_scroll.ensureWidgetVisible(panel.received, 0, 18)
            saved = self._save()
            warnings = review_messages(current)
            elapsed = float(current.get("elapsed_ms") or 0) / 1000
            comparison = f" · Second opinion: {provider_label(current.get('review_provider', ''))} · Review turn to compare" if current.get("review_text") else " · Original preserved"
            self._set_status("Review suggested" if warnings else "Translation ready", f"{provider_label(current['provider'])} · {elapsed:.1f}s" + (f" · {len(warnings)} check(s) need review" if warnings else comparison))
            if warnings:
                self.notice.setText("Review before use: " + " · ".join(warnings))
                self.notice.show()
            if not saved:
                self._set_status("Translated · save needs attention", "Retry Ctrl+S. Keep this window open until saving succeeds.")
            if self.preferences.get("voice_enabled", self.preferences.get("auto_speak", True)) and not review_messages(current, playback=True) and saved and self.panels[target_side].code() == current["target_lang"]:
                self.listen_side(side)

        def failure(message: str) -> None:
            current = current_turn()
            if current is None or event.is_set():
                return
            for key in ("translated_text", "provider", "review_text", "review_provider", "backtranslation", "backtranslation_provider"):
                current[key] = ""
            current["checks"] = []
            current["trace"] = []
            current.update(status="failed", error=message, warnings=[message])
            self._refresh_turns(select_id=turn_id)
            self._save()
            self._show_error(message)

        self.translation_token = self._run(lambda: self.service.translate(source, turn["source_lang"], turn["target_lang"], provider=provider,
                                              reinforce=reinforce, cancel_event=event, context=context), success, failure, event)
        self._update_busy()

    def cancel_jobs(self) -> None:
        self.pending_final_translation = None
        self._stop_preview()
        self.recording_timer.stop()
        self.recording_phase = None
        active = bool(self.translation_token or self.recording_token)
        for token in (self.translation_token, self.recording_token):
            if token and token in self.jobs:
                event = self.jobs[token][1]
                abort = getattr(event, "abort_event", None)
                if abort is not None:
                    abort.set()
                event.set()
                self.cancelled_tokens.add(token)
        if self.translation_token:
            for turn in self.conversation.get("turns", []):
                if turn.get("status") == "pending":
                    turn.update(status="cancelled", warnings=["Translation cancelled. Original preserved; review this turn to retry."])
            self._save()
            self._refresh_turns()
        self.translation_token = self.recording_token = self.recording_side = None
        self._update_busy()
        if active:
            self._set_status("Task cancelled", "Late results will not replace this conversation.")

    def _stop_preview(self) -> None:
        self.preview_generation += 1
        if self.preview_token and self.preview_token in self.jobs:
            self.jobs[self.preview_token][1].set()
            self.cancelled_tokens.add(self.preview_token)
        self.pending_preview = None
        self.record_context = None
        for panel in self.panels.values():
            panel.clear_preview()

    def _recording_preview(self, payload: Any) -> None:
        recording_id, value = payload
        context = self.record_context
        if not context or recording_id != context["id"] or context["event"].is_set() or self.closed:
            return
        side = context["side"]
        panel = self.panels[side]
        if self.conversation["id"] != context["conversation"] or panel.code() != context["source"] or self.draft_versions[side] != context["draft_version"]:
            return
        if not isinstance(value, dict):
            return
        result = dict(value)
        if result.get("complete") is True:
            return
        text = str(result.get("text", "")).strip()
        try:
            sequence = int(result.get("sequence", context.get("sequence", 0) + 1))
        except (TypeError, ValueError):
            return
        if not text or sequence <= context.get("sequence", 0):
            return
        context["sequence"] = sequence
        panel.show_preview(text)
        self._set_status("Recording · live preview", "Provisional words are not saved or spoken. Stop Recording commits the final turn.")
        if not hasattr(self.service, "translate_preview"):
            return
        self.preview_generation += 1
        generation = self.preview_generation
        self.pending_preview = (recording_id, dict(context), text, generation)
        if self.preview_token and self.preview_token in self.jobs:
            self.jobs[self.preview_token][1].set()
            self.cancelled_tokens.add(self.preview_token)
            return
        self._launch_pending_preview()

    def _launch_pending_preview(self) -> None:
        pending = getattr(self, "pending_preview", None)
        self.pending_preview = None
        if not pending or not self.record_context or self.record_context["event"].is_set() or self.closed:
            return
        recording_id, context, text, generation = pending
        if context["id"] != self.record_context["id"] or self.draft_versions[context["side"]] != context["draft_version"]:
            return
        side = context["side"]
        panel = self.panels[side]
        event = threading.Event()
        def ready(value: Any) -> None:
            current = self.record_context
            if event.is_set() or generation != self.preview_generation or not current or current["id"] != recording_id or current["event"].is_set() or self.draft_versions[side] != current["draft_version"]:
                return
            translated = str(dict(value).get("text", ""))
            if translated.strip():
                direction(panel.received, bool(self.language_by_code.get(context["target"], {}).get("rtl")))
                panel.show_preview(text, translated)
        self.preview_token = self._run(lambda: self.service.translate_preview(text, context["source"], context["target"], event), ready,
                                       lambda _: None, event=event)

    def record_side(self, side: str) -> None:
        if self.recording_token:
            if self.recording_side == side and self.recording_token in self.jobs and self.recording_phase == "recording":
                self.jobs[self.recording_token][1].set()
                self.recording_phase = "transcribing"
                self.recording_timer.stop()
                self._stop_preview()
                self._refresh_turns()
                self._update_busy()
                self._set_status("Transcribing", "Final recognition uses the completed recording. Your original is preserved.")
            return
        if len(self.jobs) >= 3:
            self._set_status("Finishing previous tasks", "Wait briefly before starting another recording.")
            return
        if self.translation_token:
            self._set_status("Translation is active", "Finish or cancel the translation before recording.")
            return
        if not hasattr(self.service, "recognize"):
            self._show_error("Speech recognition is unavailable. You can type this turn.")
            return
        self._stop_voice()
        panel, code, conversation_id = self.panels[side], self.panels[side].code(), self.conversation["id"]
        old_source = panel.source.toPlainText()
        completed_source = str((panel.received_turn or {}).get("reviewed_source", ""))
        replace_completed = bool(panel.received_turn and old_source == completed_source)
        event = threading.Event()
        event.abort_event = threading.Event()
        recording_id = uuid.uuid4().hex
        self.record_context = {"id": recording_id, "side": side, "source": code,
                               "target": self.panels["2" if side == "1" else "1"].code(),
                               "conversation": conversation_id, "event": event,
                               "draft_version": self.draft_versions[side], "sequence": 0}
        self.recording_side = side
        self.recording_phase = "recording"
        self.recording_started = time.monotonic()
        self.notice.hide()
        self._set_status("Recording", "Speak one turn. Stop Recording translates the final words. Maximum 50 seconds.")

        def success(value: Any) -> None:
            if self.conversation["id"] != conversation_id or event.abort_event.is_set():
                return
            self._stop_preview()
            result = dict(value) if isinstance(value, dict) else {"text": str(value)}
            text = str(result.get("text", "")).strip()
            if not text:
                self._refresh_turns()
                self._show_error("No speech was recognized. Check the microphone and selected language, then retry.")
                return
            draft = panel.source.toPlainText()
            retained = "" if replace_completed and draft == old_source else draft
            merged = retained + ("\n" if retained else "") + text
            panel.source.setPlainText(merged)
            capture = {key: result[key] for key in ("provider", "warnings", "trace", "complete", "duration_ms", "limit_reached") if key in result}
            self.conversation.setdefault("metadata", {}).setdefault("last_dictation", {})[side] = capture
            self.pending_dictation = {"side": side, "text": merged, "capture": capture}
            if not self._save():
                return
            panel.source.setFocus()
            self.pending_final_translation = {"recording": recording_id, "conversation": conversation_id, "side": side, "text": merged,
                                              "draft_version": self.draft_versions[side]}
            attribution = provider_label(str(result.get("provider", "")))
            self._set_status("Final words ready", (attribution + " · " if attribution else "") + "Starting final translation…")
            if result.get("warnings"):
                self.notice.setText("Dictation: " + " · ".join(str(x) for x in result["warnings"]))
                self.notice.show()

        def failed(message: str) -> None:
            self._stop_preview()
            self._refresh_turns()
            self._show_error("Dictation could not finish: " + message)

        def recognize() -> Any:
            # Legacy facades are supported without swallowing service exceptions.
            import inspect
            signature = inspect.signature(self.service.recognize)
            if "preview_callback" in signature.parameters or any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
                return self.service.recognize(code, event, preview_callback=lambda value: self.preview_signals.preview.emit((recording_id, value)))
            return self.service.recognize(code, event)

        self.recording_token = self._run(recognize, success, failed, event=event)
        self._update_busy()
        self.recording_timer.start()

    def _commit_final_translation(self) -> None:
        final = getattr(self, "pending_final_translation", None)
        self.pending_final_translation = None
        if not final or self.closed or self.conversation["id"] != final["conversation"]:
            return
        side = final["side"]
        if self.draft_versions[side] == final["draft_version"] and self.panels[side].source.toPlainText() == final["text"]:
            self.translate_side(side)

    def _recording_tick(self) -> None:
        if self.recording_phase != "recording" or not self.recording_side:
            self.recording_timer.stop()
            return
        elapsed = int(time.monotonic() - self.recording_started)
        self._set_status(f"Recording · {elapsed:02d}s", "Stop Recording commits the final turn. Escape discards it.")
        if elapsed >= 50:
            self.recording_phase = "transcribing"
            self.recording_timer.stop()
            self._stop_preview()
            self._refresh_turns()
            self._update_busy()
            self._set_status("Transcribing", "Recording limit reached. Recognizing the completed turn.")

    def listen_side(self, side: str) -> None:
        panel, turn = self.panels[side], self.panels[side].received_turn
        if not turn or not panel.received.toPlainText().strip():
            return
        if review_messages(turn, playback=True):
            answer = QMessageBox.question(self, "Review before playback", "This translation has checks that need review. Read the turn before playing it aloud.\n\nPlay it now?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        if not hasattr(self.service, "speak"):
            self._show_error("No voice service is available for this language.")
            return
        self._stop_voice()
        event = threading.Event()
        self.stop_voice_button.setEnabled(True)
        self.voice_event = event
        self._set_status("Preparing voice", "Stop voice or Esc cancels preparation and playback.")
        text, code = panel.received.toPlainText(), str(turn["target_lang"])
        def speak():
            if hasattr(self.service, 'speak_with_feedback'):
                return self.service.speak_with_feedback(text, code, event,
                    lambda value: self.voice_signals.preview.emit({'event':event,'value':value}))
            return self.service.speak(text, code, event)
        self.voice_token = self._run(speak,
                                     lambda result: self._set_status("Playback complete", " · ".join(result.get("warnings", [])) or "Translation and original remain available."), event=event)

    def _voice_prepared(self, payload) -> None:
        if self.closed or payload['event'] is not self.voice_event or payload['event'].is_set():
            return
        value=payload['value']
        self._set_status("Speaking", " · ".join(value.get('warnings',[])) or str(value.get('voice') or 'Stop voice or Esc ends playback.'))

    def _stop_voice(self) -> None:
        if self.voice_event is not None: self.voice_event.set()
        self.voice_event = None
        if self.voice_token and self.voice_token in self.jobs:
            self.jobs[self.voice_token][1].set()
            self.cancelled_tokens.add(self.voice_token)
        self.voice_token = None
        self.stop_voice_button.setEnabled(False)
        if hasattr(self.service, "stop_audio"):
            try:
                self.service.stop_audio()
            except Exception:
                pass

    def stop_everything(self) -> None:
        self.cancel_jobs()
        self._stop_voice()

    def _refresh_turns(self, select_id: str | None = None) -> None:
        turns = self.conversation.get("turns", [])
        old = self._selected_turn()
        selected = select_id or (old or {}).get("id")
        self.turn_table.setRowCount(len(turns))
        for row, turn in enumerate(turns):
            stamp = str(turn.get("created_at", ""))
            try:
                stamp = dt.datetime.fromisoformat(stamp).astimezone().strftime("%H:%M")
            except ValueError:
                stamp = ""
            state, warnings = str(turn.get("status", "complete")), review_messages(turn)
            review = "Pending…" if state == "pending" else (state.capitalize() if state != "complete" else (f"{len(warnings)} check(s)" if warnings else "Review available" if turn.get("review_text") or turn.get("extra_opinions") else "Ready"))
            values = [stamp, str(turn.get("speaker", "")), str(turn.get("raw_source", "")), safe_mask(str(turn.get("translated_text", "")), self.preferences.get("safe_speech", True)), review]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value.replace("\n", " "))
                item.setData(Qt.ItemDataRole.UserRole, turn["id"])
                item.setToolTip(value)
                self.turn_table.setItem(row, column, item)
            if turn["id"] == selected:
                self.turn_table.selectRow(row)
        self.lower_tabs.setTabText(0, f"Conversation · {len(turns)} turn{'s' if len(turns) != 1 else ''}")
        self.export_button.setEnabled(bool(turns or any(self.conversation.get("drafts", {}).values())))
        for side, panel in self.panels.items():
            target_code = self.panels["2" if side == "1" else "1"].code()
            latest = next((x for x in reversed(turns) if str(x.get("speaker")) == side and x.get("source_lang") == panel.code() and x.get("target_lang") == target_code), None)
            if self.recording_side == side and panel.preview_active:
                continue
            source_matches = latest and panel.source.toPlainText() == str(latest.get("reviewed_source", latest.get("raw_source", "")))
            panel.show_received(latest if source_matches and latest.get("translated_text") else None)
        self._refresh_capabilities()
        for value in (self.review_button, self.copy_turn_button, self.delete_turn_button, self.clear_button):
            value.setEnabled(bool(turns))

    def _selected_turn(self) -> dict | None:
        row = self.turn_table.currentRow()
        if row < 0 or self.turn_table.item(row, 0) is None:
            return None
        identity = self.turn_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((x for x in self.conversation.get("turns", []) if x["id"] == identity), None)

    def review_side(self, side: str) -> None:
        turn = self.panels[side].received_turn
        if turn:
            self._refresh_turns(select_id=turn["id"])
            self.review_selected_turn()

    def review_selected_turn(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            return
        if self.translation_token or self.recording_token:
            self._set_status("A task is active", "Finish or cancel the task before reviewing another turn.")
            return
        dialog = TurnDialog(turn, self, self.language_by_code)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = dialog.reviewed.toPlainText()
        if not text.strip() or len(text) > 20000:
            self._show_error("The reviewed source must contain 1–20,000 characters. The existing turn was preserved.")
            return
        previous_source = str(turn.get("reviewed_source", turn.get("raw_source", "")))
        panel = self.panels[str(turn["speaker"])]
        if panel.source.toPlainText() == previous_source:
            panel.source.setPlainText(text)
        turn.update(reviewed_source=text, ui_generation=int(turn.get("ui_generation", 1)) + 1, status="pending")
        # Older output belongs to the previous reviewed source. It remains in
        # stored revisions, but must not appear as the result of the new source.
        for key in ("translated_text", "provider", "review_text", "review_provider", "backtranslation", "backtranslation_provider", "error"):
            turn[key] = ""
            turn.get("metadata", {}).pop(key, None)
        for key in ("warnings", "trace", "checks", "extra_opinions"):
            turn[key] = []
            turn.get("metadata", {}).pop(key, None)
        if not self._save():
            turn.update(status="failed", warnings=["Save failed. Retranslation did not start; retry saving first."])
            self._refresh_turns()
            return
        self._refresh_turns(select_id=turn["id"])
        self._translate_turn(turn, text)

    def copy_selected_turn(self) -> None:
        turn = self._selected_turn()
        if turn:
            text = str(turn.get("raw_source", ""))
            if turn.get("reviewed_source") != turn.get("raw_source"):
                text += "\n\nReviewed source:\n" + str(turn.get("reviewed_source", ""))
            QApplication.clipboard().setText(text + "\n\n" + safe_mask(str(turn.get("translated_text", "")), self.preferences.get("safe_speech", True)))
            self._set_status("Turn copied", "Original and translation copied to the clipboard.")

    def remove_selected_turn(self) -> None:
        turn = self._selected_turn()
        if turn is None:
            return
        if turn.get("status") == "pending":
            self.cancel_jobs()
        self.undo_snapshot = copy.deepcopy(self.conversation)
        self.conversation["turns"] = [x for x in self.conversation["turns"] if x["id"] != turn["id"]]
        self.conversation["deleted_turn_ids"] = [turn["id"]]
        self.undo_button.show()
        self._save()
        self._refresh_turns()
        self._set_status("Turn removed", "Undo removal restores it.")

    def clear_turns(self) -> None:
        if not self.conversation.get("turns"):
            return
        result = QMessageBox.question(self, "Clear conversation turns", "Clear all turns from this conversation? Your drafts stay available. Undo removal restores these turns until you change conversations.", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if result != QMessageBox.StandardButton.Yes:
            return
        self.cancel_jobs()
        self.undo_snapshot = copy.deepcopy(self.conversation)
        self.conversation["deleted_turn_ids"] = [x["id"] for x in self.conversation["turns"]]
        self.conversation["turns"] = []
        self.undo_button.show()
        self._save()
        self._refresh_turns()
        self._set_status("Conversation cleared", "Undo removal restores the previous turns.")

    def undo_removal(self) -> None:
        if not self.undo_snapshot:
            return
        self.cancel_jobs()
        current_ids = {turn["id"] for turn in self.conversation["turns"]}
        for removed in self.undo_snapshot.get("turns", []):
            if removed["id"] not in current_ids:
                restored = copy.deepcopy(removed)
                # Conversation revision guards the restore; the tombstone has a
                # newer persisted turn revision than the pre-removal snapshot.
                restored.pop("revision", None)
                self.conversation["turns"].append(restored)
        self.conversation["turns"].sort(key=lambda turn: int(turn.get("seq", 0)))
        self.undo_snapshot = None
        self.conversation.pop("deleted_turn_ids", None)
        self.undo_button.hide()
        self._save()
        self._refresh_turns()
        self._set_status("Turns restored", "Your current drafts were preserved.")

    def _refresh_history(self) -> None:
        try:
            entries = self.service.list_conversations()
        except Exception as exc:
            self._show_error("Saved history could not be read: " + str(exc))
            return
        current = self.history_list.currentItem()
        selected_id = current.data(Qt.ItemDataRole.UserRole) if current else None
        checked = {item.data(Qt.ItemDataRole.UserRole) for item in self._checked_history_items()}
        self.history_list.blockSignals(True)
        self.history_list.clear()
        for entry in entries:
            title, stamp = str(entry.get("title", "Conversation")), str(entry.get("updated_at", entry.get("created_at", "")))
            try:
                stamp = dt.datetime.fromisoformat(stamp).astimezone().strftime("%d %b %Y · %H:%M")
            except ValueError:
                stamp = ""
            count = entry.get("turn_count", len(entry.get("turns", [])))
            item = QListWidgetItem(f"{title}\n{stamp}  ·  {count} turns")
            item.setData(Qt.ItemDataRole.UserRole, entry["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, title)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if entry["id"] in checked else Qt.CheckState.Unchecked)
            item.setSizeHint(QSize(200, 57))
            self.history_list.addItem(item)
            if entry["id"] == selected_id:
                self.history_list.setCurrentItem(item)
        self.history_list.blockSignals(False)
        self._history_check_changed()
        self._filter_history(self.history_search.text())

    def _checked_history_items(self) -> list:
        return [self.history_list.item(i) for i in range(self.history_list.count())
                if self.history_list.item(i).checkState() == Qt.CheckState.Checked]

    def _history_check_changed(self, *_: Any) -> None:
        count = len(self._checked_history_items())
        self.delete_history_button.setEnabled(bool(count))
        self.delete_history_button.setText(f"Delete selected ({count})" if count else "Delete selected")

    def _filter_history(self, query: str) -> None:
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            item.setHidden(query.casefold() not in item.text().casefold())

    def open_history(self) -> None:
        item = self.history_list.currentItem()
        if item is None:
            return
        identity = item.data(Qt.ItemDataRole.UserRole)
        if not self._save():
            return
        try:
            value = self.service.load_conversation(identity)
            if not value:
                raise ValueError("This conversation is no longer available.")
            self._load_conversation(value)
            self.lower_tabs.setCurrentIndex(0)
        except Exception as exc:
            self._show_error("Conversation could not be opened: " + str(exc))

    def rename_history(self) -> None:
        item = self.history_list.currentItem()
        if item is None:
            return
        identity = item.data(Qt.ItemDataRole.UserRole)
        title, accepted = QInputDialog.getText(self, "Rename conversation", "Conversation title", QLineEdit.EchoMode.Normal, str(item.data(Qt.ItemDataRole.UserRole + 1)))
        if not accepted or not title.strip():
            return
        try:
            if identity == self.conversation["id"]:
                self.title_edit.setText(title.strip()[:160])
                self._save()
            else:
                value = self.service.load_conversation(identity)
                value["title"] = title.strip()[:160]
                self.service.save_conversation(value)
            self._refresh_history()
        except Exception as exc:
            self._show_error("Conversation could not be renamed: " + str(exc))

    def delete_history(self) -> None:
        items = self._checked_history_items()
        if not items:
            return
        identities = [item.data(Qt.ItemDataRole.UserRole) for item in items]
        hidden = sum(item.isHidden() for item in items)
        detail = f"Delete {len(identities)} checked session(s)?"
        if hidden:
            detail += f" Includes {hidden} hidden by the search filter."
        detail += "\nExisting backups and exports are kept."
        answer = QMessageBox.question(self, "Delete selected sessions", detail, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            current_deleted = self.conversation["id"] in identities
            if current_deleted:
                self.cancel_jobs()
                self._stop_voice()
                self.draft_timer.stop()
            self.service.delete_conversations(identities)
            if current_deleted:
                self._load_conversation(self._empty_conversation())
            self._refresh_history()
            self._set_status("Sessions deleted", f"Removed {len(identities)} checked sessions.")
        except Exception as exc:
            self._show_error("Selected sessions could not be deleted: " + str(exc))

    def shred_history(self) -> None:
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Shred all history")
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setText("Purge every saved session and the current session?")
        confirm.setInformativeText("Deletes drafts, originals, translations, stored revisions and the app's automatic backups. There is no Undo.\n\nSeparate exports/backups and other app copies remain. SSDs and system backups prevent a guarantee of forensic erasure. Settings are kept.")
        confirm.addButton(QMessageBox.StandardButton.Cancel)
        shred = confirm.addButton("Shred History", QMessageBox.ButtonRole.DestructiveRole)
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        confirm.setEscapeButton(QMessageBox.StandardButton.Cancel)
        confirm.exec()
        if confirm.clickedButton() != shred:
            return
        self.cancel_jobs()
        self._stop_voice()
        self.draft_timer.stop()
        # Discard callbacks from reviews/previews as well as the main translation.
        for token, (_, event) in self.jobs.items():
            event.set()
            self.cancelled_tokens.add(token)
        try:
            result = self.service.shred_history()
        except Exception as exc:
            self._show_error("History purge could not complete: " + str(exc))
            return
        self._load_conversation(self._empty_conversation())
        self.history_search.clear()
        self._refresh_history()
        if result.get("issues"):
            self._show_error("History deleted; purge needs attention: " + " ".join(result["issues"]))
        else:
            self._set_status("History shredded", "Sessions and automatic backups purged. Separate exports and backups are unaffected.")

    def export_conversation(self) -> None:
        if not self._save():
            return
        formats = {"Word document (*.docx)": "docx", "Text document (*.txt)": "txt", "JSON archive (*.json)": "json", "CSV table (*.csv)": "csv"}
        title = str(self.conversation.get("title", "Conversation"))
        filename = "".join(x for x in title if x not in '<>:"/\\|?*')[:70].strip(" .") or "Conversation"
        path, selected = QFileDialog.getSaveFileName(self, "Export conversation", filename + ".docx", ";;".join(formats))
        if not path:
            return
        format_name = formats.get(selected, "txt")
        for extension in (".docx", ".txt", ".json", ".csv"):
            if path.lower().endswith(extension) and extension != "." + format_name:
                path = path[:-len(extension)]
                break
        if not path.lower().endswith("." + format_name):
            path += "." + format_name
        snapshot = copy.deepcopy(self.conversation)
        self._run(lambda: self.service.export_conversation(snapshot, path, format_name), lambda _: self._set_status("Export complete", path))

    def backup_history(self) -> None:
        if not self._save():
            return
        if not hasattr(self.service, "backup_history"):
            self._show_error("History backup is unavailable. Export individual conversations to JSON instead.")
            return
        filename = "Gray-Feather-history-" + dt.date.today().isoformat() + ".sqlite3"
        path, _ = QFileDialog.getSaveFileName(self, "Back up all saved conversations", filename, "SQLite history archive (*.sqlite3)")
        if not path:
            return
        if not path.lower().endswith(".sqlite3"):
            path += ".sqlite3"
        self._run(lambda: self.service.backup_history(path), lambda _: self._set_status("History backed up", path))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.settings_pane.debounce.isActive():
            self.settings_pane._save()
        self.stop_everything()
        if not self._save():
            answer = QMessageBox.question(self, "Unsaved conversation", "Saving failed. Closing now discards changes since the last successful save.\n\nClose anyway?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.closed = True
        event.accept()

