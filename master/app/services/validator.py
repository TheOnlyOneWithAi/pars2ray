from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str


ALLOWED_CORES = {"xray", "sing-box"}
ALLOWED_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2"}
ALLOWED_TRANSPORTS = {"tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"}


def validate_candidate(candidate: dict, current_score: float = 0) -> ValidationResult:
    if candidate.get("core") not in ALLOWED_CORES:
        return ValidationResult(False, "unsupported_core")
    if candidate.get("protocol") not in ALLOWED_PROTOCOLS:
        return ValidationResult(False, "unsupported_protocol")
    if candidate.get("transport") not in ALLOWED_TRANSPORTS:
        return ValidationResult(False, "unsupported_transport")
    score = float(candidate.get("score", 0))
    if score < 0 or score > 100:
        return ValidationResult(False, "invalid_score")
    if score < current_score + 1:
        return ValidationResult(False, "insufficient_improvement")
    if candidate.get("config") is not None and not isinstance(candidate.get("config"), dict):
        return ValidationResult(False, "invalid_config")
    return ValidationResult(True, "validated_for_canary")
