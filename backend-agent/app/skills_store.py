from __future__ import annotations

"""技能扫描、加载与上下文构建模块。

管理技能（Skill）的目录扫描、元数据解析、ZIP 安装、上下文拼接和删除，
支持从 SKILL.md 文件和 Markdown 文件中提取技能定义，
并将启用的技能内容拼接为 Agent 可用的上下文文本。
"""

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

SKILLS_DIR_NAME = ".skills"
SKILL_FILE_NAME = "SKILL.md"
SCRIPT_DIR_NAME = "script"


def _get_skills_config() -> dict[str, Any]:
    from app.yaml_config import get_yaml_config
    return get_yaml_config().as_dict().get("skills", {})


def _max_zip_bytes() -> int:
    return int(_get_skills_config().get("max_zip_bytes"))


def _max_single_file_bytes() -> int:
    return int(_get_skills_config().get("max_single_file_bytes"))


def _max_zip_entries() -> int:
    return int(_get_skills_config().get("max_zip_entries"))


def skills_directory(project_root: Path) -> Path:
    return project_root.resolve() / SKILLS_DIR_NAME


def scan_skills(
    project_root: Path,
    enabled_names: list[str] | None = None,
    display_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = skills_directory(project_root)
    enabled = set(enabled_names or [])
    custom_display_names = display_names or {}

    if not root.exists():
        return []

    skills: list[dict[str, Any]] = []
    for skill_file in _iter_skill_files(root):
        skill = _read_skill_metadata(root, skill_file)
        if str(skill.get("scope") or "bot") == "system":
            skill["enabled"] = bool(skill.get("always_active")) or skill["name"] in enabled
        else:
            skill["enabled"] = skill["name"] in enabled
        skill["display_name"] = custom_display_names.get(skill["name"], skill["name"])
        skills.append(skill)

    return sorted(skills, key=lambda item: str(item["name"]).lower())


def build_skill_full_context(
    project_root: Path,
    enabled_names: list[str],
) -> str:
    if not enabled_names:
        return ""

    root = skills_directory(project_root)
    if not root.exists():
        return ""

    enabled = set(enabled_names)
    parts: list[str] = []

    for skill in scan_skills(project_root, enabled_names):
        if skill["name"] not in enabled:
            continue

        path = Path(str(skill["path"]))
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        full_text = raw_text.strip()
        if not full_text:
            continue

        block = f"## Skill: {skill['name']}\n{full_text}"
        parts.append(block)

    return "\n\n".join(parts).strip()


def install_skills_zip(project_root: Path, archive_bytes: bytes) -> dict[str, Any]:
    _validate_zip_size(archive_bytes)
    root = skills_directory(project_root)
    root.mkdir(parents=True, exist_ok=True)

    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("上传文件不是有效的 zip。") from exc

    _validate_zip_entries(archive)

    extracted = 0
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue

            relative_path = Path(member.filename)
            if _is_unsafe_zip_path(relative_path):
                raise ValueError(f"zip 内包含不安全路径: {member.filename}")
            if _is_symlink_member(member):
                raise ValueError(f"zip 内包含符号链接: {member.filename}")
            if member.file_size > _max_single_file_bytes():
                raise ValueError(f"zip 内文件过大: {member.filename} ({member.file_size} bytes)")

            target_path = root / relative_path
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target_path.open("wb") as target:
                target.write(source.read())
            extracted += 1

    skills = scan_skills(project_root)
    if not skills:
        raise ValueError("zip 中没有找到可识别的 Skill。需要包含 SKILL.md 或 markdown skill 文件。")

    return {"extracted_files": extracted, "skills": skills}


def _iter_skill_files(root: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    for path in sorted(root.rglob(SKILL_FILE_NAME)):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        files.append(path)

    for child in sorted(root.iterdir()):
        if child.is_file() and child.suffix.lower() == ".md" and child.name != "README.md":
            resolved = child.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(child)

    return files


def _is_unsafe_zip_path(path: Path) -> bool:
    parts = path.parts
    return path.is_absolute() or ".." in parts or not parts


_UNIX_S_IFMT = 0o170000
UNIX_S_IFLNK = 0o120000


def _is_symlink_member(member: zipfile.ZipInfo) -> bool:
    return (member.external_attr >> 16) & _UNIX_S_IFMT == UNIX_S_IFLNK


def _find_skill_definition_file(directory: Path) -> Path | None:
    skill_file = directory / SKILL_FILE_NAME
    if skill_file.exists() and skill_file.is_file():
        return skill_file
    return None


def _read_skill_metadata(root: Path, path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""

    frontmatter = _parse_frontmatter(text)
    default_name = path.parent.name if path.name == SKILL_FILE_NAME else path.stem
    name = str(frontmatter.get("name") or default_name).strip() or default_name

    # 如果 frontmatter 有 description，取第一行用于卡片展示
    raw_desc = str(frontmatter.get("description", "")).strip()
    if raw_desc:
        # 取第一行
        description = raw_desc.splitlines()[0].strip()
    else:
        description = _first_body_line(text).strip()

    skill_root = path.parent if path.name == SKILL_FILE_NAME else path.parent
    relative_path = path.relative_to(root).as_posix()
    scope = "system" if relative_path.startswith("system/") else "bot"
    script_dir = _find_skill_script_dir(skill_root)
    script_files = _list_script_files(script_dir, skill_root) if script_dir is not None else []

    always_active_raw = str(frontmatter.get("always_active", "")).strip().lower()
    always_active = always_active_raw in ("true", "yes", "1")

    return {
        "name": name,
        "description": description,
        "relative_path": relative_path,
        "path": str(path.resolve()),
        "skill_root": str(skill_root.resolve()),
        "scope": scope,
        "has_scripts": bool(script_files),
        "script_dir": str(script_dir.resolve()) if script_dir is not None else "",
        "relative_script_dir": script_dir.relative_to(root).as_posix() if script_dir is not None else "",
        "script_files": script_files,
        "always_active": always_active,
    }


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    metadata: dict[str, str] = {}
    current_key: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return metadata

        if ":" in line and len(line.split(":", 1)[0].strip()) > 0:
            key, value = line.split(":", 1)
            current_key = key.strip()
            val = value.strip().strip("'\"")
            metadata[current_key] = val
        elif current_key is not None and stripped:
            existing = metadata.get(current_key, "")
            if existing:
                metadata[current_key] = existing + "\n" + line.rstrip("\n")
            else:
                metadata[current_key] = line.rstrip("\n")

    return metadata


def _find_skill_script_dir(skill_root: Path) -> Path | None:
    script_dir = skill_root / SCRIPT_DIR_NAME
    if script_dir.exists() and script_dir.is_dir():
        return script_dir
    return None


def _list_script_files(script_dir: Path, skill_root: Path) -> list[str]:
    files: list[str] = []
    for path in sorted(script_dir.rglob("*.py")):
        if not path.is_file():
            continue
        files.append(path.relative_to(skill_root).as_posix())
    return files


def _first_body_line(text: str) -> str:
    lines = text.splitlines()
    i = 0

    # 跳过 frontmatter
    if i < len(lines) and lines[i].strip() == "---":
        i += 1
        while i < len(lines):
            if lines[i].strip() == "---":
                i += 1
                break
            i += 1

    # 找第一行有效正文（非空、非 # 标题
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith("#"):
            return stripped
        i += 1
    return ""


def delete_skill(project_root: Path, skill_name: str) -> bool:
    """删除指定名称的技能。"""
    root = skills_directory(project_root)
    if not root.exists():
        return False

    skills = scan_skills(project_root)
    skill_to_delete = None
    for skill in skills:
        if skill["name"] == skill_name:
            skill_to_delete = skill
            break

    if not skill_to_delete:
        return False

    path = Path(skill_to_delete["path"])
    if path.name == SKILL_FILE_NAME:
        # 技能是一个目录，删除整个目录
        dir_to_delete = path.parent
        if dir_to_delete.parent == root:
            import shutil
            shutil.rmtree(dir_to_delete, ignore_errors=True)
            return True
    else:
        # 技能是单个文件，删除文件
        if path.exists():
            path.unlink(missing_ok=True)
            return True

    return False


def parse_skills_zip(archive_bytes: bytes) -> dict[str, Any]:
    _validate_zip_size(archive_bytes)
    try:
        archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("上传文件不是有效的 zip。") from exc

    _validate_zip_entries(archive)

    with tempfile.TemporaryDirectory(prefix="skills-preview-") as temp_dir:
        temp_root = Path(temp_dir)
        with archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue

                relative_path = Path(member.filename)
                if _is_unsafe_zip_path(relative_path):
                    raise ValueError(f"zip 内包含不安全路径: {member.filename}")
                if _is_symlink_member(member):
                    raise ValueError(f"zip 内包含符号链接: {member.filename}")

                target_path = temp_root / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target_path.open("wb") as target:
                    target.write(source.read())

        skill_files = _iter_skill_files(temp_root)
        skills = []
        for skill_file in skill_files:
            metadata = _read_skill_metadata(temp_root, skill_file)
            skills.append(
                {
                    "name": metadata["name"],
                    "description": metadata["description"],
                    "relative_path": metadata["relative_path"],
                }
            )

    if not skills:
        raise ValueError("zip 中没有找到可识别的 Skill。需要包含 SKILL.md 或 markdown skill 文件。")

    return {
        "skills": skills,
        "total_files": len(skill_files),
    }


def _validate_zip_size(archive_bytes: bytes) -> None:
    if len(archive_bytes) > _max_zip_bytes():
        raise ValueError(f"zip 文件大小超过限制（最大 {_max_zip_bytes() // (1024 * 1024)} MB）。")


def _validate_zip_entries(archive: zipfile.ZipFile) -> None:
    entries = [m for m in archive.infolist() if not m.is_dir()]
    if len(entries) > _max_zip_entries():
        raise ValueError(f"zip 内文件数量超过限制（最大 {_max_zip_entries()} 个）。")
    total_uncompressed = sum(m.file_size for m in entries)
    if total_uncompressed > _max_zip_bytes() * 5:
        raise ValueError("zip 解压后总大小超过限制。")
