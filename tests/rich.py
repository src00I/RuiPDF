"""排版测试：把一段带公式的 Markdown 真的排成 PDF 片段，检查结果。

用法（在项目根目录）：  python tests/rich.py [输出目录]
通过时打印 RICH OK。它要启动 Qt 自带的浏览器引擎，比冒烟测试慢（几秒），所以单独放。
给了输出目录就把排出来的 PDF 和一张渲染图存进去，可以打开看效果。
只验证"排得出来、是一页、尺寸对、公式用上了数学字体"，好不好看要人看。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymupdf  # noqa: E402
from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication([])
from ruipdf import richpaste  # noqa: E402
from ruipdf.stroke import RichItem  # noqa: E402

out_dir = sys.argv[1] if len(sys.argv) > 1 else None
SAMPLES = {
    "claude": (r"""## 基尔霍夫电流定律

对任一节点，流入电流的代数和为零：$\sum_k i_k = 0$。价格 $5 和 $10 不是公式。

$$
\oint_S \mathbf{J}\cdot d\mathbf{A} = -\frac{dQ}{dt}
$$

1. 稳态时 $\frac{dQ}{dt}=0$
2. 所以 $i_3 = \begin{cases} 2\,\mathrm{A}, & t<0 \\ 0, & t\ge 0\end{cases}$

| 量 | 符号 |
|---|---|
| 电阻 | $R$ |

```python
def kcl(currents):
    return sum(currents)
```
""", 300, 10.5),
    "gpt": (r"""The roots are \( x = \frac{-b \pm \sqrt{b^2-4ac}}{2a} \), and

\[
\begin{aligned}
A\mathbf{x} &= \mathbf{b} \\
\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}\begin{pmatrix} x \\ y \end{pmatrix} &= \begin{pmatrix} 5 \\ 6 \end{pmatrix}
\end{aligned}
\]

Bad TeX $\frac{1}{$ is shown as source instead of breaking the rest.""", 260, 12.0),
}
results = {}
t0 = time.perf_counter()


def done(name, data):
    results[name] = (data, time.perf_counter() - t0)
    if len(results) == len(SAMPLES):
        app.quit()


for name, (text, width, size) in SAMPLES.items():
    richpaste.render(richpaste.to_body(text), width, "", size, lambda data, name=name: done(name, data))
QTimer.singleShot(60000, app.quit)
app.exec()
richpaste.shutdown()

for name, (text, width, size) in SAMPLES.items():
    assert name in results, f"{name}: 一分钟内没有排完"
    data, secs = results[name]
    assert data, f"{name}: 排版失败"
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert len(doc) == 1, f"{name}: 应该正好一页，实际 {len(doc)} 页"
    r = doc[0].rect
    assert abs(r.width - width) < 2 and 30 < r.height < 1500, (name, r)
    fonts = {f[3] for f in doc[0].get_fonts()}
    assert any("KaTeX" in f for f in fonts), f"{name}: 公式没有用上 KaTeX 的字体：{fonts}"
    words = doc[0].get_text()
    assert ("基尔霍夫" in words) if name == "claude" else ("roots" in words), f"{name}: 文字不在 PDF 里"
    item = RichItem(data, 10, 10, r.width, r.height, text)  # 能作为页面对象渲染出来，底是透明的
    img = item.raster(2.0)
    assert abs(img.width() - r.width * 2) <= 2 and img.pixelColor(1, 1).alpha() == 0
    print(f"{name}: {secs:.1f} s, {len(data) // 1024} KB, {r.width:.0f} x {r.height:.0f} pt, {len(fonts)} 种字体")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"rich_{name}.pdf"), "wb") as f:
            f.write(data)
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), alpha=False).save(os.path.join(out_dir, f"rich_{name}.png"))
    doc.close()
print("RICH OK")
