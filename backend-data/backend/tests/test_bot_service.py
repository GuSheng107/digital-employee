"""bot_service 单测：加解密 + 软删除重建 + CRUD。"""

from __future__ import annotations

from datetime import UTC

import pytest
from api_common import DuplicateResourceError, ResourceNotFoundError
from secret_crypto import decrypt, encrypt, is_encrypted
from secret_crypto.crypto import PREFIX

from app.models.bot import Bot
from app.services.bot_service import BotService

_PLAIN_SECRET = "feishu-app-secret-abc123"
_ANOTHER_SECRET = "wechat-app-secret-xyz789"


def _make_bot_row(
    db_session_factory,
    *,
    bot_id: str = "bot-1",
    app_secret_raw: str = _PLAIN_SECRET,
    status: int = 1,
    deleted: bool = False,
) -> Bot:
    """直接向 DB 插入一条 Bot 记录，绕过 service 层（用于构造存量数据场景）。"""
    from datetime import datetime

    with db_session_factory() as session:
        bot = Bot(
            bot_id=bot_id,
            name=f"Bot-{bot_id}",
            platform="feishu",
            app_id="app-1",
            app_secret=app_secret_raw,
            mode="test",
            status=status,
            deleted_at=datetime.now(tz=UTC) if deleted else None,
        )
        session.add(bot)
        session.commit()
        session.refresh(bot)
        return bot


# ── create_bot：加密写入 ──────────────────────────────────────────


class TestCreateBot:
    def test_create_encrypts_app_secret_in_db(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """create_bot 入参明文，DB 中应存储 enc:v1: 前缀密文。"""
        result = bot_service.create_bot(
            bot_id="bot-1",
            name="Bot-1",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
            mode="test",
        )

        # 返回给调用方的是脱敏值
        assert result["app_secret"] == "***"

        # DB 中存的是加密密文
        with db_session_factory() as session:
            row = session.query(Bot).filter(Bot.bot_id == "bot-1").one()
            assert is_encrypted(row.app_secret)
            assert row.app_secret != _PLAIN_SECRET
            assert decrypt(row.app_secret) == _PLAIN_SECRET

    def test_create_duplicate_active_raises(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """同 bot_id 的活跃 Bot 已存在时，create 应抛 DuplicateResourceError。"""
        _make_bot_row(db_session_factory, bot_id="dup-1", app_secret_raw="legacy")
        with pytest.raises(DuplicateResourceError):
            bot_service.create_bot(
                bot_id="dup-1",
                name="Dup",
                platform="feishu",
                app_id="app-1",
                app_secret=_PLAIN_SECRET,
            )

    def test_create_after_soft_delete_rebuilds(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """软删除后同 bot_id 可再次创建（partial unique index 语义）。"""
        # 先创建并删除
        bot_service.create_bot(
            bot_id="rebuild-1",
            name="V1",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        bot_service.delete_bot(bot_id="rebuild-1")

        # 重建
        result = bot_service.create_bot(
            bot_id="rebuild-1",
            name="V2",
            platform="wechat",
            app_id="app-2",
            app_secret=_ANOTHER_SECRET,
            mode="prod",
        )
        assert result["name"] == "V2"
        assert result["platform"] == "wechat"

        # DB 中应有两条记录，一条软删除，一条活跃
        with db_session_factory() as session:
            rows = session.query(Bot).filter(Bot.bot_id == "rebuild-1").all()
            assert len(rows) == 2
            active = [r for r in rows if r.deleted_at is None]
            deleted = [r for r in rows if r.deleted_at is not None]
            assert len(active) == 1
            assert len(deleted) == 1
            assert decrypt(active[0].app_secret) == _ANOTHER_SECRET


# ── update_bot：加密更新 ──────────────────────────────────────────


class TestUpdateBot:
    def test_update_app_secret_encrypts_new_value(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """update 传入新明文 app_secret，DB 中应更新为加密密文。"""
        bot_service.create_bot(
            bot_id="upd-1",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        bot_service.update_bot(bot_id="upd-1", app_secret=_ANOTHER_SECRET)

        with db_session_factory() as session:
            row = session.query(Bot).filter(Bot.bot_id == "upd-1").one()
            assert decrypt(row.app_secret) == _ANOTHER_SECRET
            assert is_encrypted(row.app_secret)

    def test_update_without_app_secret_keeps_existing(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """update 不传 app_secret 时，DB 中 app_secret 保持不变。"""
        bot_service.create_bot(
            bot_id="upd-2",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        original_cipher = (
            db_session_factory()
            .query(Bot)
            .filter(Bot.bot_id == "upd-2")
            .one()
            .app_secret
        )
        bot_service.update_bot(bot_id="upd-2", name="New Name")
        with db_session_factory() as session:
            row = session.query(Bot).filter(Bot.bot_id == "upd-2").one()
            assert row.app_secret == original_cipher
            assert row.name == "New Name"

    def test_update_deleted_bot_raises(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """更新已软删除的 Bot 应抛 ResourceNotFoundError。"""
        bot_service.create_bot(
            bot_id="upd-3",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        bot_service.delete_bot(bot_id="upd-3")
        with pytest.raises(ResourceNotFoundError):
            bot_service.update_bot(bot_id="upd-3", name="x")


# ── list_bots / list_active_bots：脱敏 vs 明文 ──────────────────


class TestList:
    def test_list_bots_masks_app_secret(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """list_bots 返回的 app_secret 应脱敏为 ***。"""
        _make_bot_row(
            db_session_factory,
            bot_id="list-1",
            app_secret_raw=encrypt(_PLAIN_SECRET),
        )
        result = bot_service.list_bots(page=1, page_size=10)
        assert result["total"] == 1
        assert result["items"][0]["app_secret"] == "***"

    def test_list_active_bots_returns_plaintext(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """list_active_bots 应返回解密后的明文 app_secret（供 Gateway 使用）。"""
        _make_bot_row(
            db_session_factory,
            bot_id="act-1",
            app_secret_raw=encrypt(_PLAIN_SECRET),
            status=1,
        )
        # 软删除的不应返回
        _make_bot_row(
            db_session_factory,
            bot_id="act-2",
            app_secret_raw=encrypt(_ANOTHER_SECRET),
            status=1,
            deleted=True,
        )
        # status != 1 的不应返回
        _make_bot_row(
            db_session_factory,
            bot_id="act-3",
            app_secret_raw=encrypt("disabled-secret"),
            status=0,
        )

        result = bot_service.list_active_bots()
        assert len(result) == 1
        assert result[0]["bot_id"] == "act-1"
        assert result[0]["app_secret"] == _PLAIN_SECRET

    def test_list_active_bots_legacy_plaintext_compat(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """存量明文 app_secret（无 enc:v1: 前缀）应原样返回，兼容过渡期。"""
        _make_bot_row(
            db_session_factory,
            bot_id="legacy-1",
            app_secret_raw=_PLAIN_SECRET,  # 无前缀明文
            status=1,
        )
        result = bot_service.list_active_bots()
        assert len(result) == 1
        assert result[0]["app_secret"] == _PLAIN_SECRET

    def test_list_bots_excludes_soft_deleted(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """list_bots 不返回软删除的记录。"""
        _make_bot_row(db_session_factory, bot_id="alive-1", app_secret_raw=encrypt("s1"))
        _make_bot_row(
            db_session_factory,
            bot_id="dead-1",
            app_secret_raw=encrypt("s2"),
            deleted=True,
        )
        result = bot_service.list_bots(page=1, page_size=10)
        bot_ids = [b["bot_id"] for b in result["items"]]
        assert "alive-1" in bot_ids
        assert "dead-1" not in bot_ids
        assert result["total"] == 1


# ── delete_bot：软删除 + 幂等性 ──────────────────────────────────


class TestDeleteBot:
    def test_delete_sets_deleted_at(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """delete 后 DB 中 deleted_at 应非空。"""
        bot_service.create_bot(
            bot_id="del-1",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        result = bot_service.delete_bot(bot_id="del-1")
        assert result == {"bot_id": "del-1", "deleted": True}

        with db_session_factory() as session:
            row = session.query(Bot).filter(Bot.bot_id == "del-1").one()
            assert row.deleted_at is not None

    def test_delete_twice_raises(
        self, bot_service: BotService, db_session_factory
    ) -> None:
        """二次删除已软删除的 Bot 应抛 ResourceNotFoundError。"""
        bot_service.create_bot(
            bot_id="del-2",
            name="Bot",
            platform="feishu",
            app_id="app-1",
            app_secret=_PLAIN_SECRET,
        )
        bot_service.delete_bot(bot_id="del-2")
        with pytest.raises(ResourceNotFoundError):
            bot_service.delete_bot(bot_id="del-2")


# ── 加密兼容性 ──────────────────────────────────────────────────


class TestCryptoCompat:
    def test_encrypt_then_decrypt_roundtrip(self) -> None:
        """encrypt 后 decrypt 应还原明文。"""
        cipher = encrypt(_PLAIN_SECRET)
        assert cipher.startswith(PREFIX)
        assert cipher != _PLAIN_SECRET
        assert decrypt(cipher) == _PLAIN_SECRET

    def test_encrypt_empty_string_passthrough(self) -> None:
        """空字符串原样返回，不加密。"""
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_decrypt_plaintext_passthrough(self) -> None:
        """无前缀的明文 decrypt 原样返回（兼容存量数据）。"""
        assert decrypt(_PLAIN_SECRET) == _PLAIN_SECRET
