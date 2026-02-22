from PIL import ImageQt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QStackedWidget
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal

class PreviewPanel(QWidget):
    paste_requested = pyqtSignal(dict)
    plain_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PreviewPanel")
        self._item = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 28, 24, 24)
        lay.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        self._type_badge = QLabel()
        self._type_badge.setFixedHeight(20)
        self._type_badge.setObjectName("preview_badge")
        hdr.addWidget(self._type_badge)

        self._ts_lbl = QLabel()
        self._ts_lbl.setObjectName("preview_ts")
        hdr.addWidget(self._ts_lbl)
        hdr.addStretch()
        lay.addLayout(hdr)

        lay.addSpacing(18)

        # Big preview area
        self._preview_stack = QStackedWidget()
        self._preview_stack.setObjectName("preview_stack")

        # Text page
        self._text_scroll = QScrollArea()
        self._text_scroll.setObjectName("preview_text_scroll")
        self._text_scroll.setWidgetResizable(True)
        self._text_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._text_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        text_inner = QWidget()
        text_inner.setObjectName("preview_text_inner")
        ti_lay = QVBoxLayout(text_inner)
        ti_lay.setContentsMargins(0, 0, 0, 0)
        self._text_lbl = QLabel()
        self._text_lbl.setObjectName("preview_text_lbl")
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._text_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ti_lay.addWidget(self._text_lbl)
        ti_lay.addStretch()
        self._text_scroll.setWidget(text_inner)
        self._preview_stack.addWidget(self._text_scroll)  # index 0

        # Image page
        self._img_scroll = QScrollArea()
        self._img_scroll.setObjectName("preview_img_scroll")
        self._img_scroll.setWidgetResizable(True)
        self._img_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._img_lbl = QLabel()
        self._img_lbl.setObjectName("preview_img_lbl")
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_scroll.setWidget(self._img_lbl)
        self._preview_stack.addWidget(self._img_scroll)   # index 1

        # Empty page
        empty_w = QWidget()
        empty_w.setObjectName("preview_empty_pg")
        el = QVBoxLayout(empty_w)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint = QLabel("Select a card\nto preview it here")
        self._empty_hint.setObjectName("preview_empty_hint")
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self._empty_hint)
        self._preview_stack.addWidget(empty_w)            # index 2

        self._preview_stack.setCurrentIndex(2)
        lay.addWidget(self._preview_stack, stretch=1)

        lay.addSpacing(20)

        # Meta info row
        self._meta_lbl = QLabel()
        self._meta_lbl.setObjectName("preview_meta")
        self._meta_lbl.setWordWrap(True)
        lay.addWidget(self._meta_lbl)

        lay.addSpacing(16)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setObjectName("preview_div")
        lay.addWidget(div)

        lay.addSpacing(16)

        # Action buttons
        self._paste_btn = QPushButton("⏎  Paste this item")
        self._paste_btn.setObjectName("preview_paste_btn")
        self._paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._paste_btn.setFixedHeight(44)
        self._paste_btn.clicked.connect(self._on_paste)
        lay.addWidget(self._paste_btn)

        lay.addSpacing(8)

        self._plain_btn = QPushButton("Paste as plain text")
        self._plain_btn.setObjectName("preview_plain_btn")
        self._plain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plain_btn.setFixedHeight(38)
        self._plain_btn.clicked.connect(self._on_plain)
        lay.addWidget(self._plain_btn)

    def load(self, item: dict):
        self._item = item

        if item["type"] == "image":
            self._type_badge.setText("  IMAGE  ")
            self._type_badge.setObjectName("preview_badge_img")
        else:
            self._type_badge.setText("  TEXT  ")
            self._type_badge.setObjectName("preview_badge_txt")
        self._type_badge.style().unpolish(self._type_badge)
        self._type_badge.style().polish(self._type_badge)

        self._ts_lbl.setText(item["ts"].strftime("Copied at %H:%M:%S  ·  %B %d"))

        if item["type"] == "text":
            self._text_lbl.setText(item["text"])
            self._preview_stack.setCurrentIndex(0)
            char_count = len(item["text"])
            word_count = len(item["text"].split())
            line_count = item["text"].count("\n") + 1
            self._meta_lbl.setText(
                f"{char_count:,} characters  ·  {word_count:,} words  ·  {line_count:,} line{'s' if line_count != 1 else ''}"
            )
            self._plain_btn.setVisible(True)
        else:
            img = item["image"]
            qt_img = ImageQt.ImageQt(img.convert("RGBA"))
            pix = QPixmap.fromImage(qt_img).scaled(
                340, 280,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._img_lbl.setPixmap(pix)
            self._preview_stack.setCurrentIndex(1)
            self._meta_lbl.setText(
                f"{img.width} × {img.height} px  ·  {img.mode}"
            )
            self._plain_btn.setVisible(False)

        self._paste_btn.setText("⏎  Paste this item")

    def clear(self):
        self._item = None
        self._preview_stack.setCurrentIndex(2)
        self._type_badge.setText("")
        self._ts_lbl.setText("")
        self._meta_lbl.setText("")

    def _on_paste(self):
        if self._item:
            self.paste_requested.emit(self._item)

    def _on_plain(self):
        if self._item:
            self.plain_requested.emit(self._item)


class ClipCard(QWidget):
    paste_sig    = pyqtSignal(dict)
    plain_sig    = pyqtSignal(dict)
    delete_sig   = pyqtSignal(int)
    selected_sig = pyqtSignal(int)

    def __init__(self, item: dict, index: int, parent=None):
        super().__init__(parent)
        self.item  = item
        self.index = index
        self.setObjectName("ClipCard")
        self.setFixedSize(240, 130)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._selected = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(5)

        # Top row
        top = QHBoxLayout()
        top.setSpacing(6)

        badge = QLabel("IMG" if item["type"] == "image" else "TXT")
        badge.setObjectName("badge_img" if item["type"] == "image" else "badge_txt")
        badge.setFixedHeight(17)
        top.addWidget(badge)

        ts = QLabel(item["ts"].strftime("%H:%M"))
        ts.setObjectName("card_ts")
        top.addWidget(ts)
        top.addStretch()

        del_btn = QPushButton("✕")
        del_btn.setObjectName("card_del")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(lambda: self.delete_sig.emit(self.index))
        top.addWidget(del_btn)
        root.addLayout(top)

        # Content preview
        if item["type"] == "image":
            preview = QLabel()
            qt_img = ImageQt.ImageQt(item["image"].convert("RGBA"))
            pix = QPixmap.fromImage(qt_img).scaled(
                216, 60,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            preview.setPixmap(pix)
            preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setObjectName("card_img_preview")
            root.addWidget(preview, stretch=1)
        else:
            text_preview = QLabel(item["text"][:120])
            text_preview.setObjectName("card_text_preview")
            text_preview.setWordWrap(True)
            text_preview.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            root.addWidget(text_preview, stretch=1)

        self._sel_bar = QFrame()
        self._sel_bar.setObjectName("sel_bar")
        self._sel_bar.setFixedHeight(2)
        self._sel_bar.setVisible(False)
        root.addWidget(self._sel_bar)

    def set_selected(self, val: bool):
        if self._selected == val:
            return
        self._selected = val
        self._sel_bar.setVisible(val)
        self.setProperty("selected", val)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.selected_sig.emit(self.index)

    def mouseDoubleClickEvent(self, e):
        self.paste_sig.emit(self.item)