import io
import win32gui
from PIL import Image, ImageFilter, ImageQt

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QScrollArea,
    QGridLayout, QFrame
)
from PyQt6.QtGui import QColor, QPixmap, QPainter, QKeyEvent
from PyQt6.QtCore import (
    QTimer, Qt, QPropertyAnimation, QEasingCurve,
    QBuffer, QByteArray, QIODevice
)

from widgets import ClipCard, PreviewPanel
from backend import paste_text, paste_image

class FullscreenOverlay(QWidget):
    def __init__(self):
        super().__init__()

        screen = QApplication.primaryScreen()
        self._screen_geo = screen.geometry()
        self.setGeometry(self._screen_geo)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)

        self._history       = []
        self._prev_hwnd     = None
        self._bg_pixmap     = None
        self._anim          = None
        self._visible_cards = []
        self._selected_idx  = None
        self._grid_cols     = 4

        self._build_ui()
        self._apply_style()

    def _capture_desktop(self):
        screen  = QApplication.primaryScreen()
        raw_pix = screen.grabWindow(0)
        raw_img = raw_pix.toImage()

        ba   = QByteArray()
        qbuf = QBuffer(ba)
        qbuf.open(QIODevice.OpenModeFlag.WriteOnly)
        raw_img.save(qbuf, "PNG")
        qbuf.close()

        pil      = Image.open(io.BytesIO(bytes(ba))).convert("RGB")
        blurred  = pil.filter(ImageFilter.GaussianBlur(radius=22))
        overlay  = Image.new("RGBA", blurred.size, (0, 0, 0, 120))
        combined = Image.alpha_composite(blurred.convert("RGBA"), overlay)

        qt_img          = ImageQt.ImageQt(combined)
        self._bg_pixmap = QPixmap.fromImage(qt_img)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._bg_pixmap:
            painter.drawPixmap(self.rect(), self._bg_pixmap)
        else:
            painter.fillRect(self.rect(), QColor(8, 10, 16, 230))
        painter.end()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(60)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(36, 0, 36, 0)
        tbl.setSpacing(0)

        logo_icon = QLabel("◈")
        logo_icon.setObjectName("logo_icon")
        tbl.addWidget(logo_icon)
        tbl.addSpacing(8)

        logo = QLabel("ClipVault")
        logo.setObjectName("logo")
        tbl.addWidget(logo)
        tbl.addSpacing(16)

        self._count_lbl = QLabel("0 items")
        self._count_lbl.setObjectName("count_lbl")
        tbl.addWidget(self._count_lbl)
        tbl.addStretch()

        for key, label in [("↑↓←→", "Navigate"), ("⏎", "Paste"), ("P", "Plain"), ("Del", "Remove"), ("Esc", "Close")]:
            k = QLabel(key); k.setObjectName("kbd")
            l = QLabel(f"  {label}   "); l.setObjectName("hint_lbl")
            tbl.addWidget(k); tbl.addWidget(l)

        close_btn = QPushButton("✕  Close")
        close_btn.setObjectName("close_btn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.fade_out)
        tbl.addWidget(close_btn)

        root.addWidget(topbar)

        # Search bar
        search_wrap = QWidget()
        search_wrap.setObjectName("search_wrap")
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(36, 12, 36, 12)
        sl.setSpacing(10)

        self._search = QLineEdit()
        self._search.setObjectName("search")
        self._search.setPlaceholderText("  ⌕   Search clipboard history…")
        self._search.setFixedHeight(44)
        self._search.textChanged.connect(self._filter)
        self._search.installEventFilter(self)
        sl.addWidget(self._search)

        clear_btn = QPushButton("Clear All")
        clear_btn.setObjectName("clear_btn")
        clear_btn.setFixedHeight(44)
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_all)
        sl.addWidget(clear_btn)

        root.addWidget(search_wrap)

        # Main content area
        content_wrap = QWidget()
        content_wrap.setObjectName("content_wrap")
        content_lay = QHBoxLayout(content_wrap)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)

        # Left: section label + grid
        left_wrap = QWidget()
        left_wrap.setObjectName("left_wrap")
        left_lay = QVBoxLayout(left_wrap)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._section_lbl = QLabel("RECENT")
        self._section_lbl.setObjectName("section_lbl")
        self._section_lbl.setContentsMargins(40, 8, 0, 8)
        left_lay.addWidget(self._section_lbl)

        scroll = QScrollArea()
        scroll.setObjectName("scroll_area")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_container = QWidget()
        self._grid_container.setObjectName("grid_container")
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(36, 0, 16, 36)
        self._grid_layout.setSpacing(14)

        scroll.setWidget(self._grid_container)
        left_lay.addWidget(scroll, stretch=1)
        content_lay.addWidget(left_wrap, stretch=1)

        # Right: preview panel
        self._preview_panel = PreviewPanel()
        self._preview_panel.setObjectName("preview_panel_outer")
        self._preview_panel.setFixedWidth(380)
        self._preview_panel.paste_requested.connect(self._paste_item)
        self._preview_panel.plain_requested.connect(self._plain_item)

        self._preview_visible = False
        self._preview_panel.setMaximumWidth(0)

        content_lay.addWidget(self._preview_panel)
        root.addWidget(content_wrap, stretch=1)

        # Empty state
        self._empty = QWidget()
        self._empty.setObjectName("empty_state")
        el = QVBoxLayout(self._empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_icon = QLabel("◈")
        empty_icon.setStyleSheet("font-size:52px; color:rgba(34,211,195,0.10); background:transparent;")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title = QLabel("Nothing copied yet")
        empty_title.setStyleSheet("color:rgba(255,255,255,0.13); font-size:20px; font-weight:700; background:transparent;")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_sub = QLabel("Copy any text or image and it'll appear here instantly.")
        empty_sub.setStyleSheet("color:rgba(255,255,255,0.07); font-size:13px; background:transparent;")
        empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        el.addWidget(empty_icon)
        el.addSpacing(10)
        el.addWidget(empty_title)
        el.addSpacing(4)
        el.addWidget(empty_sub)

        root.addWidget(self._empty)
        self._refresh_empty()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            k = event.key()
            if k == Qt.Key.Key_Escape:
                self.fade_out()
                return True
            if k in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
                     Qt.Key.Key_Return, Qt.Key.Key_Enter,
                     Qt.Key.Key_Delete, Qt.Key.Key_P):
                self.keyPressEvent(event)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.fade_out()
            return
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._paste_selected()
            return
        elif k == Qt.Key.Key_P:
            self._plain_selected()
            return
        elif k in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._delete_selected()
            return
        elif k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._handle_navigation(e)
            return
        super().keyPressEvent(e)

    def _handle_navigation(self, e: QKeyEvent):
        k    = e.key()
        mods = QApplication.keyboardModifiers()
        if not self._visible_cards:
            return

        if self._selected_idx is None:
            self._selected_idx = 0

        cols = self._grid_cols
        idx  = self._selected_idx

        if   k == Qt.Key.Key_Left:  idx = max(0, idx - 1)
        elif k == Qt.Key.Key_Right: idx = min(len(self._visible_cards) - 1, idx + 1)
        elif k == Qt.Key.Key_Up:    idx = max(0, idx - cols)
        elif k == Qt.Key.Key_Down:  idx = min(len(self._visible_cards) - 1, idx + cols)
        elif k == Qt.Key.Key_Tab:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                idx = max(0, idx - 1)
            else:
                idx = min(len(self._visible_cards) - 1, idx + 1)

        if idx != self._selected_idx:
            self._selected_idx = idx
            self._select_card(idx)

    def _select_card(self, card_index_in_list: int):
        for c in self._visible_cards:
            c.set_selected(False)
        if 0 <= card_index_in_list < len(self._visible_cards):
            card = self._visible_cards[card_index_in_list]
            card.set_selected(True)
            self._preview_panel.load(card.item)
            self._show_preview_panel()
            self.setFocus()

    def _on_card_selected_by_click(self, history_index: int):
        for vis_idx, card in enumerate(self._visible_cards):
            if card.index == history_index:
                self._selected_idx = vis_idx
                self._select_card(vis_idx)
                break

    def _show_preview_panel(self):
        if self._preview_visible:
            return
        self._preview_visible = True
        anim = QPropertyAnimation(self._preview_panel, b"maximumWidth")
        anim.setDuration(220)
        anim.setStartValue(0)
        anim.setEndValue(380)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._preview_anim = anim

    def _hide_preview_panel(self):
        if not self._preview_visible:
            return
        self._preview_visible = False
        anim = QPropertyAnimation(self._preview_panel, b"maximumWidth")
        anim.setDuration(180)
        anim.setStartValue(380)
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._preview_panel.clear)
        anim.start()
        self._preview_anim = anim

    def add_item(self, item: dict):
        if self._history:
            last = self._history[0]
            if last["type"] == item["type"] == "text" and last["text"] == item["text"]:
                return
        self._history.insert(0, item)
        if len(self._history) > 200:
            self._history.pop()
        if self.isVisible():
            self._rebuild_and_select(self._search.text(), select_idx=0)

    def _rebuild(self, query=""):
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        W    = self._screen_geo.width() - 380 
        cols = max(2, (W - 80) // (240 + 14))
        self._grid_cols     = cols
        self._visible_cards = []

        shown = 0
        for i, item in enumerate(self._history):
            if query and query.lower() not in item["label"].lower():
                continue
            card = ClipCard(item, i)
            card.paste_sig.connect(self._paste_item)
            card.plain_sig.connect(self._plain_item)
            card.delete_sig.connect(self._delete_item)
            card.selected_sig.connect(self._on_card_selected_by_click)
            self._visible_cards.append(card)
            self._grid_layout.addWidget(card, shown // cols, shown % cols)
            shown += 1

        if shown > 0:
            remainder = shown % cols
            if remainder:
                for c in range(remainder, cols):
                    sp = QWidget(); sp.setFixedSize(240, 130); sp.setObjectName("card_spacer")
                    self._grid_layout.addWidget(sp, (shown - 1) // cols, c)

        total = len(self._history)
        self._count_lbl.setText(f"{total} item{'s' if total != 1 else ''}")
        q = self._search.text()
        self._section_lbl.setText(
            f"{shown} RESULT{'S' if shown != 1 else ''} FOR \"{q.upper()}\"" if q else "RECENT"
        )
        self._refresh_empty()
        self._selected_idx = None

    def _rebuild_and_select(self, query="", select_idx=0):
        self._rebuild(query)
        if self._visible_cards:
            idx = min(select_idx, len(self._visible_cards) - 1)
            self._selected_idx = idx
            self._select_card(idx)

    def _filter(self, text):
        self._rebuild_and_select(text, select_idx=0)

    def _clear_all(self):
        self._history.clear()
        self._rebuild()
        self._hide_preview_panel()

    def _delete_item(self, idx: int):
        if 0 <= idx < len(self._history):
            keep = min(self._selected_idx or 0, len(self._history) - 2)
            keep = max(keep, 0)
            self._history.pop(idx)
            self._rebuild_and_select(self._search.text(), select_idx=keep)

    def _refresh_empty(self):
        has = len(self._history) > 0
        self._empty.setVisible(not has)
        self._grid_container.setVisible(has)

    def _paste_item(self, item: dict):
        self.fade_out()
        if item["type"] == "text":
            QTimer.singleShot(350, lambda: paste_text(item["text"]))
        elif item["type"] == "image":
            QTimer.singleShot(350, lambda: paste_image(item["image"]))

    def _plain_item(self, item: dict):
        self.fade_out()
        if item["type"] == "text":
            QTimer.singleShot(350, lambda: paste_text(item["text"]))

    def _paste_selected(self):
        if self._selected_idx is not None and self._visible_cards:
            self._paste_item(self._visible_cards[self._selected_idx].item)
        elif self._history:
            self._paste_item(self._history[0])

    def _plain_selected(self):
        if self._selected_idx is not None and self._visible_cards:
            item = self._visible_cards[self._selected_idx].item
            if item["type"] == "text":
                self._plain_item(item)
        elif self._history and self._history[0]["type"] == "text":
            self._plain_item(self._history[0])

    def _delete_selected(self):
        if self._selected_idx is not None and self._visible_cards:
            self._delete_item(self._visible_cards[self._selected_idx].index)
        elif self._history:
            self._delete_item(0)

    def fade_in(self):
        self._prev_hwnd = win32gui.GetForegroundWindow()
        self._capture_desktop()
        self.setWindowOpacity(0)
        self.show()
        self.activateWindow()
        self.raise_()
        self._search.clear()
        self._preview_visible = False
        self._preview_panel.setMaximumWidth(0)
        self._preview_panel.clear()
        self._rebuild_and_select(select_idx=0)
        self.setFocus()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(260)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def fade_out(self):
        if self._prev_hwnd:
            try:
                win32gui.SetForegroundWindow(self._prev_hwnd)
            except Exception:
                pass
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(180)
        self._anim.setStartValue(self.windowOpacity())
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self.hide)
        self._anim.start()

    def toggle_visibility(self):
        if self.isVisible() and self.windowOpacity() > 0.5:
            self.fade_out()
        else:
            self.fade_in()

    def closeEvent(self, event):
        event.ignore()
        self.fade_out()

    def _quit(self):
        QApplication.instance().quit()

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget {
                background: transparent;
                color: #c8dce8;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            #topbar { background: rgba(5, 8, 13, 0.78); border-bottom: 1px solid rgba(34,211,195,0.07); }
            #logo_icon { font-size: 17px; color: #22d3c3; background: transparent; }
            #logo { font-size: 17px; font-weight: 800; color: #eef6fa; background: transparent; letter-spacing: 0.4px; }
            #count_lbl { font-size: 11px; color: rgba(34,211,195,0.30); background: rgba(34,211,195,0.04); border: 1px solid rgba(34,211,195,0.09); border-radius: 10px; padding: 2px 11px; }
            #kbd { background: rgba(34,211,195,0.09); border: 1px solid rgba(34,211,195,0.16); border-radius: 4px; color: rgba(34,211,195,0.60); font-size: 9.5px; font-weight: 700; font-family: 'Consolas', monospace; padding: 1px 5px; }
            #hint_lbl { font-size: 10px; color: rgba(255,255,255,0.10); background: transparent; }
            #close_btn { background: rgba(255,70,70,0.07); border: 1px solid rgba(255,70,70,0.15); border-radius: 10px; color: rgba(255,90,90,0.45); font-size: 12px; font-weight: 600; padding: 6px 16px; margin-left: 14px; }
            #close_btn:hover { background: rgba(255,70,70,0.16); border-color: rgba(255,70,70,0.38); color: rgba(255,120,120,0.88); }
            #search_wrap { background: rgba(5, 8, 13, 0.65); border-bottom: 1px solid rgba(255,255,255,0.035); }
            #search { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 12px; padding: 0 18px; color: #d0e8f0; font-size: 15px; selection-background-color: rgba(34,211,195,0.22); }
            #search:focus { border-color: rgba(34,211,195,0.38); background: rgba(34,211,195,0.04); }
            #clear_btn { background: transparent; border: 1px solid rgba(255,70,70,0.16); border-radius: 12px; color: rgba(255,85,85,0.45); font-size: 12px; font-weight: 600; padding: 0 20px; }
            #clear_btn:hover { background: rgba(255,70,70,0.09); border-color: rgba(255,70,70,0.35); color: rgba(255,105,105,0.80); }
            #section_lbl { font-size: 9.5px; font-weight: 800; color: rgba(34,211,195,0.20); background: transparent; letter-spacing: 2px; padding-left: 40px; }
            #scroll_area { background: transparent; border: none; }
            #grid_container { background: transparent; }
            QScrollBar:vertical { background: transparent; width: 4px; margin: 8px 2px; }
            QScrollBar::handle:vertical { background: rgba(34,211,195,0.15); border-radius: 2px; min-height: 24px; }
            QScrollBar::handle:vertical:hover { background: rgba(34,211,195,0.32); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            #ClipCard { background: rgba(10, 15, 22, 0.80); border: 1px solid rgba(255,255,255,0.06); border-radius: 14px; }
            #ClipCard:hover { background: rgba(14, 22, 33, 0.90); border: 1px solid rgba(34,211,195,0.22); }
            #ClipCard[selected="true"] { background: rgba(22, 38, 50, 0.95); border: 1.5px solid rgba(34,211,195,0.55); }
            #sel_bar { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(34,211,195,0), stop:0.3 #22d3c3, stop:0.7 #22d3c3, stop:1 rgba(34,211,195,0)); border-radius: 1px; }
            #badge_txt { background: rgba(99,179,237,0.13); color: #63b3ed; border: 1px solid rgba(99,179,237,0.26); border-radius: 4px; font-size: 9px; font-weight: 800; padding: 1px 5px; letter-spacing: 0.8px; }
            #badge_img { background: rgba(34,211,195,0.13); color: #22d3c3; border: 1px solid rgba(34,211,195,0.26); border-radius: 4px; font-size: 9px; font-weight: 800; padding: 1px 5px; letter-spacing: 0.8px; }
            #card_ts { font-size: 10px; color: rgba(255,255,255,0.17); background: transparent; font-family: 'Consolas', monospace; }
            #card_del { background: transparent; border: none; color: rgba(255,70,70,0.22); font-size: 11px; border-radius: 3px; }
            #card_del:hover { background: rgba(255,70,70,0.10); color: rgba(255,100,100,0.75); }
            #card_text_preview { font-size: 11.5px; color: rgba(175,205,225,0.58); background: transparent; }
            #card_img_preview { background: transparent; }
            #card_spacer { background: transparent; border: none; }
            #preview_panel_outer { background: rgba(6, 10, 16, 0.88); border-left: 1px solid rgba(34,211,195,0.10); }
            #preview_badge_txt { background: rgba(99,179,237,0.14); color: #63b3ed; border: 1px solid rgba(99,179,237,0.28); border-radius: 6px; font-size: 10px; font-weight: 800; padding: 2px 10px; letter-spacing: 1px; }
            #preview_badge_img { background: rgba(34,211,195,0.14); color: #22d3c3; border: 1px solid rgba(34,211,195,0.28); border-radius: 6px; font-size: 10px; font-weight: 800; padding: 2px 10px; letter-spacing: 1px; }
            #preview_badge { background: transparent; border: none; }
            #preview_ts { font-size: 11px; color: rgba(255,255,255,0.20); background: transparent; font-family: 'Consolas', monospace; }
            #preview_text_scroll { background: transparent; border: none; }
            #preview_text_inner { background: transparent; }
            #preview_img_scroll { background: transparent; border: none; }
            #preview_text_lbl { font-size: 13px; color: rgba(200,224,240,0.85); background: transparent; line-height: 1.7; }
            #preview_img_lbl { background: transparent; }
            #preview_meta { font-size: 11px; color: rgba(34,211,195,0.35); background: transparent; font-family: 'Consolas', monospace; }
            #preview_div { color: rgba(255,255,255,0.06); }
            #preview_paste_btn { background: rgba(34,211,195,0.12); border: 1px solid rgba(34,211,195,0.28); border-radius: 11px; color: #22d3c3; font-size: 13px; font-weight: 700; }
            #preview_paste_btn:hover { background: rgba(34,211,195,0.24); border-color: rgba(34,211,195,0.55); color: #50ffe8; }
            #preview_plain_btn { background: rgba(99,179,237,0.08); border: 1px solid rgba(99,179,237,0.18); border-radius: 11px; color: rgba(99,179,237,0.65); font-size: 12px; font-weight: 600; }
            #preview_plain_btn:hover { background: rgba(99,179,237,0.18); border-color: rgba(99,179,237,0.40); color: #90cdf4; }
            #preview_empty_hint { font-size: 14px; color: rgba(255,255,255,0.08); background: transparent; line-height: 1.8; }
            #empty_state { background: transparent; }
        """)