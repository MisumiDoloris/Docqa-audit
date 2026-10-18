#!/usr/bin/env bash
# 在纯 CPU、无 sudo 的机器上装 Docling 的完整办法（2026-10-18 实测走通）
#
# 踩过的四个坑，一次说清：
# 1. PyPI 的 torch 轮子是 CUDA 版，装它要拉几个 G 的 nvidia 库，import 还要 libcublasLt.so。
#    必须去 download.pytorch.org/whl/cpu 下 +cpu 那支（本机直连这个域名是通的，不用代理）。
# 2. torchvision 也得用 +cpu 那支，否则 import 时报 "operator torchvision::nms does not exist"，
#    它和 CUDA 版 torch 的 ABI 对不上。
# 3. transformers 5.x 在这套组合下会炸在 AutoImageProcessor，降到 4.x。
# 4. HuggingFace 默认走 Xet 传输，国内镜像会 401。设 HF_HUB_DISABLE_XET=1 + HF_ENDPOINT 走 hf-mirror。
#
# 注意：旧版本这个脚本走的是「--no-deps + pip check 循环补依赖」，那条路是死的，
# 因为 torch 的 CUDA 依赖写在 METADATA 里，pip check 认定它缺，绕不掉，import 也真会炸。
set -u
cd "$(dirname "$0")/.." || exit 1
PY=".venv/bin/python"
PIP=".venv/bin/pip"
M="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --no-input"
PT="https://download.pytorch.org/whl/cpu"
mkdir -p wheels

TORCH="torch-2.14.1+cpu-cp310-cp310-manylinux_2_28_x86_64.whl"
TV="torchvision-0.29.1+cpu-cp310-cp310-manylinux_2_28_x86_64.whl"

echo "[1/5] 下载 CPU 版 torch 与 torchvision"
for f in "$TORCH" "$TV"; do
  if [ -f "wheels/$f" ]; then echo "  已有 $f"; continue; fi
  curl -s -o "wheels/$f" "$PT/${f//+/%2B}" || { echo "  下载失败 $f"; exit 1; }
done

echo "[2/5] 装 torch / torchvision（--no-deps，不带 CUDA）"
$PIP install $M --no-deps "./wheels/$TORCH" "./wheels/$TV" >/dev/null || exit 1
$PIP install $M filelock typing-extensions sympy networkx jinja2 fsspec >/dev/null
$PY -c "import torch, torchvision; print('  torch', torch.__version__, '/ torchvision', torchvision.__version__)" || exit 1

echo "[3/5] 装 docling 与其余依赖"
$PIP install $M docling >/dev/null || exit 1
$PIP install $M "transformers<5" >/dev/null || exit 1

echo "[4/5] 自检"
$PY - <<'EOF'
from docling.document_converter import DocumentConverter  # noqa: F401
import transformers
print("  docling 导入成功，transformers", transformers.__version__)
EOF

echo "[5/5] 首次转换会从 hf-mirror 下版面模型（约 160MB）"
cat <<'TIP'

跑转换时记得带这两个环境变量，否则模型下不动：

  HF_HUB_DISABLE_XET=1 HF_ENDPOINT=https://hf-mirror.com \
    .venv/bin/python -m docqa_audit convert --tool docling --pdf 某文件.pdf --out 输出.md

TIP
