from __future__ import annotations

import hmac
import os
import socket
import statistics
import time
from enum import StrEnum

import psutil
import socket as socket_module
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.core_manager import apply, capability, core_status, restart_service, rollback

AGENT_VERSION = os.getenv("AGENT_VERSION", "2.0.0")
NODE_KEY = os.getenv("NODE_KEY", "UNSET")
COUNTRY = os.getenv("COUNTRY", "")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "")

app = FastAPI(title=f"Pars2Ray Node Agent {NODE_KEY}", version=AGENT_VERSION, docs_url=None, redoc_url=None, openapi_url=None)


def authorize(token: str | None) -> None:
    if not AGENT_TOKEN or not token or not hmac.compare_digest(token, AGENT_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "node_key": NODE_KEY, "country": COUNTRY, "agent_version": AGENT_VERSION, "hostname": socket.gethostname(), "timestamp": int(time.time())}


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


@app.post("/benchmark/tcp")
def benchmark(request: BenchmarkRequest, x_agent_token: str | None = Header(default=None)) -> dict:
    authorize(x_agent_token)
    latencies: list[float] = []
    failures = 0
    for _ in range(request.attempts):
        start = time.perf_counter()
        try:
            with socket_module.create_connection((request.host, request.port), timeout=request.timeout_seconds):
                pass
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
    RUN_BENCHMARK = "RUN_BENCHMARK"
    APPLY_CONFIG = "APPLY_CONFIG"
    ROLLBACK = "ROLLBACK"
    RESTART_SERVICE = "RESTART_SERVICE"


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
    if request.command == Command.RUN_BENCHMARK:
        return benchmark(BenchmarkRequest(**request.payload), x_agent_token)
    if request.command == Command.APPLY_CONFIG:
        return apply(request.payload)
    if request.command == Command.ROLLBACK:
        return rollback()
    if request.command == Command.RESTART_SERVICE:
        return restart_service()
    raise HTTPException(status_code=400, detail="unsupported_command")
