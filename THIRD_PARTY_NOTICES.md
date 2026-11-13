# Third-party notices / 第三方组件声明

RuiPDF itself is licensed under the GNU Affero General Public License v3.0 (see `LICENSE`).
It uses the components below. Each remains under its own license.

RuiPDF 本身按 GNU Affero General Public License v3.0 发布（见 `LICENSE`）。
它用到下面这些组件，各自仍按原来的许可证。

| Component | Used for | License | Source |
|---|---|---|---|
| PyMuPDF / MuPDF | Reading, rendering and writing PDF | AGPL-3.0 (or a commercial license from Artifex) | https://github.com/pymupdf/PyMuPDF |
| PySide6 / Qt 6 (including Qt WebEngine) | User interface; laying out pasted answers | LGPL-3.0 (some modules GPL-3.0); commercial license available from The Qt Company | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Chromium (part of Qt WebEngine) | Browser engine behind Qt WebEngine | BSD-3-Clause and others | https://www.chromium.org |
| markdown-it-py | Markdown to HTML | MIT | https://github.com/executablebooks/markdown-it-py |
| KaTeX 0.16.11 | Rendering formulas | MIT | https://github.com/KaTeX/KaTeX |
| KaTeX fonts | Formula fonts | SIL Open Font License 1.1 | https://github.com/KaTeX/KaTeX |

## Where the copies are / 这些组件在哪

- **In this repository**: only KaTeX (`ruipdf/assets/katex/`: `katex.min.js`, `katex.min.css`, 20 `.woff2` fonts),
  unmodified, downloaded from the official npm distribution. See the README in that folder.
- **Installed by pip** when running from source: PyMuPDF, PySide6, markdown-it-py (`requirements.txt`).
- **Inside the packaged program** (`dist\RuiPDF\`, the installer): all of the above, unmodified, as shipped in
  their official wheels. PyInstaller only collects them into the `_internal` folder; the Qt libraries stay as
  separate DLLs there, so they can be replaced with other builds of the same version.

## License texts / 许可证全文

- AGPL-3.0: `LICENSE` in this repository
- LGPL-3.0: https://www.gnu.org/licenses/lgpl-3.0.html
- GPL-3.0: https://www.gnu.org/licenses/gpl-3.0.html
- Qt's own third-party notices: https://doc.qt.io/qt-6/licenses-used-in-qt.html
- Qt WebEngine / Chromium notices: https://doc.qt.io/qt-6/qtwebengine-licensing.html
- SIL OFL 1.1: https://openfontlicense.org

### KaTeX (MIT)

```
The MIT License (MIT)

Copyright (c) 2013-2020 Khan Academy and other contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### markdown-it-py (MIT)

```
MIT License

Copyright (c) 2020 ExecutableBookProject

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
