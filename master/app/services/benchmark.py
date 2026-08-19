def score_measurement(latency_ms: float, jitter_ms: float, packet_loss: float, success_rate: float, down_mbps: float, cpu: float = 0, ram: float = 0) -> float:
    latency = max(0, 100 - min(latency_ms, 500) / 5)
    jitter = max(0, 100 - min(jitter_ms, 200) / 2)
    loss = max(0, 100 - min(packet_loss, 100))
    success = max(0, min(success_rate, 100))
    throughput = min(max(down_mbps, 0), 500) / 5
    resources = max(0, 100 - (cpu + ram) / 2)
    return round(max(0, min(latency * .22 + jitter * .10 + loss * .22 + success * .25 + throughput * .16 + resources * .05, 100)), 2)
