#!/usr/bin/env python3
"""LLM / ASR 平台 API Key 连通性自测脚本。

只验证「集成商提供的 API Key 是否贯通」，不依赖抖音链接、不消耗多少额度：
- LLM：发一条极简 chat 请求（约几十 token），打印模型、耗时与回复片段。
- ASR：用 ffmpeg 生成 1 秒静音音频，POST 到转写接口，验证鉴权与可达性
  （ffmpeg 不可用时退化为「鉴权探针」，仅根据状态码判断 Key 是否有效）。

用法：
    # 复用环境变量（API_KEY / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL / ASR_MODEL）
    python scripts/check_api_keys.py

    # 只测其中一项
    python scripts/check_api_keys.py --only llm
    python scripts/check_api_keys.py --only asr

    # 临时覆盖 Key
    python scripts/check_api_keys.py --api-key sk-xxxx

退出码：全部通过为 0，否则为 1，便于在 CI / 脚本中判断。
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

# 默认配置（与项目保持一致：硅基流动同时提供 LLM 与 ASR）
DEFAULT_LLM_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_LLM_MODEL = "Qwen/Qwen3-8B"
DEFAULT_ASR_URL = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"

OK = "✅"
FAIL = "❌"
WARN = "⚠️"


def _resolve_key(cli_key: str) -> str:
    return cli_key or os.getenv("LLM_API_KEY") or os.getenv("API_KEY", "")


def check_llm(api_key: str) -> bool:
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL).rstrip("/")
    model = os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL)
    url = f"{base_url}/chat/completions"
    print(f"\n=== LLM 连通性 ===\n  endpoint: {url}\n  model:    {model}")
    if not api_key:
        print(f"{FAIL} 未提供 API Key（设置 LLM_API_KEY 或 API_KEY，或用 --api-key）")
        return False

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "只回复两个字：你好"}],
        "temperature": 0,
        "max_tokens": 16,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    t0 = time.time()
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except requests.RequestException as e:
        print(f"{FAIL} 网络错误: {e}")
        return False
    dt = time.time() - t0

    if resp.status_code == 401:
        print(f"{FAIL} 鉴权失败(401)：API Key 无效或已过期")
        return False
    if resp.status_code == 402 or "insufficient" in resp.text.lower() or "余额" in resp.text:
        print(f"{FAIL} 额度不足({resp.status_code})：{resp.text[:200]}")
        return False
    if resp.status_code != 200:
        print(f"{FAIL} 异常状态码 {resp.status_code}：{resp.text[:200]}")
        return False

    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} 响应解析失败: {e}；原文: {resp.text[:200]}")
        return False

    print(f"{OK} LLM 可用（{dt:.2f}s）回复片段: {content!r}")
    return True


def _make_silence(path: Path) -> bool:
    """用 ffmpeg 生成 1 秒静音 mp3；成功返回 True。"""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-t", "1", "-q:a", "9", str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return path.exists() and path.stat().st_size > 0
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def check_asr(api_key: str) -> bool:
    url = os.getenv("ASR_BASE_URL", DEFAULT_ASR_URL)
    model = os.getenv("ASR_MODEL", DEFAULT_ASR_MODEL)
    print(f"\n=== ASR 连通性 ===\n  endpoint: {url}\n  model:    {model}")
    if not api_key:
        print(f"{FAIL} 未提供 API Key（设置 API_KEY，或用 --api-key）")
        return False

    headers = {"Authorization": f"Bearer {api_key}"}

    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "silence.mp3"
        if _make_silence(audio):
            files = {
                "file": (audio.name, open(audio, "rb"), "audio/mpeg"),
                "model": (None, model),
            }
            try:
                resp = requests.post(url, headers=headers, files=files, timeout=60)
            except requests.RequestException as e:
                print(f"{FAIL} 网络错误: {e}")
                return False
            finally:
                files["file"][1].close()

            if resp.status_code == 401:
                print(f"{FAIL} 鉴权失败(401)：API Key 无效或已过期")
                return False
            if resp.status_code == 200:
                text = ""
                try:
                    text = resp.json().get("text", "")
                except Exception:  # noqa: BLE001
                    text = resp.text[:80]
                print(f"{OK} ASR 可用（1s 静音转写成功）text={text!r}")
                return True
            print(f"{FAIL} 异常状态码 {resp.status_code}：{resp.text[:200]}")
            return False

        # 退化：无 ffmpeg，仅做鉴权探针
        print(f"{WARN} 未找到 ffmpeg，改用鉴权探针（不发送音频）")
        try:
            resp = requests.post(url, headers=headers, data={"model": model}, timeout=30)
        except requests.RequestException as e:
            print(f"{FAIL} 网络错误: {e}")
            return False
        if resp.status_code == 401:
            print(f"{FAIL} 鉴权失败(401)：API Key 无效或已过期")
            return False
        # 缺少 file 通常返回 400，说明 Key 有效、仅请求不完整
        print(f"{OK} Key 鉴权通过（状态码 {resp.status_code}，缺音频属预期）")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM / ASR API Key 连通性自测")
    parser.add_argument("--api-key", default="", help="临时覆盖 API Key")
    parser.add_argument("--only", choices=["llm", "asr"], help="只测其中一项")
    args = parser.parse_args()

    api_key = _resolve_key(args.api_key)
    masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "(空)"
    print(f"使用 API Key: {masked}")

    results = []
    if args.only in (None, "llm"):
        results.append(check_llm(api_key))
    if args.only in (None, "asr"):
        results.append(check_asr(api_key))

    ok = all(results) and bool(results)
    print(f"\n{'全部通过 ' + OK if ok else '存在失败 ' + FAIL}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
