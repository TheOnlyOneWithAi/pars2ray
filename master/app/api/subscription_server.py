    quota_gb = max(float(user.quota_gb or 0), 0.0)
    used_gb = max(float(user.used_gb or sub.used_gb or 0), 0.0)
    if quota_gb > 0 and used_gb >= quota_gb:
        return None
    return sub, user


def _client_id(token: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"pars2ray:client:{token_hash(token)}"))


def _route_links(db: Session, sub: Subscription, user: User, token: str) -> list[str]:
    rows: list[str] = []
    routes = db.scalars(select(Route).where(Route.is_active.is_(True)).order_by(Route.id)).all()
    allowed = set(sub.node_keys)
    client_id = _client_id(token)
    for route in routes:
        if allowed and not allowed.intersection(route.node_keys):
            continue
        try:
            cfg = json.loads(decrypt_secret(route.config_enc)) if route.config_enc else {}
        except Exception:
            cfg = {}
        server = str(cfg.get("server") or cfg.get("host") or "")
        if not server and route.node_keys:
            node = db.scalar(select(Node).where(Node.node_key == route.node_keys[0]))
            if node:
                server = node.endpoint.split("://", 1)[-1].split("/", 1)[0].rsplit(":", 1)[0]
        if not server:
            continue
        port = int(cfg.get("port", 443))
        name = quote(route.name, safe="")
        transport = route.transport
        security = str(cfg.get("security") or ("tls" if cfg.get("tls") else "none")).lower()
        params = {"type": "ws" if transport == "websocket" else transport, "security": security}
        if cfg.get("server_name") or cfg.get("sni"):
            params["sni"] = str(cfg.get("server_name") or cfg.get("sni"))
        if cfg.get("fingerprint"):
            params["fp"] = str(cfg["fingerprint"])
        reality = cfg.get("reality") or {}
        if security == "reality":
            if reality.get("public_key") or cfg.get("public_key"):
                params["pbk"] = str(reality.get("public_key") or cfg.get("public_key"))
            if reality.get("short_id") or cfg.get("short_id"):
                params["sid"] = str(reality.get("short_id") or cfg.get("short_id"))
        if transport in {"websocket", "httpupgrade", "xhttp"}:
            params["path"] = str(cfg.get("path", "/"))
            if cfg.get("host"):
                params["host"] = str(cfg["host"])
        if transport == "grpc":
            params["serviceName"] = str(cfg.get("service_name", "pars2ray"))
        query = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in params.items())
        if route.protocol == "vless":
            rows.append(f"vless://{client_id}@{server}:{port}?{query}#{name}")
        elif route.protocol == "vmess":
            payload = {"v": "2", "ps": route.name, "add": server, "port": str(port), "id": client_id, "aid": "0", "scy": "auto", "net": transport, "type": "none", "host": str(cfg.get("host", "")), "path": str(cfg.get("path", "/")), "tls": "tls" if security == "tls" else "", "sni": str(cfg.get("server_name") or cfg.get("sni") or "")}
            rows.append("vmess://" + base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode())
        elif route.protocol == "shadowsocks":
            method = str(cfg.get("method", "aes-128-gcm"))
            password = str(cfg.get("password") or client_id)
            auth = base64.urlsafe_b64encode(f"{method}:{password}".encode()).decode().rstrip("=")
            rows.append(f"ss://{auth}@{server}:{port}#{name}")
        elif route.protocol == "trojan":
            rows.append(f"trojan://{client_id}@{server}:{port}?{query}#{name}")
    return rows


def _stored_links(sub: Subscription) -> list[str]:
    if not sub.config_enc:
        return []
    try:
        data = json.loads(decrypt_secret(sub.config_enc))
    except Exception:
        return []
    links: list[str] = []
    if isinstance(data, dict):
        raw_links = data.get("links", [])
        if isinstance(raw_links, list):
            links.extend(str(link).strip() for link in raw_links if isinstance(link, str) and "://" in link)
        direct = data.get("direct", [])
        if isinstance(direct, list):
            for row in direct:
                if isinstance(row, dict) and row.get("enabled", True) and isinstance(row.get("link"), str) and "://" in row["link"]:
                    links.append(row["link"].strip())
    return links


def _all_links(db: Session, sub: Subscription, user: User, token: str) -> list[str]:
    stored = _stored_links(sub)
    return list(dict.fromkeys(stored + _route_links(db, sub, user, token)))
