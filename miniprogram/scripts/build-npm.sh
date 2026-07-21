#!/usr/bin/env bash
# 将 node_modules 中的小程序 npm 包同步到 miniprogram_npm/
# 等价于微信开发者工具「工具 → 构建 npm」（仅处理 tdesign-miniprogram）
# 并将 TDesign 图标字体改为本地 assets（避免 CDN ERR_CACHE_MISS）
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d node_modules/tdesign-miniprogram/miniprogram_dist ]]; then
  echo "请先在本目录执行: npm install"
  exit 1
fi

rm -rf miniprogram_npm/tdesign-miniprogram
mkdir -p miniprogram_npm
cp -r node_modules/tdesign-miniprogram/miniprogram_dist miniprogram_npm/tdesign-miniprogram

# 图标字体走本地，避免微信小程序加载 tdesign.gtimg.com 失败
ICON_WXSS="miniprogram_npm/tdesign-miniprogram/icon/icon.wxss"
if [[ -f "$ICON_WXSS" ]]; then
  # 相对 icon/ 目录：../../assets/fonts/
  sed -i \
    -e "s|https://tdesign.gtimg.com/icon/[0-9.]*/fonts/t\.eot[^'\")]*|/assets/fonts/t.ttf|g" \
    -e "s|https://tdesign.gtimg.com/icon/[0-9.]*/fonts/t\.woff|/assets/fonts/t.woff|g" \
    -e "s|https://tdesign.gtimg.com/icon/[0-9.]*/fonts/t\.ttf|/assets/fonts/t.ttf|g" \
    -e "s|https://tdesign.gtimg.com/icon/[0-9.]*/fonts/t\.svg[^'\")]*|/assets/fonts/t.ttf|g" \
    "$ICON_WXSS"
  # 简化为仅本地 woff/ttf
  python3 - <<'PY'
from pathlib import Path
import re
p = Path("miniprogram_npm/tdesign-miniprogram/icon/icon.wxss")
text = p.read_text(encoding="utf-8")
text = re.sub(
    r"@font-face\s*\{[^}]*font-family:\s*t;[^}]*\}",
    """@font-face {
  font-family: t;
  src: url('/assets/fonts/t.woff') format('woff'), url('/assets/fonts/t.ttf') format('truetype');
  font-weight: normal;
  font-style: normal;
}""",
    text,
    count=1,
    flags=re.DOTALL,
)
p.write_text(text, encoding="utf-8")
print("已将 TDesign 图标字体改为本地 /assets/fonts/")
PY
fi

echo "已生成 miniprogram_npm/tdesign-miniprogram"
