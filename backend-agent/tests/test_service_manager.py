"""Agent 后台服务管理测试。"""

from __future__ import annotations

import json

import psutil

from scripts import service_manager
from scripts.service_manager import ProcessRecord


def test_write_and_read_record_round_trip(monkeypatch, tmp_path) -> None:
    """进程记录应能够无损写入并读取。"""
    runtime_directory = tmp_path / ".runtime"
    pid_file = runtime_directory / "agent.json"
    monkeypatch.setattr(service_manager, "RUNTIME_DIRECTORY", runtime_directory)
    monkeypatch.setattr(service_manager, "PID_FILE", pid_file)
    expected = ProcessRecord(
        pid=1234,
        create_time=100.5,
        host="127.0.0.1",
        port=8030,
    )
    service_manager._write_record(expected)
    assert service_manager._read_record() == expected


def test_read_record_returns_none_for_invalid_json(monkeypatch, tmp_path) -> None:
    """损坏的进程记录应被视为无记录。"""
    pid_file = tmp_path / "agent.json"
    pid_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(service_manager, "PID_FILE", pid_file)
    assert service_manager._read_record() is None


def test_stop_service_cleans_invalid_record(monkeypatch, tmp_path) -> None:
    """无效 PID 记录应被安全清理且不结束其他进程。"""
    pid_file = tmp_path / "agent.json"
    pid_file.write_text(
        json.dumps(
            {
                "pid": 999999,
                "create_time": 1.0,
                "host": "127.0.0.1",
                "port": 8030,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(service_manager, "PID_FILE", pid_file)
    monkeypatch.setattr(service_manager, "STOP_REQUEST_FILE", tmp_path / "stop.request")
    assert service_manager.stop_service() == 0
    assert pid_file.exists() is False


def test_stop_service_prefers_graceful_request(monkeypatch, tmp_path) -> None:
    """有效进程应先收到停止请求，不应直接被强制终止。"""
    stop_request_file = tmp_path / "stop.request"
    pid_file = tmp_path / "agent.json"
    record = ProcessRecord(
        pid=1234,
        create_time=100.5,
        host="127.0.0.1",
        port=8030,
    )

    class FakeProcess:
        """记录服务管理器采用的停止路径。"""

        def wait(self, *, timeout) -> None:
            assert timeout == service_manager.STOP_TIMEOUT_SECONDS
            assert stop_request_file.read_text(encoding="utf-8") == "stop\n"

        def terminate(self) -> None:
            raise AssertionError("优雅停止成功时不应强制终止进程")

    monkeypatch.setattr(service_manager, "PID_FILE", pid_file)
    monkeypatch.setattr(service_manager, "STOP_REQUEST_FILE", stop_request_file)
    monkeypatch.setattr(service_manager, "RUNTIME_DIRECTORY", tmp_path)
    monkeypatch.setattr(service_manager, "_read_record", lambda: record)
    monkeypatch.setattr(service_manager, "_resolve_process", lambda _record: FakeProcess())

    assert service_manager.stop_service() == 0
    assert stop_request_file.exists() is False


def test_terminate_process_escalates_after_timeout() -> None:
    """终止超时后应强制结束进程，避免留下孤儿。"""

    class FakeProcess:
        """模拟首次等待超时的进程。"""

        def __init__(self) -> None:
            self.terminated = False
            self.killed = False
            self.wait_count = 0

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, *, timeout) -> None:
            assert timeout == service_manager.STOP_TIMEOUT_SECONDS
            self.wait_count += 1
            if self.wait_count == 1:
                raise psutil.TimeoutExpired(timeout)

    process = FakeProcess()
    service_manager._terminate_process(process)

    assert process.terminated is True
    assert process.killed is True
    assert process.wait_count == 2
