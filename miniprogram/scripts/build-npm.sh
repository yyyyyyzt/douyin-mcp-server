#!/usr/bin/env bash
# 将 node_modules 中的小程序 npm 包同步到 miniprogram_npm/
# 并把 TDesign 图标字体以 base64 写入 icon.wxss（微信拒绝本地 ttf/woff 路径）
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d node_modules/tdesign-miniprogram/miniprogram_dist ]]; then
  echo "请先在本目录执行: npm install"
  exit 1
fi

rm -rf miniprogram_npm/tdesign-miniprogram
mkdir -p miniprogram_npm
cp -r node_modules/tdesign-miniprogram/miniprogram_dist miniprogram_npm/tdesign-miniprogram

ICON_WXSS="miniprogram_npm/tdesign-miniprogram/icon/icon.wxss"
FONT_WOFF="assets/fonts/t.woff"
if [[ -f "$ICON_WXSS" && -f "$FONT_WOFF" ]]; then
  python3 - <<'PY'
from pathlib import Path
import base64
import re

wxss = Path("miniprogram_npm/tdesign-miniprogram/icon/icon.wxss")
woff = Path("assets/fonts/t.woff").read_bytes()
b64 = base64.b64encode(woff).decode("ascii")
face = f"""@font-face {{
  font-family: t;
  src: url('data:font/woff;charset=utf-8;base64,{b64}') format('woff');
  font-weight: normal;
  font-style: normal;
}}"""
text = wxss.read_text(encoding="utf-8")
text, n = re.subn(
    r"@font-face\s*\{[^}]*font-family:\s*t;[^}]*\}",
    face,
    text,
    count=1,
    flags=re.DOTALL,
)
wxss.write_text(text, encoding="utf-8")
print(f"已将 TDesign 图标字体嵌入为 base64，替换 {n} 处 @font-face")
PY
fi

echo "已生成 miniprogram_npm/tdesign-miniprogram"
