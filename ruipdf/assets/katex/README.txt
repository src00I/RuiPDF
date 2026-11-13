KaTeX 0.16.11（https://katex.org，MIT 许可；字体为 SIL OFL 1.1 / MIT）

来源：https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/
  katex.min.js、katex.min.css、fonts/*.woff2（20 个）
只取了 woff2 字体；katex.min.css 里还列着 woff / ttf 的备用地址，Chromium 用不到。

用途：ruipdf/richpaste.py 排版粘贴进来的 AI 回答时渲染公式。随程序带着，运行时不联网。
升级：把上面地址里的版本号换掉重新下载这些文件即可，然后跑一遍 python tests/rich.py。
