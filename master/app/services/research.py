from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import ResearchFinding

REPOSITORIES = {"xray": "XTLS/Xray-core", "sing-box": "SagerNet/sing-box"}


async def fetch_releases() -> list[dict]:
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=15, headers={"Accept": "application/vnd.github+json", "User-Agent": "Pars2Ray-Enterprise/2.2"}) as client:
        for source, repository in REPOSITORIES.items():
            response = await client.get(f"https://api.github.com/repos/{repository}/releases/latest")
            if response.status_code != 200:
                continue
            item = response.json()
            results.append({"source": source, "version": item.get("tag_name", ""), "title": (item.get("name") or item.get("tag_name", ""))[:255], "notes": (item.get("body") or "")[:5000], "url": item.get("html_url", "")})
    return results


async def refresh(db: Session) -> list[ResearchFinding]:
    added: list[ResearchFinding] = []
    for item in await fetch_releases():
        if not item["version"] or db.scalar(select(ResearchFinding).where(ResearchFinding.source == item["source"], ResearchFinding.version == item["version"])):
            continue
        finding = ResearchFinding(**item)
        db.add(finding)
        added.append(finding)
    db.commit()
    return added
