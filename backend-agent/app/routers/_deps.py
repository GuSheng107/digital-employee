from __future__ import annotations

from pathlib import Path

from fastapi import Depends, Request

from app.bot_process_manager import BotProcessManager


def get_database_path(request: Request) -> Path:
    return request.app.state.database_path


def get_project_root(request: Request) -> Path:
    return request.app.state.project_root


def get_manager(request: Request) -> BotProcessManager:
    return request.app.state.manager
