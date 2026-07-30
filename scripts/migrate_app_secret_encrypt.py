"""一次性迁移脚本：把 bots 表中的明文 app_secret 加密为 ``enc:v1:`` 前缀密文。

背景：bot_service 已切换为「写入加密、读取解密」模式，存量明文 app_secret
需批量加密以保证 service 层 ``decrypt`` 行为一致（无前缀当明文兼容过渡，但
新写入必须带前缀）。

本脚本直接连 PostgreSQL（绕过 service 层），扫描所有 app_secret 非空且
未带 ``enc:v1:`` 前缀的记录，调 ``secret_crypto.encrypt`` 加密后 UPDATE。
幂等：已加密的记录跳过，重复执行无副作用。

运行方式（从 backend-data/backend/ 目录执行）::

    uv run python ../../scripts/migrate_app_secret_encrypt.py

依赖环境变量：
- ``APP_SECRET_KEY``：加密主密钥 passphrase（与 backend-data 运行时一致）
- 数据库连接配置（CORE_DB_* 或 Nacos 拉取的 POSTGRES_*）
"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证脚本能导入 backend-data/app 与 backend-share/crypto
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_DATA_PATH = _PROJECT_ROOT / "backend-data" / "backend"
_CRYPTO_SRC_PATH = _PROJECT_ROOT / "backend-share" / "crypto" / "src"
for _path in (_BACKEND_DATA_PATH, _CRYPTO_SRC_PATH):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from secret_crypto import encrypt  # noqa: E402
from secret_crypto.crypto import PREFIX  # noqa: E402
from sqlalchemy import select, text  # noqa: E402

from app.core.database import DatabaseRole, get_engine  # noqa: E402
from app.models.bot import Bot  # noqa: E402


def migrate_app_secret_encrypt() -> None:
    """扫描所有未加密的 app_secret，加密后写回数据库。"""
    engine = get_engine(DatabaseRole.CORE)
    encrypted_count = 0
    skipped_count = 0
    failed_count = 0

    with engine.begin() as conn:
        # 选出 app_secret 非空且未带 enc:v1: 前缀的记录。
        rows = conn.execute(
            select(Bot.id, Bot.bot_id, Bot.app_secret).where(
                Bot.app_secret.is_not(None),
                Bot.app_secret != "",
                text(f"app_secret NOT LIKE '{PREFIX}%'"),
            )
        ).all()

        if not rows:
            print("[INFO] 未发现需要迁移的明文 app_secret 记录。")
            return

        print(f"[INFO] 发现 {len(rows)} 条待加密记录，开始迁移...")

        for row in rows:
            bot_pk = row.id
            bot_id = row.bot_id
            plain_secret = row.app_secret
            try:
                cipher = encrypt(plain_secret)
            except Exception as exc:
                print(f"[FAILED] bot_id='{bot_id}' 加密失败: {exc}")
                failed_count += 1
                continue

            conn.execute(
                text("UPDATE bots SET app_secret = :cipher WHERE id = :pk"),
                {"cipher": cipher, "pk": bot_pk},
            )
            print(f"[SUCCESS] bot_id='{bot_id}' 已加密")
            encrypted_count += 1

    print("\n" + "=" * 40)
    print(
        f"迁移完成！加密: {encrypted_count}, "
        f"跳过(已加密或空): {skipped_count}, 失败: {failed_count}"
    )
    print("=" * 40)


if __name__ == "__main__":
    migrate_app_secret_encrypt()
