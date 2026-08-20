from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str


ALLOWED_CORES = {"xray", "sing-box"}
ALLOWED_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}
ALLOWED_TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"}


def validate_candidate(candidate: dict, current_score: float = 0) -> ValidationResult:
    if not isinstance(candidate, dict):
        return ValidationResult(False, "invalid_candidate")
    if not isinstance(current_score, (int, float)) or not math.isfinite(float(current_score)):
        return ValidationResult(False, "invalid_current_score")
    if candidate.get("core") not in ALLOWED_CORES:
        return ValidationResult(False, "unsupported_core")
    if candidate.get("protocol") not in ALLOWED_PROTOCOLS:
        return ValidationResult(False, "unsupported_protocol")
    if candidate.get("transport") not in ALLOWED_TRANSPORTS:
        return ValidationResult(False, "unsupported_transport")
    try:
        score = float(candidate.get("score", 0))
    except (TypeError, ValueError):
        return ValidationResult(False, "invalid_score")
    if not math.isfinite(score) or score < 0 or score > 100:
        return ValidationResult(False, "invalid_score")
    if score < float(current_score) + 1:
        return ValidationResult(False, "insufficient_improvement")
    if candidate.get("config") is not None and not isinstance(candidate.get("config"), dict):
        return ValidationResult(False, "invalid_config")
    return ValidationResult(True, "validated_for_canary")
