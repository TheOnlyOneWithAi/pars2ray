from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.core.config import settings
from app.core.security import encrypt_secret, hash_password, random_token, token_hash, utcnow, verify_password
from app.db.base import get_db
from app.models.entities import ApiKey, AuditLog, Decision, Experiment, Metric, Node, Plan, RefreshToken, ResearchFinding, Role, Route, Subscription, SystemSetting, SystemState, Traffic, User
from app.schemas import BenchmarkRequest, ExperimentCreate, LoginRequest, NodeOut, NodeRegisterRequest, OptimizerRequest, PlanCreate, RefreshRequest, RouteCreate, RouteOut, SubscriptionCreate, SystemSettingUpdate, TokenPair, UserCreate, UserOut, UserUpdate
from app.services import agent_client
from app.services.audit import record
from app.services.auth import authenticate, ensure_seed, issue_tokens, rotate_refresh
from app.services.benchmark import score_measurement
from app.services.candidate_engine import generate
from app.services.gate import evaluate_gate
from app.services.national_mode import national_engine
from app.services.openai_optimizer import analyze
from app.services.telemetry import hourly_traffic
from app.services.validator import validate_candidate

router = APIRouter(prefix="/api/v1")


def role(*names: str):
    return Depends(require_roles(*names))


@router.get("/health", tags=["system"])
def health() -> dict:
    return {"ok": True, "service": settings.app_name, "version": settings.app_version, "environment": settings.environment}


@router.post("/auth/login", response_model=TokenPair, tags=["auth"])
def login(payload: LoginRequest, db: Session = Depends(get_db), request: Request = None) -> TokenPair:
    user = authenticate(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    access, refresh, ttl = issue_tokens(db, user)
    record(db, user, "auth.login", "user", str(user.id), request_ip(request) if request else "")
    db.commit()
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=ttl)


@router.post("/auth/refresh", response_model=TokenPair, tags=["auth"])
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    result = rotate_refresh(db, payload.refresh_token)
    if not result:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_refresh_token")
    _, access, refresh_token, ttl = result
    return TokenPair(access_token=access, refresh_token=refresh_token, expires_in=ttl)


@router.post("/auth/logout", tags=["auth"])
def logout(payload: RefreshRequest, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(payload.refresh_token), RefreshToken.user_id == user.id))
    if stored:
        stored.revoked_at = utcnow()
        record(db, user, "auth.logout", "user", str(user.id))
        db.commit()
    return {"ok": True}


@router.get("/dashboard", tags=["system"])
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    nodes = db.scalars(select(Node)).all()
    online = [node for node in nodes if node.status == "ONLINE"]
    active = db.scalar(select(Route).where(Route.is_active.is_(True)))
    state = db.get(SystemState, 1)
    traffic_rx = sum(node.traffic_rx_bytes for node in nodes)
    traffic_tx = sum(node.traffic_tx_bytes for node in nodes)
    return {"node_count": len(nodes), "online_nodes": len(online), "network_health": round(sum(n.score for n in nodes) / len(nodes), 1) if nodes else 0, "traffic": {"rx_bytes": traffic_rx, "tx_bytes": traffic_tx}, "current_best_route": active.name if active else None, "ai_status": state.ai_status if state else "DISABLED", "mode": state.mode if state else "NORMAL", "user_count": db.scalar(select(func.count(User.id))) or 0, "subscription_count": db.scalar(select(func.count(Subscription.id)).where(Subscription.enabled.is_(True))) or 0}


@router.get("/dashboard/telemetry", tags=["system"])
def dashboard_telemetry(hours: int = 24, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    bounded_hours = min(max(hours, 1), 168)
    cutoff = utcnow() - timedelta(hours=bounded_hours)
    samples = db.scalars(select(Traffic).where(Traffic.sampled_at >= cutoff).order_by(Traffic.sampled_at)).all()
    return hourly_traffic(samples)


@router.post("/nodes/register", tags=["nodes"])
def register_node(payload: NodeRegisterRequest, x_master_secret: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    if not x_master_secret or not secrets.compare_digest(x_master_secret, settings.master_secret):
        raise HTTPException(status_code=401, detail="unauthorized")
    node = db.scalar(select(Node).where(Node.node_key == payload.node_key))
    values = {"country": payload.country, "endpoint": payload.endpoint, "agent_token_hash": token_hash(payload.agent_token), "agent_token_enc": encrypt_secret(payload.agent_token), "agent_version": payload.agent_version, "status": "REGISTERED", "last_seen_at": utcnow()}
    if node:
        for key, value in values.items():
            setattr(node, key, value)
    else:
        node = Node(node_key=payload.node_key, **values)
        db.add(node)
    db.commit()
    return {"id": node.id, "node_key": node.node_key, "status": node.status}


@router.get("/nodes", tags=["nodes"], response_model=list[NodeOut])
def list_nodes(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Node]:
    return list(db.scalars(select(Node).order_by(Node.country, Node.node_key)).all())


@router.get("/nodes/{node_key}", tags=["nodes"], response_model=NodeOut)
def get_node(node_key: str, db: Session = Depends(get_db), user: User = Depends(current_user)) -> Node:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    return node


@router.get("/nodes/{node_key}/metrics", tags=["nodes"], response_model=None)
def node_metrics(node_key: str, limit: int = 60, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Metric]:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    bounded_limit = min(max(limit, 1), 500)
    rows = db.scalars(select(Metric).where(Metric.node_id == node.id).order_by(desc(Metric.measured_at)).limit(bounded_limit)).all()
    return list(reversed(rows))


async def _node_action(node_key: str, action: str, db: Session, user: User, request: Request, payload: dict | None = None) -> dict:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    try:
        result = await getattr(agent_client, action)(node, payload) if payload is not None else await getattr(agent_client, action)(node)
    except Exception:
        node.status = "OFFLINE"
        db.commit()
        raise HTTPException(status_code=502, detail="node_unreachable")
    record(db, user, f"node.{action}", "node", str(node.id), request_ip(request))
    db.commit()
    return result


@router.post("/nodes/{node_key}/benchmark", tags=["nodes"])
async def benchmark_node(node_key: str, payload: BenchmarkRequest, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    return await _node_action(node_key, "benchmark", db, user, request, payload.model_dump())


@router.post("/nodes/{node_key}/restart", tags=["nodes"])
async def restart_node(node_key: str, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    return await _node_action(node_key, "restart", db, user, request)


@router.post("/nodes/{node_key}/rollback", tags=["nodes"])
async def rollback_node(node_key: str, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    return await _node_action(node_key, "rollback", db, user, request)


@router.post("/nodes/{node_key}/drain", tags=["nodes"])
def drain_node(node_key: str, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    node.status = "DRAINING"
    record(db, user, "node.drain", "node", str(node.id), request_ip(request))
    db.commit()
    return {"ok": True, "node_key": node_key, "status": node.status}


@router.delete("/nodes/{node_key}", tags=["nodes"])
def remove_node(node_key: str, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> dict:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    record(db, user, "node.remove", "node", str(node.id), request_ip(request))
    db.delete(node)
    db.commit()
    return {"ok": True}


@router.get("/routes", tags=["routes"], response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Route]:
    return list(db.scalars(select(Route).order_by(desc(Route.is_active), desc(Route.score))).all())


@router.post("/routes", tags=["routes"], response_model=RouteOut)
def create_route(payload: RouteCreate, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    if db.scalar(select(Route).where(Route.name == payload.name)):
        raise HTTPException(status_code=409, detail="route_name_exists")
    route = Route(name=payload.name, node_keys=payload.node_keys, core=payload.core, protocol=payload.protocol, transport=payload.transport, config_enc=encrypt_secret(str(payload.config)))
    db.add(route)
    record(db, user, "route.create", "route", payload.name, request_ip(request))
    db.commit()
    db.refresh(route)
    return route


@router.post("/routes/{route_id}/activate", tags=["routes"])
def activate_route(route_id: int, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> dict:
    route = db.get(Route, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="route_not_found")
    for active in db.scalars(select(Route).where(Route.is_active.is_(True))).all():
        active.is_active = False
        active.status = "VERIFIED"
    route.is_active = True
    route.status = "ACTIVE"
    record(db, user, "route.activate", "route", str(route.id), request_ip(request))
    db.commit()
    return {"ok": True, "route_id": route.id, "status": route.status}


@router.get("/experiments", tags=["experiments"], response_model=None)
def list_experiments(limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Experiment]:
    return list(db.scalars(select(Experiment).order_by(desc(Experiment.created_at)).limit(min(max(limit, 1), 500))).all())


@router.post("/experiments", tags=["experiments"], response_model=None)
def create_experiment(payload: ExperimentCreate, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> Experiment:
    experiment = Experiment(**payload.model_dump(exclude={"metadata"}), metadata_json=payload.metadata)
    db.add(experiment)
    record(db, user, "experiment.create", "experiment", payload.candidate_id, request_ip(request))
    db.commit()
    db.refresh(experiment)
    return experiment


@router.post("/experiments/{experiment_id}/promote", tags=["experiments"])
def promote_experiment(experiment_id: int, level: str, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> dict:
    if level not in {"GOLDEN", "VERIFIED", "EXPERIMENTAL"}:
        raise HTTPException(status_code=422, detail="invalid_experiment_level")
    experiment = db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    experiment.level = level
    record(db, user, "experiment.promote", "experiment", str(experiment.id), request_ip(request), {"level": level})
    db.commit()
    return {"ok": True, "level": level}


@router.post("/optimizer/decide", tags=["optimizer"])
async def optimizer_decide(payload: OptimizerRequest, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN", "OPERATOR")) -> dict:
    gate = evaluate_gate(payload.current_score, payload.previous_score, payload.anomaly, payload.new_method, payload.route_failed, payload.optimization_requested)
    if not gate.call_ai:
        decision = {"action": "KEEP", "candidate_id": None, "confidence": 1.0, "reason": gate.reason}
        db.add(Decision(current_score=payload.current_score, proposed_score=payload.current_score, action="KEEP", candidate_id=None, reason=gate.reason, ai_called=False))
        db.commit()
        return {**decision, "ai_called": False}
    context = {"current_route": payload.current_route, "current_score": payload.current_score, "previous_score": payload.previous_score, "trigger": gate.reason, "candidates": payload.candidates[:20]}
    ai_called = False
    usage: dict = {}
    try:
        decision, usage = await analyze(context)
        ai_called = bool(settings.ai_enabled and settings.openai_api_key)
    except Exception:
        decision = {"action": "KEEP", "candidate_id": None, "confidence": 0, "reason": "AI unavailable; local safe policy retained the active route."}
    selected = next((candidate for candidate in payload.candidates if candidate.get("candidate_id") == decision.get("candidate_id")), None)
    if decision.get("action") in {"CANARY", "SWITCH"} and (not selected or not validate_candidate(selected, payload.current_score).valid):
        decision = {"action": "TEST", "candidate_id": selected.get("candidate_id") if selected else None, "confidence": 0, "reason": "Validator rejected the proposed production transition."}
    details = usage.get("input_tokens_details", {}) if isinstance(usage, dict) else {}
    db.add(Decision(current_score=payload.current_score, proposed_score=float(selected.get("score", payload.current_score)) if selected else payload.current_score, action=decision["action"], candidate_id=decision.get("candidate_id"), reason=decision["reason"], ai_called=ai_called, model=settings.openai_model if ai_called else "", input_tokens=int(usage.get("input_tokens", 0) or 0), cached_tokens=int(details.get("cached_tokens", 0) or 0), output_tokens=int(usage.get("output_tokens", 0) or 0)))
    record(db, user, "optimizer.decide", "optimizer", "", request_ip(request), {"action": decision["action"], "ai_called": ai_called})
    db.commit()
    return {**decision, "ai_called": ai_called, "usage": {"input_tokens": int(usage.get("input_tokens", 0) or 0), "cached_tokens": int(details.get("cached_tokens", 0) or 0), "output_tokens": int(usage.get("output_tokens", 0) or 0)}}


@router.get("/optimizer/decisions", tags=["optimizer"], response_model=None)
def optimizer_decisions(limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Decision]:
    return list(db.scalars(select(Decision).order_by(desc(Decision.created_at)).limit(min(max(limit, 1), 500))).all())


@router.get("/optimizer/candidates", tags=["optimizer"])
def optimizer_candidates(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    keys = [node.node_key for node in db.scalars(select(Node).where(Node.status.in_(["ONLINE", "REGISTERED"]))).all()]
    return {"candidates": generate(keys, settings.national_max_candidates_per_round), "mode": (db.get(SystemState, 1).mode if db.get(SystemState, 1) else "NORMAL")}


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> list[User]:
    return list(db.scalars(select(User).order_by(desc(User.id))).all())


@router.post("/users", response_model=UserOut, tags=["users"])
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), actor: User = role("SUPER_ADMIN", "ADMIN")) -> User:
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="username_exists")
    role_row = db.scalar(select(Role).where(Role.name == payload.role))
    if not role_row:
        raise HTTPException(status_code=422, detail="role_not_found")
    user = User(username=payload.username, email=payload.email, password_hash=hash_password(payload.password), is_active=payload.is_active, roles=[role_row])
    db.add(user)
    record(db, actor, "user.create", "user", payload.username, request_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), actor: User = role("SUPER_ADMIN", "ADMIN")) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user_not_found")
    if payload.email is not None:
        user.email = payload.email
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role:
        role_row = db.scalar(select(Role).where(Role.name == payload.role))
        if not role_row:
            raise HTTPException(status_code=422, detail="role_not_found")
        user.roles = [role_row]
    record(db, actor, "user.update", "user", str(user.id), request_ip(request))
    db.commit()
    db.refresh(user)
    return user


@router.get("/plans", tags=["billing"], response_model=None)
def list_plans(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Plan]:
    return list(db.scalars(select(Plan).order_by(Plan.name)).all())


@router.post("/plans", tags=["billing"], response_model=None)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> Plan:
    plan = Plan(**payload.model_dump())
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.get("/subscriptions", tags=["subscriptions"], response_model=None)
def list_subscriptions(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[Subscription]:
    return list(db.scalars(select(Subscription).order_by(desc(Subscription.created_at))).all())


@router.post("/subscriptions", tags=["subscriptions"])
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db), actor: User = role("SUPER_ADMIN", "ADMIN", "RESELLER")) -> dict:
    plan = db.get(Plan, payload.plan_id)
    target = db.get(User, payload.user_id)
    if not plan or not target:
        raise HTTPException(status_code=404, detail="user_or_plan_not_found")
    raw = random_token()
    sub = Subscription(user_id=target.id, plan_id=plan.id, token_hash=token_hash(raw), node_keys=payload.node_keys, expires_at=utcnow() + timedelta(days=plan.duration_days))
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"id": sub.id, "token": raw, "expires_at": sub.expires_at, "node_keys": sub.node_keys}


@router.post("/api-keys", tags=["auth"])
def create_api_key(name: str, scopes: list[str] | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    raw = "omk_" + random_token(32)
    key = ApiKey(user_id=user.id, name=name[:100], key_prefix=raw[:12], key_hash=token_hash(raw), scopes=scopes or [])
    db.add(key)
    record(db, user, "api_key.create", "api_key", key.key_prefix)
    db.commit()
    return {"id": key.id, "name": key.name, "key": raw, "warning": "Store this key now; it is not shown again."}


@router.get("/audit-logs", tags=["system"], response_model=None)
def audit_logs(limit: int = 100, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(min(max(limit, 1), 500))).all())


@router.get("/system/settings", tags=["system"])
def settings_list(db: Session = Depends(get_db), user: User = role("SUPER_ADMIN", "ADMIN")) -> list[dict]:
    rows = db.scalars(select(SystemSetting).order_by(SystemSetting.key)).all()
    return [{"key": row.key, "is_secret": row.is_secret, "updated_at": row.updated_at} for row in rows]


@router.put("/system/settings/{key}", tags=["system"])
def update_setting(key: str, payload: SystemSettingUpdate, request: Request, db: Session = Depends(get_db), user: User = role("SUPER_ADMIN")) -> dict:
    if key not in {"optimizer.enabled", "optimizer.min_score_change", "national_mode.enabled"}:
        raise HTTPException(status_code=422, detail="setting_not_editable")
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if not row:
        row = SystemSetting(key=key, value_enc=encrypt_secret(payload.value), is_secret=False)
        db.add(row)
    else:
        row.value_enc = encrypt_secret(payload.value)
    record(db, user, "system_setting.update", "system_setting", key, request_ip(request))
    db.commit()
    return {"ok": True, "key": key}


@router.get("/national-mode", tags=["system"])
def national_mode(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    state = national_engine.get_state(db)
    return {"mode": state.mode, "failures": state.international_failures, "successes": state.international_successes}


@router.get("/research", tags=["system"], response_model=None)
def research(limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[ResearchFinding]:
    return list(db.scalars(select(ResearchFinding).order_by(desc(ResearchFinding.created_at)).limit(min(max(limit, 1), 500))).all())
