"""侧栏里的 Claude 面板：把选中的区域或当前页发给 Claude 提问，可以追问，回答可以贴到页面上。"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from . import ai
from .appsettings import app_settings
from .i18n import T

QUICK = [(T("讲解"), T("请讲解这部分内容：它在说什么，关键点和容易出错的地方是什么。")),
         (T("翻译"), T("请把这部分内容翻译成中文，术语保留原文。")),
         (T("出题"), T("请根据这部分内容出 3 道考试风格的题目，先只给题目；我作答后再给答案和解析。")),
         (T("检查"), T("请检查图中我手写的解答：哪一步有错，正确的做法是什么。"))]


class _Input(QPlainTextEdit):
    """回车发送，Shift+回车换行。"""
    submit = Signal()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not (ev.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
        else:
            super().keyPressEvent(ev)


class AIPanel(QWidget):
    pasteRequested = Signal(str)  # 把这段回答贴到当前页

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = app_settings()
        self.messages = []      # 发给 API 的对话历史
        self.log = []           # 显示用：[(角色, 文字)]
        self.pending = None     # 等待发送的截图（QImage）
        self.pending_text = ""  # 随截图一起发的页面文字
        self.worker = None
        self.partial = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        top = QHBoxLayout()
        self.cb_model = QComboBox()
        self.cb_model.setEditable(True)  # 可以手动填别的模型代号
        for key, name in ai.MODELS:
            self.cb_model.addItem(name, key)
        saved = self.settings.value("claude_model", ai.DEFAULT_MODEL)
        i = self.cb_model.findData(saved)
        if i >= 0:
            self.cb_model.setCurrentIndex(i)
        else:
            self.cb_model.setEditText(saved)
        self.cb_model.setToolTip(T("模型。Sonnet 快而便宜，Opus / Fable 更强更贵。"))
        b_key = QPushButton(T("API 密钥…"))
        b_key.clicked.connect(self.ask_key)
        top.addWidget(self.cb_model, 1)
        top.addWidget(b_key)
        lay.addLayout(top)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)

        self.thumb = QLabel()
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:#F4F4F6; border:1px dashed #C7C7CC; border-radius:6px; padding:4px;")
        self.thumb.hide()
        lay.addWidget(self.thumb)

        quick = QHBoxLayout()
        for name, prompt in QUICK:
            b = QPushButton(name)
            b.setToolTip(prompt)
            b.clicked.connect(lambda _=False, p=prompt: self.send(p))
            quick.addWidget(b)
        lay.addLayout(quick)

        self.input = _Input()
        self.input.setPlaceholderText(T("输入问题，回车发送（Shift+回车换行）"))
        self.input.setFixedHeight(70)
        self.input.submit.connect(lambda: self.send())
        lay.addWidget(self.input)

        row = QHBoxLayout()
        self.b_send = QPushButton(T("发送"))
        self.b_send.clicked.connect(self._send_or_stop)
        b_paste = QPushButton(T("贴到页面"))
        b_paste.setToolTip(T("把最后一条回答作为文本框贴到当前页"))
        b_paste.clicked.connect(self._paste_last)
        b_clear = QPushButton(T("清空"))
        b_clear.clicked.connect(self.clear)
        row.addWidget(self.b_send, 1)
        row.addWidget(b_paste)
        row.addWidget(b_clear)
        lay.addLayout(row)
        self._render()

    # ------------------------------------------------------------------
    def model(self) -> str:
        i = self.cb_model.currentIndex()
        if i >= 0 and self.cb_model.itemText(i) == self.cb_model.currentText():
            return self.cb_model.itemData(i)
        return self.cb_model.currentText().strip() or ai.DEFAULT_MODEL

    def ask_key(self) -> bool:
        """填写 / 修改 API 密钥。"""
        text, ok = QInputDialog.getText(
            self, T("Claude API 密钥"),
            T("在 Claude Console（platform.claude.com）创建 API 密钥后粘贴到这里。\n"
              "密钥只保存在这台电脑上。使用时，选中的截图和问题会发送给 Anthropic，按用量计费。"),
            QLineEdit.Password, self.settings.value("claude_api_key", ""))
        if ok:
            self.settings.setValue("claude_api_key", text.strip())
        return ok and bool(text.strip())

    def attach(self, image, page_text: str = ""):
        """附上一张截图（选区或整页），等用户提问。"""
        self.pending, self.pending_text = image, page_text or ""
        if image is None:
            self.thumb.hide()
        else:
            pm = QPixmap.fromImage(image)
            self.thumb.setPixmap(pm.scaled(260, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.thumb.show()
        self.input.setFocus()

    def clear(self):
        if self.worker:
            self.worker.stop()
        self.messages, self.log, self.partial = [], [], ""
        self.attach(None)
        self._render()

    def _send_or_stop(self):
        if self.worker:
            self.worker.stop()
        else:
            self.send()

    def send(self, prompt: str = None):
        if self.worker:
            return
        text = (prompt or self.input.toPlainText()).strip()
        if not text and self.pending is None:
            return
        if not text:
            text = QUICK[0][1]
        if not ai.api_key() and not self.ask_key():
            return
        content = []
        if self.pending is not None:
            content.append(ai.image_block(self.pending))
            if self.pending_text.strip():
                content.append({"type": "text", "text": "Text extracted from this PDF page (may be incomplete):\n"
                                                        + self.pending_text.strip()[:6000]})
        content.append({"type": "text", "text": text})
        self.messages.append({"role": "user", "content": content})
        self.log.append(("user", ("🖼 " if self.pending is not None else "") + text))
        self.settings.setValue("claude_model", self.model())
        self.attach(None)
        if prompt is None:
            self.input.clear()
        self.partial = ""
        self.worker = ai.ClaudeWorker(ai.api_key(), self.model(), self.messages, self)
        self.worker.chunk.connect(self._on_chunk)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_thread_end)
        self.b_send.setText(T("停止"))
        self._render()
        self.worker.start()

    def _on_chunk(self, piece):
        self.partial += piece
        self._render()

    def _on_done(self, full):
        full = full or self.partial
        if full.strip():
            self.messages.append({"role": "assistant", "content": full})
            self.log.append(("assistant", full))
        else:
            self.messages.pop()  # 没有回答：撤回这条提问，避免历史里连着两条 user
            self.log.append(("error", T("没有收到回答。")))
        self.partial = ""
        self._render()

    def _on_failed(self, message, code):
        if self.messages and self.messages[-1]["role"] == "user":
            self.messages.pop()
        hint = ""
        if code == 401:
            hint = T("密钥无效，请点“API 密钥…”重新填写。")
        elif code in (402, 403):
            hint = T("账户没有权限或余额不足，请到 Claude Console 检查。")
        elif code == 404:
            hint = T("模型代号不对，请换一个模型。")
        elif code == 429:
            hint = T("请求太频繁或额度用完了，稍后再试。")
        elif code == 0:
            hint = T("网络连接失败，请检查网络。")
        self.log.append(("error", f"{hint}\n{message}".strip()))
        self.partial = ""
        self._render()

    def _on_thread_end(self):
        self.worker = None
        self.b_send.setText(T("发送"))
        self._render()

    def last_answer(self) -> str:
        for role, text in reversed(self.log):
            if role == "assistant":
                return text
        return ""

    def _paste_last(self):
        text = self.last_answer()
        if text:
            self.pasteRequested.emit(text)
        else:
            QMessageBox.information(self, "Claude", T("还没有可以贴的回答。"))

    def _render(self):
        parts = []
        if not self.log and not self.partial:
            parts.append(T("用套索圈住讲义上的一块内容，右键选“问 Claude”；或点顶部的“问 Claude”发送当前页。"))
        for role, text in self.log:
            if role == "user":
                parts.append(f"**{T('你')}**\n\n{text}")
            elif role == "assistant":
                parts.append(f"**Claude**\n\n{text}")
            else:
                parts.append(f"**⚠ {T('出错了')}**\n\n{text}")
        if self.worker is not None or self.partial:
            parts.append(f"**Claude**\n\n{self.partial or '…'}")
        self.view.setMarkdown("\n\n---\n\n".join(parts))
        self.view.moveCursor(QTextCursor.End)
