from datetime import datetime
from sqlalchemy import select, desc
from app.models.entities import SystemState, Experiment
from app.core.config import settings
from app.services.candidate_engine import generate

class NationalModeEngine:
    def get_state(self, db):
        s=db.get(SystemState,1)
        if not s:
            s=SystemState(id=1,mode='NORMAL'); db.add(s); db.commit(); db.refresh(s)
        return s
    def update_connectivity(self, db, foreign_reachable: bool):
        s=self.get_state(db)
        if foreign_reachable:
            s.international_successes += 1; s.international_failures=0
            if s.mode=='NATIONAL' and s.international_successes>=settings.national_recovery_threshold: s.mode='NORMAL'
        else:
            s.international_failures += 1; s.international_successes=0
            if settings.national_mode_enabled and s.international_failures>=settings.national_failure_threshold: s.mode='NATIONAL'
        s.updated_at=datetime.utcnow(); db.commit(); return s
    def known_good(self, db, limit=30):
        q=select(Experiment).where(Experiment.level.in_(['GOLDEN','VERIFIED'])).order_by(desc(Experiment.score),desc(Experiment.created_at)).limit(limit)
        return db.scalars(q).all()
    def fallback_candidates(self, node_keys):
        return generate(node_keys,settings.national_max_candidates_per_round,False)

national_engine=NationalModeEngine()
