from __future__ import annotations

import hmac
import ipaddress
import os
import socket
import statistics
import time
from enum import StrEnum

import psutil
import socket as socket_module
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.services.core_manager import apply, capability, core_status, restart_service, rollback
from app.services.inbound_manager import current_config, update_existing_inbounds
from app.services.operations import firewall_status, logs as service_logs, service_action, update as update_core, version as core_version

AGENT_VERSION = os.getenv("AGENT_VERSION", "2.3.0")
NODE_KEY = os.getenv("NODE_KEY", "UNSET")
COUNTRY = os.getenv("COUNTRY", "")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")
app = FastAPI(title=f"Pars2Ray Node Agent {NODE_KEY}", version=AGENT_VERSION, docs_url=None, redoc_url=None, openapi_url=None)


def authorize(token: str | None) -> None:
    if not AGENT_TOKEN or not token or not hmac.compare_digest(token, AGENT_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/heartbeat")
def heartbeat(x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    return {"ok": True, "node_key": NODE_KEY, "timestamp": int(time.time()), "capabilities": capability()}


@app.get("/metrics")
def metrics(x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    net = psutil.net_io_counters()
    return {"cpu_percent": psutil.cpu_percent(interval=0.15), "memory_percent": psutil.virtual_memory().percent, "traffic_rx_bytes": net.bytes_recv, "traffic_tx_bytes": net.bytes_sent, "timestamp": int(time.time())}


@app.get("/capabilities")
def capabilities(x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    return capability()


class BenchmarkRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    attempts: int = Field(default=5, ge=1, le=20)
    timeout_seconds: float = Field(default=3.0, ge=0.2, le=15.0)

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        value = value.strip().rstrip(".")
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("invalid_host")
        return value


def _public_addresses(host: str) -> list[tuple[int, str]]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="host_resolution_failed") from exc
    addresses: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for family, _, _, _, sockaddr in infos:
        address = sockaddr[0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not parsed.is_global:
            raise HTTPException(status_code=422, detail="benchmark_target_must_be_public")
        item = (family, address)
        if item not in seen:
            seen.add(item)
            addresses.append(item)
    if not addresses:
        raise HTTPException(status_code=422, detail="no_public_address")
    return addresses


def _connect_address(family: int, address: str, port: int) -> tuple:
    if family == socket.AF_INET6:
        return (address, port, 0, 0)
    return (address, port)


@app.post("/benchmark/tcp")
def benchmark(request: BenchmarkRequest, x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    addresses = _public_addresses(request.host)
    latencies: list[float] = []
    failures = 0
    for attempt in range(request.attempts):
        family, address = addresses[attempt % len(addresses)]
        start = time.perf_counter()
        try:
            with socket_module.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(request.timeout_seconds)
                sock.connect(_connect_address(family, address, request.port))
            latencies.append((time.perf_counter() - start) * 1000)
        except OSError:
            failures += 1
    if not latencies:
        return {"ok": False, "latency_ms": 0, "jitter_ms": 0, "packet_loss_percent": 100, "stability_percent": 0}
    return {"ok": True, "latency_ms": round(statistics.mean(latencies), 2), "jitter_ms": round(statistics.pstdev(latencies), 2) if len(latencies) > 1 else 0, "packet_loss_percent": round(failures / request.attempts * 100, 2), "stability_percent": round(len(latencies) / request.attempts * 100, 2)}


class Command(StrEnum):
    GET_STATUS = "GET_STATUS"
    GET_METRICS = "GET_METRICS"
    GET_CORE_STATUS = "GET_CORE_STATUS"
    GET_CONFIG = "GET_CONFIG"
    RUN_BENCHMARK = "RUN_BENCHMARK"
    APPLY_CONFIG = "APPLY_CONFIG"
    UPDATE_EXISTING_INBOUNDS = "UPDATE_EXISTING_INBOUNDS"
    ROLLBACK = "ROLLBACK"
    RESTART_SERVICE = "RESTART_SERVICE"
    START_SERVICE = "START_SERVICE"
    STOP_SERVICE = "STOP_SERVICE"
    CORE_VERSION = "CORE_VERSION"
    CORE_LOGS = "CORE_LOGS"
    UPDATE_CORE = "UPDATE_CORE"
    FIREWALL_STATUS = "FIREWALL_STATUS"


class CommandRequest(BaseModel):
    command: Command
    payload: dict = Field(default_factory=dict)


@app.post("/command")
def command(request: CommandRequest, x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    if request.command == Command.GET_STATUS:
        return {"ok": True, "status": health(), "capabilities": capability()}
    if request.command == Command.GET_METRICS:
        return metrics(x_agent_token)
    if request.command == Command.GET_CORE_STATUS:
        return {"ok": True, **core_status()}
    if request.command == Command.GET_CONFIG:
        return {"ok": True, **current_config()}
    if request.command == Command.RUN_BENCHMARK:
        return benchmark(BenchmarkRequest(**request.payload), x_agent_token)
    if request.command == Command.APPLY_CONFIG:
        return apply(request.payload)
    if request.command == Command.UPDATE_EXISTING_INBOUNDS:
        return update_existing_inbounds(request.payload.get("updates", []))
    if request.command == Command.ROLLBACK:
        return rollback(str(request.payload.get("operation_id") or "").strip())
    if request.command == Command.RESTART_SERVICE:
        return restart_service()
    if request.command == Command.START_SERVICE:
        return service_action("start")
    if request.command == Command.STOP_SERVICE:
        return service_action("stop")
    if request.command == Command.CORE_VERSION:
        return core_version()
    if request.command == Command.CORE_LOGS:
        return service_logs(request.payload.get("lines", 200))
    if request.command == Command.UPDATE_CORE:
        return update_core()
    if request.command == Command.FIREWALL_STATUS:
        return firewall_status()
    raise HTTPException(status_code=400, detail="unsupported_command")
