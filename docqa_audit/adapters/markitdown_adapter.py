"""把 MarkItDown 的输出转成这一层能吃的 Markdown。

为什么默认用它：
- MIT 许可，代码干净，没有传染性
- 纯 python，不依赖 torch，256M 的环境就能装完、一分钟跑完
- 电子版 PDF 的表格它能拿得住，够验收层做第一遍体检

它不管什么：扫描件（没有 OCR）。扫描件那批要走 Docling 或者别的带 OCR 的底座，
见同一目录下的 docling_adapter.py。这就是适配器模式的意义：底座能换，判据不换。
"""

import os


def available():
    try:
        import markitdown  # noqa: F401
        return True
    except Exception:
        return False


def convert_to_markdown(pdf_path, out_path=None):
    try:
        from markitdown import MarkItDown
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "没装 markitdown。装法：.venv/bin/pip install 'markitdown[pdf]'"
        ) from exc

    md = MarkItDown().convert(pdf_path).text_content or ""

    if out_path:
        parent = os.path.dirname(os.path.abspath(out_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
    return md
