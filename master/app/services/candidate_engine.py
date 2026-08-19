import hashlib, json
SUPPORTED_PROTOCOLS=['vless','trojan','shadowsocks']
SUPPORTED_TRANSPORTS=['tcp','grpc','websocket','httpupgrade','xhttp']
SUPPORTED_CORES=['xray','sing-box']

def make_id(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]

def generate(nodes: list[str], max_candidates: int=30, allow_experimental: bool=False) -> list[dict]:
    out=[]
    if not nodes: return out
    transports=SUPPORTED_TRANSPORTS if allow_experimental else ['tcp','grpc','xhttp']
    for node in nodes:
        for core in SUPPORTED_CORES:
            for protocol in SUPPORTED_PROTOCOLS:
                for transport in transports:
                    c={'path':[node],'core':core,'protocol':protocol,'transport':transport,'settings':{}}
                    c['candidate_id']=make_id(c); out.append(c)
                    if len(out)>=max_candidates: return out
    return out
