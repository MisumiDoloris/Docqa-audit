"""把 Docling 的输出转成这一层能吃的 Markdown。

为什么要一个适配器，而不是 fork Docling：
- 只调用不复制，许可干净，不牵扯 AGPL 传染
- 上游改接口，改这一支就够，工具本体不受影响
- 面试能讲清取舍：底座可换，判据不能换

用法：
    python3 -m docqa_audit convert --pdf 某文件.pdf --out demo/parse/out.md

第一次跑会下载 Docling 的版面模型，几百 MB，走网络。之后是本地推理。
没装 Docling 不影响三层验收本身，核心逻辑只用标准库。
"""

import os


def available():
    try:
        import docling.document_converter  # noqa: F401
        return True
    except Exception:
        return False


def convert_to_markdown(pdf_path, out_path=None):
    """跑 Docling，返回 Markdown 文本；给了 out_path 就顺手落盘。"""
    try:
        from docling.document_converter import DocumentConverter
    except Exception as exc:  # pragma: no cover - 取决于有没有装
        raise RuntimeError(
            "没装 Docling。装法：.venv/bin/pip install docling（走代理）。"
            "验收层本身不需要它，只有 convert 这个子命令需要。"
        ) from exc

    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    md = result.document.export_to_markdown()

    if out_path:
        parent = os.path.dirname(os.path.abspath(out_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
    return md
