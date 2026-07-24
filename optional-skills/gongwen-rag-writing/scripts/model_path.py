# 本地 embedding 模型路径解析（内网离线）
from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_embedding_model(default_hub_id: str = "BAAI/bge-small-zh-v1.5") -> str:
    """Prefer env or skill-local models/; fail closed when HF offline and missing."""
    env = os.environ.get("GONGWEN_EMBEDDING_MODEL", "").strip()
    if env:
        return env

    skill_root = Path(__file__).resolve().parent.parent
    local = skill_root / "models" / "bge-small-zh-v1.5"
    if local.is_dir() and any(local.iterdir()):
        return str(local)

    offline = os.environ.get("HF_HUB_OFFLINE", "").lower() in ("1", "true", "yes")
    offline = offline or os.environ.get("TRANSFORMERS_OFFLINE", "").lower() in ("1", "true", "yes")
    if offline:
        print(
            f"❌ 未找到本地 embedding 模型目录: {local}\n"
            "请将 bge-small-zh-v1.5 放入 skill 的 models/ 下，"
            "或设置环境变量 GONGWEN_EMBEDDING_MODEL。内网禁止联网下载。",
            file=sys.stderr,
        )
        sys.exit(2)
    return default_hub_id
