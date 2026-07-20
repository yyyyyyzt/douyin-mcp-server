#!/usr/bin/env bash
# 将 node_modules 中的小程序 npm 包同步到 miniprogram_npm/
# 等价于微信开发者工具「工具 → 构建 npm」（仅处理 tdesign-miniprogram）
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d node_modules/tdesign-miniprogram/miniprogram_dist ]]; then
  echo "请先在本目录执行: npm install"
  exit 1
fi

rm -rf miniprogram_npm/tdesign-miniprogram
mkdir -p miniprogram_npm
cp -r node_modules/tdesign-miniprogram/miniprogram_dist miniprogram_npm/tdesign-miniprogram
echo "已生成 miniprogram_npm/tdesign-miniprogram"
