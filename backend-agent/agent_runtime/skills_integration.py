
from __future__ import annotations

"""Skills 系统集成模块，通过子进程执行与记忆系统（memory-reader、memory-creator）和通知系统（notify-me）的交互。"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from app.llm_usage import extract_token_usage, resolve_token_usage
from app.logger import get_logger

logger = get_logger("agent_runtime.skills_integration")

# ─── LLM 查询扩展 ───

_QUERY_EXPANSION_TIMEOUT_SECONDS = 15
_QUERY_EXPANSION_MAX_TERMS = 6

_QUERY_EXPANSION_PROMPT = """只做记忆检索关键词扩展。快速输出一行，禁止解释、推理、编号和换行。
格式：词1|词2|词3
规则：最多6个；优先实体、别名、产品、功能、故障词；不要重复原查询已有完整词；不要单字和泛词。
例1 Q: 这家公司主要做啥
A: 主营业务|经营范围|公司简介|产品体系
例2 Q: 店+有哪些产品
A: 产品体系|智能中台|智慧门店|会员私域|SaaS ERP|门店POS
例3 Q: 聚水潭推送商品类目不存在
A: 商品推送|类目不存在|规格模板|授权管理|聚水潭类目|店家类目
Q: {query}
A:"""


async def expand_query_with_llm(
    user_query: str,
    settings: Any = None,
    database_path: Path | None = None,
    trace_id: str = "",
) -> list[str]:
    """使用 LLM 对用户查询进行语义扩展，返回扩展词列表。"""
    try:
        from langchain_core.messages import HumanMessage

        llm = _build_llm_for_expansion(settings, database_path)
        if llm is None:
            return []

        prompt = _QUERY_EXPANSION_PROMPT.format(query=user_query)
        model_info = _get_llm_model_info(settings, database_path)

        _log_query_expansion(
            database_path=database_path,
            trace_id=trace_id,
            phase="prompt",
            user_query=user_query,
            prompt=prompt,
            model_info=model_info,
        )

        start = time.monotonic()
        response = await asyncio.wait_for(
            asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)]),
            timeout=_QUERY_EXPANSION_TIMEOUT_SECONDS,
        )
        elapsed = round(time.monotonic() - start, 2)
        text = str(response.content or "").strip()

        # 解析模型输出，兼容偶发的标签、逗号或换行。
        text = re.sub(r"^\s*扩展词\s*[:：]\s*", "", text)
        query_lower = user_query.lower()
        terms: list[str] = []
        seen: set[str] = set()
        for part in re.split(r"[|｜,，\r\n]+", text):
            term = part.strip(" \t-:：;；")
            if not term or len(term) <= 1:
                continue
            if term.lower() in query_lower:
                continue
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
            if len(terms) >= _QUERY_EXPANSION_MAX_TERMS:
                break

        tokens, token_usage_source = resolve_token_usage(response, prompt)
        _log_query_expansion(
            database_path=database_path,
            trace_id=trace_id,
            phase="response",
            user_query=user_query,
            raw_output=text,
            terms=terms,
            tokens=tokens,
            token_usage_source=token_usage_source,
            elapsed_seconds=elapsed,
        )
        _record_expansion_token_usage(
            database_path=database_path,
            settings=settings,
            tokens=tokens,
            trace_id=trace_id,
        )

        if terms:
            logger.info(f"LLM 查询扩展: '{user_query}' → {terms} ({elapsed}s)")

        return terms

    except asyncio.TimeoutError:
        _log_query_expansion(
            database_path=database_path,
            trace_id=trace_id,
            phase="timeout",
            user_query=user_query,
        )
        logger.warning("LLM 查询扩展超时，跳过")
        return []
    except Exception as e:
        _log_query_expansion(
            database_path=database_path,
            trace_id=trace_id,
            phase="error",
            user_query=user_query,
            error=str(e),
        )
        logger.warning(f"LLM 查询扩展失败，跳过: {e}")
        return []


def _log_query_expansion(
    *,
    database_path: Path | None,
    trace_id: str,
    phase: str,
    user_query: str = "",
    prompt: str = "",
    model_info: dict | None = None,
    raw_output: str = "",
    terms: list[str] | None = None,
    tokens: dict | None = None,
    token_usage_source: str = "",
    elapsed_seconds: float = 0,
    error: str = "",
) -> None:
    """将查询扩展的各阶段日志写入 project_logs。"""
    if not trace_id or not database_path:
        return
    try:
        from app.db.log_store import insert_project_log

        source = f"query_expansion.{phase}"

        if phase == "prompt":
            message = "LLM 查询扩展请求"
            detail_parts = [
                f"user_query={user_query}",
                f"provider_key={model_info.get('provider_key', '<unknown>') if model_info else '<unknown>'}",
                f"model={model_info.get('model', '<unknown>') if model_info else '<unknown>'}",
                f"provider_type={model_info.get('provider_type', '<unknown>') if model_info else '<unknown>'}",
                f"timeout={_QUERY_EXPANSION_TIMEOUT_SECONDS}s",
                "temperature=0.0",
                "max_retries=0",
                "thinking_mode=disabled",
                "reasoning_trace=not_requested",
                "",
                "=" * 80,
                "【完整 Prompt】",
                "=" * 80,
                prompt,
            ]
        elif phase == "response":
            message = "LLM 查询扩展响应"
            detail_parts = [
                f"user_query={user_query}",
                f"elapsed={elapsed_seconds}s",
                f"input_tokens={tokens.get('input_tokens', 0) if tokens else 0}",
                f"output_tokens={tokens.get('output_tokens', 0) if tokens else 0}",
                f"total_tokens={tokens.get('total_tokens', 0) if tokens else 0}",
                f"token_usage_source={token_usage_source or '<unknown>'}",
                f"terms_count={len(terms or [])}",
                "",
                "=" * 80,
                "【模型原始输出】",
                "=" * 80,
                raw_output or "<empty>",
                "",
                "=" * 80,
                "【解析结果】",
                "=" * 80,
                "|".join(terms) if terms else "<empty>",
            ]
        elif phase == "timeout":
            message = "LLM 查询扩展超时"
            detail_parts = [
                f"user_query={user_query}",
                f"timeout={_QUERY_EXPANSION_TIMEOUT_SECONDS}s",
                "thinking_mode=disabled",
            ]
        elif phase == "error":
            message = "LLM 查询扩展失败"
            detail_parts = [
                f"user_query={user_query}",
                f"error={error}",
            ]
        else:
            return

        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="WARNING" if phase in ("timeout", "error") else "INFO",
            category="ai",
            source=source,
            message=message,
            detail="\n".join(detail_parts),
        )
    except Exception:
        logger.debug("Failed to log query expansion event", exc_info=True)


def _extract_tokens_from_response(response: Any) -> dict[str, int]:
    """从 LLM 响应中提取 token 使用量。"""
    return extract_token_usage(response)


def _get_llm_model_info(settings: Any, database_path: Path | None = None) -> dict[str, str]:
    """获取当前 LLM 模型信息。"""
    try:
        effective_settings = settings
        if effective_settings is None and database_path:
            from app.db.settings_store import load_settings_from_database
            effective_settings = load_settings_from_database(database_path)
        if effective_settings is None:
            return {}
        provider = effective_settings.agent.providers.get(effective_settings.agent.provider)
        if provider is None:
            return {}
        return {
            "provider_key": effective_settings.agent.provider,
            "provider_type": provider.type,
            "model": provider.model,
        }
    except Exception:
        return {}


def _record_expansion_token_usage(
    *,
    database_path: Path | None,
    settings: Any,
    tokens: dict[str, int],
    trace_id: str,
) -> None:
    """记录查询扩展的 token 消耗。"""
    if not database_path or tokens.get("total_tokens", 0) <= 0:
        return
    try:
        from app.db.token_usage_store import record_token_usage

        model_info = _get_llm_model_info(settings, database_path)
        record_token_usage(
            database_path,
            provider_key=model_info.get("provider_key", ""),
            provider_type=model_info.get("provider_type", ""),
            model=model_info.get("model", ""),
            call_type="query_expansion",
            trace_id=trace_id,
            input_tokens=tokens.get("input_tokens", 0),
            output_tokens=tokens.get("output_tokens", 0),
            total_tokens=tokens.get("total_tokens", 0),
        )
    except Exception:
        logger.debug("Failed to record query expansion token usage", exc_info=True)


def _configure_query_expansion_provider(provider: Any) -> None:
    """隔离配置查询扩展 LLM，不影响普通 Agent 的模型参数。"""
    provider.temperature = 0.0
    provider.max_retries = 0
    provider.timeout_seconds = min(
        max(int(provider.timeout_seconds or _QUERY_EXPANSION_TIMEOUT_SECONDS), 1),
        _QUERY_EXPANSION_TIMEOUT_SECONDS,
    )
    provider_type = str(getattr(provider, "type", "") or "").strip().lower()
    model_kwargs = dict(getattr(provider, "model_kwargs", None) or {})
    model_kwargs.pop("reasoning_effort", None)
    model_kwargs.pop("enable_thinking", None)
    if provider_type == "dashscope":
        model_kwargs["enable_thinking"] = False
    elif provider_type in {"openai", "openai_compatible"}:
        model_kwargs["reasoning_effort"] = ""
    provider.model_kwargs = model_kwargs


def _disable_expansion_thinking(llm: Any, provider_type: str = "") -> None:
    """在已构建的 LLM 实例上注入关闭思考的参数。

    根据提供商类型选择不同的注入方式：
    - dashscope: 通过 model_kwargs 传递 enable_thinking=False
    - openai_compatible: 通过 extra_body 传递 enable_thinking=False
    - 其他提供商只清理思考参数，不注入未知字段
    """
    try:
        pt = provider_type.strip().lower()

        if pt == "dashscope":
            # ChatTongyi 通过 model_kwargs 传递
            model_kwargs = getattr(llm, "model_kwargs", None)
            if model_kwargs is None:
                llm.model_kwargs = {}
                model_kwargs = llm.model_kwargs
            model_kwargs["enable_thinking"] = False
        elif pt == "openai_compatible":
            extra_body = dict(getattr(llm, "extra_body", None) or {})
            extra_body["enable_thinking"] = False
            llm.extra_body = extra_body
    except Exception:
        logger.debug("Failed to disable thinking on expansion LLM", exc_info=True)


_MEMORY_BUDGET_TIERS = [
    (500, 500),      # 估算 < 400 → 500
    (3000, 3000),    # 估算 < 2500 → 3000
    (6000, 6000),    # 估算 < 5000 → 6000
    (10000, 10000),  # 估算 >= 5000 → 10000
]


def _pick_budget_tier(estimated_tokens: int) -> int:
    """根据估算 token 数选择对应的 budget 档位。"""
    thresholds = [400, 2500, 5000]
    for threshold, tier in zip(thresholds, _MEMORY_BUDGET_TIERS):
        if estimated_tokens < threshold:
            return tier[0]
    return _MEMORY_BUDGET_TIERS[-1][0]


def _resolve_memory_token_budget(memory_dir: Path) -> tuple[int, int]:
    """根据记忆目录的内容量估算 token 需求，返回 (base_budget, expanded_budget)。

    base_budget: 仅统计核心记忆（排除 documents/），按档位选择。
    expanded_budget: 综合核心+文档记忆估算，按档位选择；若与 base 相同则不扩展。
    档位: 500 / 3000 / 6000 / 10000。
    memory-reader 先用 base_budget 选取，若文档命中且有 item 被截断则扩展到 expanded_budget。
    """
    fallback = 3000
    try:
        core_chars = 0
        doc_chars = 0
        if memory_dir.exists():
            for json_file in memory_dir.rglob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    items = data.get("items", []) if isinstance(data, dict) else []
                    # 判断是否属于 documents 子目录
                    is_doc = "documents" in json_file.parts
                    for item in items:
                        if isinstance(item, dict):
                            content = str(item.get("content", "") or "")
                            if is_doc:
                                doc_chars += len(content)
                            else:
                                core_chars += len(content)
                except Exception:
                    continue

        core_estimated = int(core_chars * 1.2)
        doc_estimated = int(doc_chars * 1.2)
        base_budget = _pick_budget_tier(core_estimated)
        expanded_budget = _pick_budget_tier(core_estimated + doc_estimated)
        logger.info(
            f"记忆 token budget 动态选择: "
            f"核心估算={core_estimated}, 文档估算={doc_estimated}, "
            f"base={base_budget}, expanded={expanded_budget}"
        )
        return base_budget, expanded_budget
    except Exception:
        logger.debug("Failed to resolve memory token budget", exc_info=True)
        return fallback, fallback


def _build_llm_for_expansion(settings: Any, database_path: Path | None = None) -> Any | None:
    """构建用于查询扩展的轻量 LLM 实例，强制关闭思考模式以降低延迟。"""
    try:
        import copy

        from agent_runtime.models import build_chat_model

        effective_settings = settings
        if effective_settings is None and database_path:
            from app.db.settings_store import load_settings_from_database

            effective_settings = load_settings_from_database(database_path)
        if effective_settings is None:
            return None

        expansion_settings = copy.deepcopy(effective_settings)
        provider = expansion_settings.agent.providers.get(expansion_settings.agent.provider)
        provider_type = ""
        if provider is not None:
            _configure_query_expansion_provider(provider)
            provider_type = str(getattr(provider, "type", "") or "")

        llm = build_chat_model(expansion_settings, no_retry=True)
        _disable_expansion_thinking(llm, provider_type=provider_type)
        return llm
    except Exception as e:
        logger.warning(f"构建查询扩展 LLM 失败: {e}")
        return None


def _is_query_expansion_enabled(project_root: Path) -> bool:
    """检查 LLM 查询扩展是否启用。"""
    try:
        from app.yaml_config import get_yaml_config
        yaml_cfg = get_yaml_config()
        return bool(yaml_cfg.get("memory.query_expansion.enabled", False))
    except Exception:
        return False


def _parse_json_result(stdout: str) -> dict[str, Any] | None:
    text = str(stdout or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _error_from_subprocess_output(stdout: str, stderr: str, fallback: str = "unknown error") -> str:
    payload = _parse_json_result(stdout)
    if payload:
        message = str(payload.get("error") or payload.get("message") or "").strip()
        if message:
            return message
    stderr_text = str(stderr or "").strip()
    if stderr_text:
        return stderr_text
    stdout_text = str(stdout or "").strip()
    if stdout_text:
        return stdout_text[:2000]
    return fallback


def _get_project_root(project_root: Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root)
    candidate = Path(__file__).resolve()
    for parent in candidate.parents:
        if (parent / ".skills").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def _parse_split_pattern(filename: str) -> tuple[str, int] | None:
    dot_pos = filename.rfind(".")
    stem = filename if dot_pos == -1 else filename[:dot_pos]
    underscore_pos = stem.rfind("_")
    if underscore_pos == -1:
        return None
    num_part = stem[underscore_pos + 1:]
    if not num_part.isdigit():
        return None
    index = int(num_part)
    basename = stem[:underscore_pos]
    if index <= 0 or not basename:
        return None
    return basename, index


def _document_memory_label_map(database_path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    try:
        from app.db.document_store import list_documents

        for doc in list_documents(database_path):
            filename = str(doc.get("filename") or "").strip()
            if not filename:
                continue
            parsed = _parse_split_pattern(filename)
            source_id = parsed[0] if parsed is not None else str(doc.get("id") or "").strip()
            label = parsed[0] if parsed is not None else filename
            if source_id and label:
                labels.setdefault(source_id, label)
    except Exception as exc:
        logger.warning("Failed to build document memory labels: %s", exc)
    return labels


def _get_llm_config(settings: Any) -> dict[str, str]:
    """Extract LLM config from settings."""
    if not settings:
        return {}
    
    provider = settings.agent.providers.get(settings.agent.provider)
    if not provider:
        return {}
    
    config: dict[str, str] = {}
    if provider.type:
        config["provider_type"] = provider.type
    if provider.model:
        config["model"] = provider.model
    if provider.api_key:
        config["api_key"] = provider.api_key
    if provider.base_url:
        config["base_url"] = provider.base_url
    return config


def _get_platform_llm_config(database_path: Path) -> dict[str, str]:
    try:
        from app.yaml_config import get_yaml_config
        from app.db.core import connect_database
        from app.crypto_utils import get_crypto_utils
        from app.exceptions import CryptoError

        yaml_cfg = get_yaml_config()
        provider_key = yaml_cfg.get("agent.provider")
        if not provider_key:
            return {}

        with connect_database(database_path) as conn:
            row = conn.execute(
                "SELECT provider_type, model, base_url, api_key FROM agent_provider_config WHERE provider_key = ? AND is_active = 1",
                (provider_key,),
            ).fetchone()

        if not row:
            return {}

        crypto = get_crypto_utils()
        try:
            api_key = crypto.decrypt(str(row["api_key"]))
        except CryptoError:
            api_key = ""

        config: dict[str, str] = {}
        if str(row["provider_type"]):
            config["provider_type"] = str(row["provider_type"])
        if str(row["model"]):
            config["model"] = str(row["model"])
        if api_key:
            config["api_key"] = api_key
        if str(row["base_url"]):
            config["base_url"] = str(row["base_url"])
        return config
    except Exception as e:
        logger.error(f"Failed to get platform LLM config: {e}")
        return {}


def _build_subprocess_env(llm_config: dict[str, str]) -> dict[str, str]:
    env: dict[str, str] = {}
    if llm_config.get("api_key"):
        env["LLM_API_KEY"] = llm_config["api_key"]
    return env


async def _run_subprocess_async(
    cmd: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
) -> tuple[bool, str, str]:
    proc: subprocess.CompletedProcess[str] | None = None
    try:
        subprocess_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        if env:
            subprocess_env.update(env)
        proc = await asyncio.wait_for(
            asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(cwd),
                env=subprocess_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
            ),
            timeout=305,
        )
        return (
            proc.returncode == 0,
            proc.stdout,
            proc.stderr,
        )
    except asyncio.TimeoutError:
        logger.error(f"Subprocess timed out after 300s: {cmd[0] if cmd else 'unknown'}")
        return False, "", "Timeout"
    except subprocess.TimeoutExpired:
        logger.error(f"Subprocess timed out after 300s: {cmd[0] if cmd else 'unknown'}")
        return False, "", "Timeout"
    except Exception as e:
        logger.error(f"Failed to run subprocess: {e}")
        return False, "", str(e)


async def read_memory(
    user_query: str,
    project_root: Path | None = None,
    settings: Any = None,
    database_path: Path | None = None,
    trace_id: str = "",
    expanded_terms: list[str] | None = None,
) -> dict[str, Any]:
    """读取记忆包，通过子进程调用 memory-reader 脚本获取与用户查询相关的记忆内容。"""
    empty_result = {
        "memory_pack": "",
        "selected_files": [],
        "selected_sections": [],
        "omitted_files": [],
        "token_budget_used_estimate": 0,
        "confidence": "",
        "needs_more_memory": False,
        "reason": "",
    }
    try:
        project_root = _get_project_root(project_root)

        memory_dir = project_root / ".memory"
        if not memory_dir.exists():
            await init_memory(project_root=project_root)

        script_path = project_root / ".skills" / "system" / "memory-reader" / "script" / "read.py"

        if not script_path.exists():
            logger.error(f"memory-reader script not found at {script_path}")
            return dict(empty_result)

        # 根据记忆条目数量动态决定 token budget
        base_budget, expanded_budget = _resolve_memory_token_budget(memory_dir)
        cmd = [
            sys.executable,
            str(script_path),
            "--current-message", user_query,
            "--memory-dir", str(memory_dir),
            "--token-budget", str(base_budget),
        ]
        if expanded_budget > base_budget:
            cmd.extend(["--token-budget-expanded", str(expanded_budget)])
        document_labels = _document_memory_label_map(database_path) if database_path else {}
        if document_labels:
            cmd.extend(["--document-labels-json", json.dumps(document_labels, ensure_ascii=False)])

        # LLM 查询扩展（如果启用）
        resolved_expanded_terms = expanded_terms
        if resolved_expanded_terms is None and _is_query_expansion_enabled(project_root):
            resolved_expanded_terms = await expand_query_with_llm(
                user_query, settings=settings, database_path=database_path, trace_id=trace_id
            )
        if resolved_expanded_terms:
            cmd.extend(["--expanded-terms", "|".join(resolved_expanded_terms)])
            logger.info(f"记忆读取传入扩展词: {resolved_expanded_terms}")
        elif expanded_terms is not None or _is_query_expansion_enabled(project_root):
            logger.info("记忆读取: 查询扩展未返回扩展词")

        success, stdout, stderr = await _run_subprocess_async(cmd, project_root)

        if not success:
            logger.error(f"read_memory failed: {stderr}")
            return dict(empty_result)

        try:
            output = json.loads(stdout)
            if output.get("ok", False):
                result = dict(empty_result)
                result["memory_pack"] = str(output.get("memory_pack", "")).strip()
                result["selected_files"] = [str(item) for item in output.get("selected_files", []) if str(item).strip()]
                result["selected_sections"] = [str(item) for item in output.get("selected_sections", []) if str(item).strip()]
                result["omitted_files"] = [str(item) for item in output.get("omitted_files", []) if str(item).strip()]
                result["token_budget_used_estimate"] = max(0, int(output.get("token_budget_used_estimate", 0) or 0))
                result["confidence"] = str(output.get("confidence", "") or "")
                result["needs_more_memory"] = bool(output.get("needs_more_memory", False))
                result["reason"] = str(output.get("reason", "") or "")
                return result
            return dict(empty_result)
        except json.JSONDecodeError:
            logger.error(f"read_memory invalid JSON output: {stdout[:200]}")
            return dict(empty_result)

    except Exception as e:
        logger.warning(f"Failed to read memory, graceful degradation: {e}")
        return dict(empty_result)


async def _run_memory_creator_subprocess(
    source_type: str,
    source_text: str,
    metadata: dict[str, Any],
    project_root: Path,
    settings: Any = None,
    database_path: Path | None = None,
    mode: str = "append",
    split_series: str = "",
    split_index: int = 0,
    split_total: int = 0,
) -> dict[str, Any]:
    script_path = project_root / ".skills" / "system" / "memory-creator" / "script" / "consolidate.py"

    if not script_path.exists():
        logger.error(f"memory-creator script not found at {script_path}")
        return {"ok": False, "error": f"script not found: {script_path}"}

    temp_file = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".txt", delete=False
    )
    try:
        temp_file.write(source_text)
        temp_file.close()
        temp_file_path = temp_file.name

        cmd = [
            sys.executable,
            str(script_path),
            "--source-type", source_type,
            "--source-file", str(temp_file_path),
            "--source-id", metadata.get("source_id", ""),
            "--title", metadata.get("title", ""),
            "--memory-dir", str(project_root / ".memory"),
            "--mode", mode,
        ]

        if split_series:
            cmd.extend([
                "--split-series", split_series,
                "--split-index", str(split_index),
                "--split-total", str(split_total),
            ])

        llm_config = _get_platform_llm_config(database_path) if database_path else _get_llm_config(settings)
        env = _build_subprocess_env(llm_config)
        if llm_config.get("provider_type"):
            cmd.extend(["--provider-type", llm_config["provider_type"]])
        if llm_config.get("model"):
            cmd.extend(["--model", llm_config["model"]])
        if llm_config.get("base_url"):
            cmd.extend(["--base-url", llm_config["base_url"]])

        success, stdout, stderr = await _run_subprocess_async(cmd, project_root, env=env)

        if not success:
            error_text = _error_from_subprocess_output(stdout, stderr)
            logger.error(f"extract_{source_type}_memory failed: {error_text}")
            payload = _parse_json_result(stdout)
            if payload is not None:
                return payload
            return {"ok": False, "error": error_text}

        try:
            output = json.loads(stdout)
            if output.get("ok", False):
                logger.info(f"extract_{source_type}_memory succeeded, updated files: {output.get('updated_files', [])}")
                return output
            else:
                logger.error(f"extract_{source_type}_memory returned error: {output.get('error')}")
                return {"ok": False, "error": output.get("error", "unknown error")}
        except json.JSONDecodeError:
            logger.error(f"extract_{source_type}_memory invalid JSON output: {stdout[:200]}")
            return {"ok": False, "error": f"invalid JSON output: {stdout[:200]}"}
    finally:
        try:
            Path(temp_file_path).unlink()
        except Exception:
            pass


async def add_explicit_memory(
    source_text: str,
    metadata: dict[str, Any] | None = None,
    project_root: Path | None = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    try:
        project_root = _get_project_root(project_root)
        if metadata is None:
            metadata = {}
        return await _run_memory_creator_subprocess(
            source_type="explicit",
            source_text=source_text,
            metadata=metadata,
            project_root=project_root,
            database_path=database_path,
        )
    except Exception as e:
        logger.error(f"Failed to add explicit memory: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def extract_chat_memory(
    source_text: str,
    metadata: dict[str, Any],
    project_root: Path | None = None,
    settings: Any = None,
    database_path: Path | None = None,
) -> dict[str, Any]:
    try:
        project_root = _get_project_root(project_root)
        return await _run_memory_creator_subprocess(
            source_type="chat",
            source_text=source_text,
            metadata=metadata,
            project_root=project_root,
            settings=settings,
            database_path=database_path,
        )
    except Exception as e:
        logger.error(f"Failed to extract chat memory: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def extract_document_memory(
    source_text: str,
    metadata: dict[str, Any],
    project_root: Path | None = None,
    settings: Any = None,
    mode: str = "append",
    split_series: str = "",
    split_index: int = 0,
    split_total: int = 0,
    database_path: Path | None = None,
) -> dict[str, Any]:
    try:
        project_root = _get_project_root(project_root)
        return await _run_memory_creator_subprocess(
            source_type="document",
            source_text=source_text,
            metadata=metadata,
            project_root=project_root,
            settings=settings,
            database_path=database_path,
            mode=mode,
            split_series=split_series,
            split_index=split_index,
            split_total=split_total,
        )
    except Exception as e:
        logger.error(f"Failed to extract document memory: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def review_memory(
    project_root: Path | None = None,
    settings: Any = None,
    database_path: Path | None = None,
    review_type: str = "conversation_usage",
    audit_payload: list[dict[str, Any]] | None = None,
    usage_scope: str = "chat",
    mode: str = "review",
    review_prompt: str = "",
) -> dict[str, Any]:
    try:
        project_root = _get_project_root(project_root)
        script_path = project_root / ".skills" / "system" / "memory-reviewer" / "script" / "review.py"

        if not script_path.exists():
            logger.error(f"memory-reviewer script not found at {script_path}")
            return {"ok": False, "error": f"script not found: {script_path}"}

        cmd = [
            sys.executable,
            str(script_path),
            "--review-type", review_type,
            "--memory-dir", str(project_root / ".memory"),
            "--mode", mode,
        ]
        temp_audit_path: str | None = None
        if review_type == "conversation_usage":
            temp_audit = tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".json", delete=False
            )
            try:
                json.dump(audit_payload or [], temp_audit, ensure_ascii=False)
            finally:
                temp_audit.close()
            temp_audit_path = temp_audit.name
            cmd.extend([
                "--audit-file", temp_audit_path,
                "--usage-scope", usage_scope,
            ])
            if review_prompt.strip():
                cmd.extend(["--review-prompt", review_prompt.strip()])

        llm_config = _get_platform_llm_config(database_path) if database_path else _get_llm_config(settings)
        env = _build_subprocess_env(llm_config)
        if llm_config.get("provider_type"):
            cmd.extend(["--provider-type", llm_config["provider_type"]])
        if llm_config.get("model"):
            cmd.extend(["--model", llm_config["model"]])
        if llm_config.get("base_url"):
            cmd.extend(["--base-url", llm_config["base_url"]])
        
        success, stdout, stderr = await _run_subprocess_async(cmd, project_root, env=env)

        if not success:
            error_text = _error_from_subprocess_output(stdout, stderr)
            logger.error(f"review_memory failed: {error_text}")
            payload = _parse_json_result(stdout)
            if payload is not None:
                return payload
            return {"ok": False, "error": error_text}
        
        try:
            output = json.loads(stdout)
            if output.get("ok", False):
                logger.info(f"review_memory succeeded")
                return output
            else:
                logger.error(f"review_memory returned error: {output.get('error')}")
                return output
        except json.JSONDecodeError:
            logger.error(f"review_memory invalid JSON output: {stdout[:200]}")
            return {"ok": False, "error": f"invalid JSON output: {stdout[:200]}"}
    except Exception as e:
        logger.error(f"Failed to review memory: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
    finally:
        if 'temp_audit_path' in locals() and temp_audit_path:
            try:
                Path(temp_audit_path).unlink()
            except Exception:
                pass


async def init_memory(
    project_root: Path | None = None,
) -> dict[str, Any]:
    """初始化记忆目录，通过子进程调用 memory-creator 的初始化脚本创建记忆存储结构。"""
    try:
        project_root = _get_project_root(project_root)
        script_path = project_root / ".skills" / "system" / "memory-creator" / "script" / "init_memory.py"

        if not script_path.exists():
            logger.error(f"init_memory script not found at {script_path}")
            return {"ok": False, "error": f"script not found: {script_path}"}

        cmd = [
            sys.executable,
            str(script_path),
            "--memory-dir", str(project_root / ".memory"),
        ]

        success, stdout, stderr = await _run_subprocess_async(cmd, project_root)

        if not success:
            logger.error(f"init_memory failed: {stderr}")
            return {"ok": False, "error": stderr}

        try:
            output = json.loads(stdout)
            if output.get("ok", False):
                message = output.get("message", "")
                if "already initialized" not in message:
                    logger.info(f"init_memory succeeded: {message}")
                return output
            else:
                logger.error(f"init_memory returned error: {output.get('error')}")
                return {"ok": False, "error": output.get("error", "unknown error")}
        except json.JSONDecodeError:
            logger.error(f"init_memory invalid JSON output: {stdout[:200]}")
            return {"ok": False, "error": f"invalid JSON output: {stdout[:200]}"}

    except Exception as e:
        logger.error(f"Failed to init memory: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


async def notify_owner(
    content: str,
    reason: str,
    chat_id: str,
    bot_key: str,
    project_root: Path | None = None,
) -> bool:
    """调用 notify-me 技能通知 Bot 管理员，通过子进程执行通知脚本发送结果通知。"""
    try:
        project_root = _get_project_root(project_root)
        script_path = project_root / ".skills" / "system" / "notify-me" / "script" / "notify.py"
        
        if not script_path.exists():
            logger.error(f"notify-me script not found at {script_path}")
            return False
        
        cmd = [
            sys.executable,
            str(script_path),
            "--content", content,
            "--reason", reason,
            "--chat-id", chat_id,
            "--bot-key", bot_key,
        ]
        
        success, stdout, stderr = await _run_subprocess_async(cmd, project_root)
        
        if not success:
            logger.error(f"notify_owner failed: {stderr}")
            return False
        
        try:
            output = json.loads(stdout)
            if output.get("ok", False):
                logger.info(f"notify_owner succeeded")
                return True
            else:
                logger.error(f"notify_owner returned error: {output.get('error')}")
                return False
        except json.JSONDecodeError:
            logger.error(f"notify_owner invalid JSON output: {stdout[:200]}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to notify owner: {e}", exc_info=True)
        return False
