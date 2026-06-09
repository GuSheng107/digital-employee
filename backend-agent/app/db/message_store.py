from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from app.db.core import connect_database
from app.db.user_store import list_user_display_names
from app.utils import utc_now


def list_unconverted_messages(
    database_path: Path,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, list[dict]]:
    with connect_database(database_path) as conn:
        base_query = """
            SELECT id, created_at, direction, chat_id, chat_name, sender_name,
                   content, msg_type, reply_source, convert_status
            FROM chat_messages
            WHERE convert_status = 'unconverted'
              AND msg_type NOT IN ('system', 'busy', 'context_summary')
        """
        conditions = []
        params = []
        
        if start_time is not None:
            conditions.append("created_at >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("created_at <= ?")
            params.append(end_time)
        
        if conditions:
            query = base_query + " AND " + " AND ".join(conditions) + " ORDER BY chat_id, created_at ASC"
            rows = conn.execute(query, params).fetchall()
        else:
            query = base_query + " ORDER BY chat_id, created_at ASC"
            rows = conn.execute(query).fetchall()
    result: dict[str, list[dict]] = {}
    for row in rows:
        msg = {
            "id": str(row["id"]),
            "created_at": str(row["created_at"]),
            "direction": str(row["direction"]),
            "chat_id": str(row["chat_id"]),
            "chat_name": str(row["chat_name"]),
            "sender_name": str(row["sender_name"]),
            "content": str(row["content"]),
            "msg_type": str(row["msg_type"]),
            "reply_source": str(row["reply_source"]) if row["reply_source"] else "",
            "convert_status": str(row["convert_status"]) if row["convert_status"] else "",
        }
        result.setdefault(msg["chat_id"], []).append(msg)
    return result


def mark_messages_converted(database_path: Path, message_ids: list[str]) -> None:
    if not message_ids:
        return
    now = utc_now()
    placeholders = ", ".join("?" for _ in message_ids)
    with connect_database(database_path) as conn:
        conn.execute(
            f"UPDATE chat_messages SET convert_status = 'converted', convert_at = ? WHERE id IN ({placeholders})",
            (now, *message_ids),
        )


def list_unconverted_messages_with_chat_info(
    database_path: Path,
    start_time: str | None = None,
    end_time: str | None = None,
) -> dict[str, list[dict]]:
    """
    获取未转换消息，并附带会话信息和用户显示名
    
    Returns:
        key 为 chat_id，value 为该会话的消息列表
        每个消息包含：原始消息信息 + chat_type + chat_display_name + sender_display_name
    """
    # 首先获取未转换消息（关联会话表获取 chat_type 和 display_name）
    with connect_database(database_path) as conn:
        base_query = """
            SELECT 
                m.id, m.created_at, m.direction, m.chat_id, m.chat_name, m.sender_id, m.sender_name,
                m.content, m.msg_type, m.reply_source, m.convert_status,
                COALESCE(c.chat_type, 'unknown') AS chat_type,
                COALESCE(NULLIF(c.display_name, ''), m.chat_name) AS chat_display_name
            FROM chat_messages AS m
            LEFT JOIN conversations AS c ON c.chat_id = m.chat_id
            WHERE m.convert_status = 'unconverted'
              AND m.msg_type NOT IN ('system', 'busy', 'context_summary')
        """
        conditions = []
        params = []
        
        if start_time is not None:
            conditions.append("m.created_at >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("m.created_at <= ?")
            params.append(end_time)
        
        if conditions:
            query = base_query + " AND " + " AND ".join(conditions) + " ORDER BY m.chat_id, m.created_at ASC"
            rows = conn.execute(query, params).fetchall()
        else:
            query = base_query + " ORDER BY m.chat_id, m.created_at ASC"
            rows = conn.execute(query).fetchall()

    # 收集所有 sender_id 用于批量获取显示名
    sender_ids = list({str(row["sender_id"] or "").strip() for row in rows if str(row["sender_id"] or "").strip()})
    
    # 批量获取用户显示名
    user_display_names = list_user_display_names(database_path, sender_ids) if sender_ids else {}

    # 构建结果
    result: dict[str, list[dict]] = {}
    for row in rows:
        # 确定发送者显示名（优先使用映射，否则使用 sender_name）
        sender_id = str(row["sender_id"] or "").strip()
        sender_display_name = user_display_names.get(sender_id, "")
        if not sender_display_name:
            sender_display_name = str(row["sender_name"] or "")
        
        # 构建消息对象
        msg = {
            "id": str(row["id"]),
            "created_at": str(row["created_at"]),
            "direction": str(row["direction"]),
            "chat_id": str(row["chat_id"]),
            "chat_name": str(row["chat_name"]),
            "sender_id": sender_id,
            "sender_name": str(row["sender_name"]),
            "content": str(row["content"]),
            "msg_type": str(row["msg_type"]),
            "reply_source": str(row["reply_source"]) if row["reply_source"] else "",
            "convert_status": str(row["convert_status"]) if row["convert_status"] else "",
            "chat_type": str(row["chat_type"]),
            "chat_display_name": str(row["chat_display_name"]),
            "sender_display_name": sender_display_name,
        }
        result.setdefault(msg["chat_id"], []).append(msg)
    
    return result


def organize_messages_into_qa_pairs(
    messages_by_chat: dict[str, list[dict]],
) -> dict[str, dict]:
    """
    将消息组织成统一的 pairs 结构，允许单侧缺失，便于前端补全。
    """
    result = {}
    
    for chat_id, messages in messages_by_chat.items():
        if not messages:
            continue
        
        chat_info = {
            "chat_name": messages[0]["chat_name"],
            "chat_display_name": messages[0]["chat_display_name"],
            "chat_type": messages[0]["chat_type"],
            "pairs": [],
        }
        
        chat_type = messages[0]["chat_type"]
        is_group = chat_type in ("group", "room")
        
        if is_group:
            _pair_group_messages(messages, chat_info)
        else:
            _pair_single_messages(messages, chat_info)
        
        result[chat_id] = chat_info
    
    return result


def _pair_single_messages(messages: list[dict], chat_info: dict) -> None:
    segments: list[dict] = []
    current_dir = None
    current_msgs: list[dict] = []

    def flush():
        if current_msgs:
            segments.append({"direction": current_dir, "messages": list(current_msgs)})

    for msg in messages:
        d = msg["direction"]
        if d == current_dir:
            current_msgs.append(msg)
        else:
            flush()
            current_dir = d
            current_msgs = [msg]
    flush()

    for i in range(0, len(segments) - 1, 2):
        user_seg = segments[i] if segments[i]["direction"] == "user" else None
        bot_seg = segments[i + 1] if segments[i + 1]["direction"] == "bot" else None

        if user_seg and bot_seg:
            chat_info["pairs"].append(_build_pair_from_segments(user_seg["messages"], bot_seg["messages"]))
        elif user_seg:
            for m in user_seg["messages"]:
                chat_info["pairs"].append(_build_pair(m, None))
        elif bot_seg:
            for m in bot_seg["messages"]:
                chat_info["pairs"].append(_build_pair(None, m))

    if len(segments) % 2 == 1:
        last = segments[-1]
        if last["direction"] == "user":
            for m in last["messages"]:
                chat_info["pairs"].append(_build_pair(m, None))
        else:
            for m in last["messages"]:
                chat_info["pairs"].append(_build_pair(None, m))


def _pair_group_messages(messages: list[dict], chat_info: dict) -> None:
    user_groups = defaultdict(list)
    for msg in messages:
        user_groups[msg["sender_id"]].append(msg)
    
    bot_messages = user_groups.pop("bot", []) + user_groups.pop("manual", [])
    bot_messages.sort(key=lambda m: m["created_at"])
    
    for sender_id, user_messages in user_groups.items():
        paired_user_ids = set()
        for i in range(len(user_messages)):
            if i in paired_user_ids:
                continue
            current_msg = user_messages[i]
            if current_msg["direction"] == "user":
                for bot_msg in bot_messages:
                    if bot_msg["created_at"] > current_msg["created_at"]:
                        chat_info["pairs"].append(_build_pair(current_msg, bot_msg))
                        paired_user_ids.add(i)
                        bot_messages.remove(bot_msg)
                        break
            if i not in paired_user_ids:
                chat_info["pairs"].append(_build_pair(current_msg, None))
    
    for bot_msg in bot_messages:
        chat_info["pairs"].append(_build_pair(None, bot_msg))


def _build_pair(question_msg: dict | None, answer_msg: dict | None) -> dict:
    question_time = str(question_msg.get("created_at") or "") if question_msg else ""
    answer_time = str(answer_msg.get("created_at") or "") if answer_msg else ""
    question_id = str(question_msg.get("id") or "") if question_msg else ""
    answer_id = str(answer_msg.get("id") or "") if answer_msg else ""
    question_msg_type = str(question_msg.get("msg_type") or "") if question_msg else ""
    answer_msg_type = str(answer_msg.get("msg_type") or "") if answer_msg else ""
    answer_reply_source = str(answer_msg.get("reply_source") or "") if answer_msg else ""
    question_sender = ""
    answer_sender = ""

    if question_msg:
        question_sender = str(question_msg.get("sender_display_name") or question_msg.get("sender_name") or "用户")
    if answer_msg:
        answer_sender = str(answer_msg.get("sender_display_name") or answer_msg.get("sender_name") or "")
    if not answer_sender:
        answer_sender = "助理"

    return {
        "pair_id": f"pair-{question_id or 'none'}-{answer_id or 'none'}",
        "question": str(question_msg.get("content") or "") if question_msg else "",
        "answer": str(answer_msg.get("content") or "") if answer_msg else "",
        "question_message_ids": [question_id] if question_id else [],
        "answer_message_ids": [answer_id] if answer_id else [],
        "question_msg_type": question_msg_type,
        "answer_msg_type": answer_msg_type,
        "answer_reply_source": answer_reply_source,
        "question_time": question_time,
        "answer_time": answer_time,
        "question_sender": question_sender,
        "answer_sender": answer_sender,
        "question_edited": False,
        "answer_edited": False,
        "direction": str(answer_reply_source or "bot") if answer_msg else "",
        "time": answer_time or question_time or "",
    }


def _build_pair_from_segments(question_msgs: list[dict], answer_msgs: list[dict]) -> dict:
    question_parts = [str(m.get("content") or "") for m in question_msgs if str(m.get("content") or "").strip()]
    answer_parts = [str(m.get("content") or "") for m in answer_msgs if str(m.get("content") or "").strip()]
    question_ids = [str(m.get("id") or "") for m in question_msgs]
    answer_ids = [str(m.get("id") or "") for m in answer_msgs]
    first_q = question_msgs[0] if question_msgs else None
    last_a = answer_msgs[-1] if answer_msgs else None
    question_time = str(first_q.get("created_at") or "") if first_q else ""
    answer_time = str(last_a.get("created_at") or "") if last_a else ""
    question_msg_type = str(first_q.get("msg_type") or "") if first_q else ""
    answer_msg_type = str(last_a.get("msg_type") or "") if last_a else ""
    answer_reply_source = str(last_a.get("reply_source") or "") if last_a else ""
    question_sender = str(first_q.get("sender_display_name") or first_q.get("sender_name") or "用户") if first_q else "用户"
    answer_sender = str(last_a.get("sender_display_name") or last_a.get("sender_name") or "助理") if last_a else "助理"

    return {
        "pair_id": f"pair-{question_ids[0] or 'none'}-{answer_ids[-1] or 'none'}",
        "question": "\n".join(question_parts),
        "answer": "\n".join(answer_parts),
        "question_message_ids": question_ids,
        "answer_message_ids": answer_ids,
        "question_msg_type": question_msg_type,
        "answer_msg_type": answer_msg_type,
        "answer_reply_source": answer_reply_source,
        "question_time": question_time,
        "answer_time": answer_time,
        "question_sender": question_sender,
        "answer_sender": answer_sender,
        "question_edited": False,
        "answer_edited": False,
        "direction": str(answer_reply_source or "bot") if last_a else "",
        "time": answer_time or question_time or "",
    }
