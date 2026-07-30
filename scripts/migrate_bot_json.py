# -*- coding: utf-8 -*-
"""bot.json 配置数据迁移到数据库脚本。

读取 backend-gateway/config/bot.json 并调用 data-client
写入 PostgreSQL 数据库，实现平滑过渡。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 保证脚本能导入 backend-share/data-client
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARE_CLIENT_PATH = PROJECT_ROOT / "backend-share" / "data-client" / "src"
if str(SHARE_CLIENT_PATH) not in sys.path:
    sys.path.insert(0, str(SHARE_CLIENT_PATH))

from api_common import DuplicateResourceError  # noqa: E402
from data_client import get_data_client  # noqa: E402


def migrate_bot_json() -> None:
    """读取 bot.json 并迁移数据至数据库。"""
    config_path = PROJECT_ROOT / "backend-gateway" / "config" / "bot.json"
    if not config_path.exists():
        print(f"[SKIP] 未找到配置文件: {config_path}，跳过迁移。")
        return

    print(f"[INFO] 正在从 {config_path} 读取机器人配置...")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[ERROR] 读取或解析 bot.json 失败: {exc}")
        return

    bots = data.get("bots", [])
    if not isinstance(bots, list) or not bots:
        print("[WARN] bot.json 中无有效 bots 配置。")
        return

    client = get_data_client()
    success_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, bot_cfg in enumerate(bots, start=1):
        bot_id = bot_cfg.get("bot_id")
        platform = bot_cfg.get("platform", "feishu")
        app_id = bot_cfg.get("app_id", "")
        app_secret = bot_cfg.get("app_secret", "")
        mode = bot_cfg.get("mode", "test")
        name = bot_cfg.get("name", f"Bot-{bot_id}")

        if not bot_id:
            print(f"[WARN] 第 {idx} 个条目缺失 bot_id，跳过。")
            failed_count += 1
            continue

        try:
            client.create_bot(
                bot_id=bot_id,
                name=name,
                platform=platform,
                app_id=app_id,
                app_secret=app_secret,
                mode=mode,
            )
            print(f"[SUCCESS] 迁移机器人成功: bot_id='{bot_id}', platform='{platform}'")
            success_count += 1
        except DuplicateResourceError:
            print(f"[SKIP] 机器人 '{bot_id}' 数据库中已存在，跳过导入。")
            skipped_count += 1
        except Exception as exc:
            print(f"[FAILED] 迁移机器人 '{bot_id}' 失败: {exc}")
            failed_count += 1

    print("\n" + "=" * 40)
    print(f"迁移完成！成功: {success_count}, 跳过(已存在): {skipped_count}, 失败: {failed_count}")
    print("=" * 40)


if __name__ == "__main__":
    migrate_bot_json()
