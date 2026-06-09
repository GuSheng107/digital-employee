from __future__ import annotations

from pathlib import Path
from typing import Any



from app.db.core import connect_database
from app.db.user_store import list_user_display_names


def _empty_bot_usage(label: str = "") -> dict[str, Any]:
    return {
        "item_label": label,
        "mounted_bot_count": 0,
        "mounted_bot_names": [],
        "mounted_bot_keys": [],
        "platform_agent_task_count": 0,
        "platform_agent_task_names": [],
        "is_platform_agent": False,
    }


def _collect_agent_bot_usage(database_path: Path, provider_keys: list[str]) -> dict[str, dict[str, Any]]:
    clean_keys = [str(item or "").strip() for item in provider_keys if str(item or "").strip()]
    if not clean_keys:
        return {}
    placeholders = ", ".join("?" for _ in clean_keys)
    result = {key: _empty_bot_usage() for key in clean_keys}

    with connect_database(database_path) as conn:
        # 获取当前平台Agent配置
        platform_agent_key = ""
        try:
            from app.db.settings_store import get_platform_settings
            platform_settings = get_platform_settings()
            platform_agent_key = str(platform_settings.get("platform_agent_provider", "")).strip()
        except:
            pass

        # 获取Agent标签信息
        agent_rows = conn.execute(
            f"""
            SELECT provider_key, label, provider_name
            FROM agent_provider_config
            WHERE provider_key IN ({placeholders})
            """,
            clean_keys,
        ).fetchall()
        agent_labels = {}
        for agent_row in agent_rows:
            key = str(agent_row["provider_key"]).strip()
            alabel = str(agent_row["label"]).strip() if agent_row["label"] else ""
            aname = str(agent_row["provider_name"]).strip() if agent_row["provider_name"] else ""
            label = alabel or aname or key
            agent_labels[key] = label
            if key in result:
                result[key]["item_label"] = label
                result[key]["is_platform_agent"] = (key == platform_agent_key)

        # 获取Bot挂载信息
        rows = conn.execute(
            f"""
            SELECT bc.agent_provider AS ref_id, bc.bot_key, bc.name AS bot_name
            FROM bot_config bc
            WHERE trim(bc.agent_provider) != '' AND bc.agent_provider IN ({placeholders})
              AND bc.deleted_at = ''
            ORDER BY bc.name
            """,
            clean_keys,
        ).fetchall()

        for row in rows:
            ref_id = str(row["ref_id"] or "").strip()
            if not ref_id:
                continue
            item = result.setdefault(ref_id, _empty_bot_usage(agent_labels.get(ref_id, ref_id)))
            bot_key = str(row["bot_key"] or "").strip()
            bot_name = str(row["bot_name"] or bot_key).strip()
            if bot_key and bot_key not in item["mounted_bot_keys"]:
                item["mounted_bot_keys"].append(bot_key)
                item["mounted_bot_names"].append(bot_name)
                item["mounted_bot_count"] += 1

        # 如果有平台Agent，获取绑定的任务信息
        if platform_agent_key and platform_agent_key in clean_keys:
            task_rows = conn.execute(
                """
                SELECT task_key, name, handler_name, is_enabled, run_state
                FROM scheduled_tasks
                WHERE executor_kind = 'platform_agent'
                  AND task_scope = 'system'
                  AND handler_name IN (
                    'memory_update',
                    'self_review_chat_memory',
                    'self_review_document_memory'
                  )
                ORDER BY name
                """
            ).fetchall()
            for task_row in task_rows:
                task_name = str(task_row["name"] or "").strip()
                task_handler = str(task_row["handler_name"] or "").strip()
                is_enabled = bool(task_row["is_enabled"])
                run_state = str(task_row["run_state"] or "").strip()
                task_key = str(task_row["task_key"] or "").strip()
                if task_name:
                    # 构建更友好的任务显示
                    display_name = task_name
                    if is_enabled:
                        display_name += " (已启用)"
                    else:
                        display_name += " (已停用)"
                    if run_state in ["running", "manual_pending"]:
                        display_name += " *"
                    result[platform_agent_key]["platform_agent_task_names"].append(display_name)
                    result[platform_agent_key]["platform_agent_task_count"] += 1

    return result


def _collect_skill_bot_usage(database_path: Path, skill_names: list[str]) -> dict[str, dict[str, Any]]:
    clean_names = [str(item or "").strip() for item in skill_names if str(item or "").strip()]
    if not clean_names:
        return {}
    placeholders = ", ".join("?" for _ in clean_names)
    result = {name: _empty_bot_usage() for name in clean_names}

    with connect_database(database_path) as conn:
        skill_rows = conn.execute(
            f"""
            SELECT skill_name, display_name
            FROM skill_config
            WHERE skill_name IN ({placeholders})
            """,
            clean_names,
        ).fetchall()
        skill_labels = {}
        for skill_row in skill_rows:
            sname = str(skill_row["skill_name"]).strip()
            sdisplay = str(skill_row["display_name"]).strip() if skill_row["display_name"] else ""
            label = sdisplay or sname
            skill_labels[sname] = label
            if sname in result:
                result[sname]["item_label"] = label

        rows = conn.execute(
            f"""
            SELECT bm.skill_name AS ref_id, bc.bot_key, bc.name AS bot_name
            FROM bot_skill_mapping bm
            JOIN bot_config bc ON bc.bot_key = bm.bot_key AND bc.deleted_at = ''
            WHERE bm.skill_name IN ({placeholders})
            ORDER BY bc.name
            """,
            clean_names,
        ).fetchall()
    for row in rows:
        ref_id = str(row["ref_id"] or "").strip()
        if not ref_id:
            continue
        item = result.setdefault(ref_id, _empty_bot_usage(skill_labels.get(ref_id, ref_id)))
        bot_key = str(row["bot_key"] or "").strip()
        bot_name = str(row["bot_name"] or bot_key).strip()
        if bot_key and bot_key not in item["mounted_bot_keys"]:
            item["mounted_bot_keys"].append(bot_key)
            item["mounted_bot_names"].append(bot_name)
            item["mounted_bot_count"] += 1
    return result


def _collect_mcp_bot_usage(database_path: Path, server_ids: list[str]) -> dict[str, dict[str, Any]]:
    clean_ids = [str(item or "").strip() for item in server_ids if str(item or "").strip()]
    if not clean_ids:
        return {}
    placeholders = ", ".join("?" for _ in clean_ids)
    result = {server_id: _empty_bot_usage() for server_id in clean_ids}

    with connect_database(database_path) as conn:
        mcp_rows = conn.execute(
            f"""
            SELECT server_id, name
            FROM mcp_server_config
            WHERE server_id IN ({placeholders})
            """,
            clean_ids,
        ).fetchall()
        mcp_labels = {}
        for mcp_row in mcp_rows:
            sid = str(mcp_row["server_id"]).strip()
            sname = str(mcp_row["name"]).strip() if mcp_row["name"] else ""
            label = sname or sid
            mcp_labels[sid] = label
            if sid in result:
                result[sid]["item_label"] = label

        rows = conn.execute(
            f"""
            SELECT bm.server_id AS ref_id, bc.bot_key, bc.name AS bot_name
            FROM bot_mcp_mapping bm
            JOIN bot_config bc ON bc.bot_key = bm.bot_key AND bc.deleted_at = ''
            WHERE bm.server_id IN ({placeholders})
            ORDER BY bc.name
            """,
            clean_ids,
        ).fetchall()
    for row in rows:
        ref_id = str(row["ref_id"] or "").strip()
        if not ref_id:
            continue
        item = result.setdefault(ref_id, _empty_bot_usage(mcp_labels.get(ref_id, ref_id)))
        bot_key = str(row["bot_key"] or "").strip()
        bot_name = str(row["bot_name"] or bot_key).strip()
        if bot_key and bot_key not in item["mounted_bot_keys"]:
            item["mounted_bot_keys"].append(bot_key)
            item["mounted_bot_names"].append(bot_name)
            item["mounted_bot_count"] += 1
    return result


def _enrich_bot_bound_item(item: dict[str, Any] | None, usage: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None
    result = dict(item)
    usage_data = usage or _empty_bot_usage()
    if not usage_data.get("item_label"):
        usage_data["item_label"] = str(
            result.get("label")
            or result.get("display_name")
            or result.get("name")
            or result.get("provider_name")
            or result.get("server_id")
            or result.get("provider_key")
            or ""
        ).strip()
    result["is_bound_to_bot"] = bool(usage_data["mounted_bot_count"])
    result["mounted_bot_count"] = int(usage_data["mounted_bot_count"])
    result["mounted_bot_names"] = list(usage_data["mounted_bot_names"])
    result["mounted_bot_keys"] = list(usage_data["mounted_bot_keys"])
    result["is_platform_agent"] = bool(usage_data.get("is_platform_agent", False))
    result["platform_agent_task_count"] = int(usage_data.get("platform_agent_task_count", 0))
    result["platform_agent_task_names"] = list(usage_data.get("platform_agent_task_names", []))
    return result


def _bot_api_view(
    bot: dict[str, Any] | None,
    *,
    mapping_counts: dict[str, dict[str, int]] | None = None,
    unread_totals: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    if bot is None:
        return None
    item = dict(bot)
    item["is_bound"] = bool(str(item.get("bound_chat_id") or "").strip())
    item.pop("bound_chat_id", None)
    item.pop("bound_user_id", None)
    item["bot_deleted"] = bool(str(item.get("deleted_at") or "").strip())
    if mapping_counts and item.get("bot_key") in mapping_counts:
        counts = mapping_counts[item["bot_key"]]
        item["enabled_skill_count"] = counts.get("enabled_skill_count", 0)
        item["enabled_mcp_count"] = counts.get("enabled_mcp_count", 0)
    else:
        item["enabled_skill_count"] = item.get("enabled_skill_count", 0)
        item["enabled_mcp_count"] = item.get("enabled_mcp_count", 0)
    item["unread_total"] = (unread_totals or {}).get(item.get("bot_key", ""), 0)
    return item


def _group_chat_messages(
    messages: list[dict[str, Any]],
    *,
    conversations: list[dict[str, Any]],
    database_path: Path,
) -> list[dict[str, Any]]:
    from app.context_store import batch_get_context_usage

    all_bot_keys = set()
    user_ids: set[str] = set()
    for conversation in conversations:
        raw_bot_key = str(conversation.get("bot_key") or "")
        if raw_bot_key:
            all_bot_keys.add(raw_bot_key)
        sender_id = str(conversation.get("sender_id") or "").strip()
        if sender_id and sender_id != "unknown":
            user_ids.add(sender_id)
    for message in messages:
        msg_bot_key = str(message.get("bot_key") or "")
        if msg_bot_key:
            all_bot_keys.add(msg_bot_key)
        sender_id = str(message.get("sender_id") or "").strip()
        if sender_id and sender_id != "unknown":
            user_ids.add(sender_id)

    deleted_bot_keys: set[str] = set()
    if all_bot_keys:
        with connect_database(database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT bot_key FROM bot_config
                WHERE bot_key IN ({','.join('?' for _ in all_bot_keys)})
                  AND deleted_at != ''
                """,
                list(all_bot_keys),
            ).fetchall()
            deleted_bot_keys = {str(row["bot_key"]) for row in rows}

    user_display_names = list_user_display_names(database_path, list(user_ids))

    groups: dict[str, dict[str, Any]] = {}
    for conversation in conversations:
        chat_id = str(conversation.get("chat_id") or "unknown")
        raw_bot_key = str(conversation.get("bot_key") or "")
        sender_id = str(conversation.get("sender_id") or "")
        custom_sender_display_name = user_display_names.get(sender_id, "")
        chat_type = str(conversation.get("chat_type") or "unknown")
        conversation_kind = str(conversation.get("conversation_kind") or "external")
        
        # 用户类型的会话，如果没有自定义 display_name，优先使用用户映射名
        display_name = str(conversation.get("display_name") or "")
        if not display_name and conversation_kind != "me" and chat_type not in ("group", "room") and custom_sender_display_name:
            display_name = custom_sender_display_name
        
        groups[chat_id] = {
            "chat_id": chat_id,
            "chat_name": str(conversation.get("chat_name") or chat_id),
            "display_name": display_name,
            "created_at": str(conversation.get("created_at") or ""),
            "updated_at": str(conversation.get("updated_at") or ""),
            "chat_type": chat_type,
            "bot_key": raw_bot_key,
            "bot_deleted": raw_bot_key in deleted_bot_keys,
            "external_chat_id": str(conversation.get("external_chat_id") or chat_id),
            "conversation_kind": conversation_kind,
            "pinned": bool(conversation.get("pinned")),
            "pin_rank": int(conversation.get("pin_rank") or 0),
            "unread_count": int(conversation.get("unread_count") or 0),
            "reply_status": str(conversation.get("reply_status") or "replied"),
            "reply_mode": str(conversation.get("reply_mode") or "manual"),
            "conversation_status": str(conversation.get("conversation_status") or "active"),
            "last_send_error": str(conversation.get("last_send_error") or ""),
            "context": {},
            "sender_id": sender_id,
            "sender_name": str(conversation.get("sender_name") or "未知用户"),
            "sender_custom_display_name": custom_sender_display_name,
            "sender_display_name": custom_sender_display_name or str(conversation.get("sender_name") or "未知用户"),
            "last_message": "",
            "last_at": str(conversation.get("last_message_at") or conversation.get("updated_at") or ""),
            "messages": [],
        }
    for message in messages:
        chat_id = str(message.get("chat_id") or "unknown")
        msg_bot_key = str(message.get("bot_key") or "")
        sender_id = str(message.get("sender_id") or "")
        custom_sender_display_name = user_display_names.get(sender_id, "")
        message["sender_custom_display_name"] = custom_sender_display_name
        message["sender_display_name"] = custom_sender_display_name or str(message.get("sender_name") or "未知用户")
        group = groups.setdefault(
            chat_id,
            {
                "chat_id": chat_id,
                "chat_name": str(message.get("chat_name") or chat_id),
                "display_name": str(message.get("display_name") or ""),
                "created_at": str(message.get("created_at") or ""),
                "updated_at": str(message.get("created_at") or ""),
                "chat_type": str(message.get("chat_type") or "unknown"),
                "bot_key": msg_bot_key,
                "bot_deleted": msg_bot_key in deleted_bot_keys,
                "external_chat_id": str(message.get("external_chat_id") or chat_id),
                "conversation_kind": str(message.get("conversation_kind") or "external"),
                "pinned": bool(message.get("pinned")),
                "pin_rank": int(message.get("pin_rank") or 0),
                "unread_count": int(message.get("unread_count") or 0),
                "reply_status": str(message.get("reply_status") or "replied"),
                "reply_mode": str(message.get("reply_mode") or "manual"),
                "last_send_error": "",
                "context": {},
                "sender_id": sender_id,
                "sender_name": str(message.get("sender_name") or "未知用户"),
                "sender_custom_display_name": custom_sender_display_name,
                "sender_display_name": custom_sender_display_name or str(message.get("sender_name") or "未知用户"),
                "last_message": "",
                "last_at": "",
                "messages": [],
            },
        )
        group["last_message"] = str(message.get("content") or "")
        group["last_at"] = str(message.get("created_at") or "")
        group["messages"].append(message)

    chat_ids = list(groups.keys())
    try:
        context_map = batch_get_context_usage(
            database_path=database_path,
            chat_ids=chat_ids,
            sender_ids_by_chat_id={
                cid: str(group.get("sender_id") or "")
                for cid, group in groups.items()
            },
        )
        for cid, ctx in context_map.items():
            if cid in groups:
                groups[cid]["context"] = ctx
    except Exception:
        pass

    try:
        from app.db.feedback_store import batch_get_feedbacks_by_chat_ids
        feedback_map = batch_get_feedbacks_by_chat_ids(database_path, chat_ids)
        for cid, feedbacks in feedback_map.items():
            if cid not in groups:
                continue
            group = groups[cid]
            results = set(str(fb.get("result") or "").strip().lower() for fb in feedbacks)
            has_useful = "useful" in results
            has_useless = "useless" in results
            if has_useful and has_useless:
                group["feedback_summary"] = "mixed"
            elif has_useless:
                group["feedback_summary"] = "useless"
            elif has_useful:
                group["feedback_summary"] = "useful"
            else:
                group["feedback_summary"] = ""
            for msg in group.get("messages", []):
                if str(msg.get("direction") or "") == "user":
                    continue
                msg_created = str(msg.get("created_at") or "")
                msg_feedbacks: list[dict[str, Any]] = []
                for fb in feedbacks:
                    fb_created = str(fb.get("created_at") or "")
                    if fb_created >= msg_created:
                        msg_feedbacks.append(fb)
                if not msg_feedbacks:
                    continue
                fb_results = set(str(fb.get("result") or "").strip().lower() for fb in msg_feedbacks)
                fb_has_useful = "useful" in fb_results
                fb_has_useless = "useless" in fb_results
                if fb_has_useful and fb_has_useless:
                    msg_status = "mixed"
                elif fb_has_useless:
                    msg_status = "useless"
                elif fb_has_useful:
                    msg_status = "useful"
                else:
                    msg_status = ""
                useless_reasons = [str(fb.get("reason") or "").strip() for fb in msg_feedbacks if str(fb.get("result") or "").strip().lower() == "useless" and str(fb.get("reason") or "").strip()]
                primary = msg_feedbacks[0]
                msg["feedback"] = {
                    "id": str(primary.get("id") or ""),
                    "result": msg_status,
                    "reason": "；".join(useless_reasons) if useless_reasons else str(primary.get("reason") or ""),
                    "created_at": str(primary.get("created_at") or ""),
                    "count": len(msg_feedbacks),
                    "all_results": sorted(fb_results),
                }
    except Exception:
        pass

    return sorted(
        groups.values(),
        key=lambda item: (
            bool(item.get("pinned")),
            int(item.get("pin_rank") or 0),
            str(item.get("last_at") or ""),
        ),
        reverse=True,
    )
