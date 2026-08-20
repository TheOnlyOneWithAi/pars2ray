from datetime import datetime

from sqlalchemy import desc, select

from app.core.config import settings
from app.models.entities import Experiment, SystemState
from app.services.candidate_engine import generate


class NationalModeEngine:
    def get_state(self, db):
        state = db.get(SystemState, 1)
        if not state:
            state = SystemState(id=1, mode="NORMAL")
            db.add(state)
            db.commit()
            db.refresh(state)
        return state

    def update_connectivity(self, db, foreign_reachable: bool):
        state = self.get_state(db)
        if foreign_reachable:
            state.international_successes += 1
            state.international_failures = 0
            if (
                state.mode == "NATIONAL"
                and state.international_successes >= settings.national_recovery_threshold
            ):
                state.mode = "NORMAL"
        else:
            state.international_failures += 1
            state.international_successes = 0
            if (
                settings.national_mode_enabled
                and state.international_failures >= settings.national_failure_threshold
            ):
                state.mode = "NATIONAL"
        state.updated_at = datetime.utcnow()
        db.commit()
        return state

    def known_good(self, db, limit=30):
        query = (
            select(Experiment)
            .where(Experiment.level.in_(["GOLDEN", "VERIFIED"]))
            .order_by(desc(Experiment.score), desc(Experiment.created_at))
            .limit(limit)
        )
        return db.scalars(query).all()

    def fallback_candidates(self, node_keys):
        return generate(
            node_keys,
            settings.national_max_candidates_per_round,
            False,
        )


national_engine = NationalModeEngine()
