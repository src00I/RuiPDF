"""调用 Claude API（Anthropic Messages API）。只用 Python 标准库，在后台线程里流式接收回答。"""
import base64
import json
import os
import urllib.error
import urllib.request

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QThread, Signal
from PySide6.QtGui import QImage

from .appsettings import app_settings
from .i18n import LANG

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# 可选模型：代号, 显示名。也可以在面板里手动输入别的模型代号。
MODELS = [("claude-sonnet-5-5", "Claude Sonnet 5.5"), ("claude-opus-5-5", "Claude Opus 5.5"),
          ("claude-fable-5-2", "Claude Fable 5.2"), ("claude-haiku-5-5", "Claude Haiku 5.5")]
DEFAULT_MODEL = MODELS[0][0]
MAX_TOKENS = 2500

SYSTEM_PROMPT = (
    "You are a study tutor built into RuiPDF, a PDF annotation app. The user is a university student "
    "reviewing lecture slides and their own handwritten notes for exams, often in engineering subjects. "
    "They send you a cropped region or a whole page (printed lecture content plus handwriting) and a question.\n"
    "- Read the image carefully, including handwriting, formulas, axes and labels. If something is illegible, say so "
    "instead of guessing.\n"
    "- Be accurate first and concise second: explain the key idea, then the reasoning steps that matter for an exam.\n"
    "- If the user's own handwritten work contains a mistake, point to the exact step.\n"
    "- Write formulas as plain Unicode text (e.g. U = R·I, ω₀ = 1/√(LC)); do not use LaTeX, and avoid tables.\n"
    "- Use short paragraphs and simple lists so the answer reads well in a narrow side panel.\n"
    + ("- Answer in Simplified Chinese unless the user asks for another language. Keep technical terms from the "
       "material in their original language in brackets on first use."
       if LANG == "zh" else "- Answer in English unless the user asks for another language.")
)


def api_key() -> str:
    """密钥：优先用环境变量 ANTHROPIC_API_KEY，其次是设置里保存的。"""
    return (os.environ.get("ANTHROPIC_API_KEY") or app_settings().value("claude_api_key", "") or "").strip()


def image_block(img: QImage) -> dict:
    """QImage -> API 的图片内容块（PNG，base64）。"""
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.standard_b64encode(bytes(data)).decode("ascii")}}


def _open(request):  # 单独成函数，方便测试时替换
    return urllib.request.urlopen(request, timeout=120)


class ClaudeWorker(QThread):
    """发一次请求，流式返回。chunk：新到的一段文字；finished_ok：完整回答；failed：(错误说明, HTTP 状态码)。"""
    chunk = Signal(str)
    finished_ok = Signal(str)
    failed = Signal(str, int)

    def __init__(self, key: str, model: str, messages: list, parent=None):
        super().__init__(parent)
        self.key, self.model, self.messages = key, model, messages
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        body = json.dumps({"model": self.model, "max_tokens": MAX_TOKENS, "system": SYSTEM_PROMPT,
                           "messages": self.messages, "stream": True}).encode("utf-8")
        req = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "x-api-key": self.key, "anthropic-version": API_VERSION, "content-type": "application/json"})
        text = []
        try:
            with _open(req) as resp:
                for raw in resp:  # 服务器推送事件：每行 "data: {...}"
                    if self._stop:
                        break
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    kind = ev.get("type")
                    if kind == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                        piece = ev["delta"].get("text", "")
                        text.append(piece)
                        self.chunk.emit(piece)
                    elif kind == "error":
                        self.failed.emit(ev.get("error", {}).get("message", "error"), 0)
                        return
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8", "replace")).get("error", {}).get("message", "")
            except Exception:
                msg = ""
            self.failed.emit(msg or str(e), e.code)
            return
        except Exception as e:  # 断网、超时等
            self.failed.emit(str(e), 0)
            return
        self.finished_ok.emit("".join(text))
