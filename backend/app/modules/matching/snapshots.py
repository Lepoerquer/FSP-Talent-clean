"""Selection Snapshots Management.

Allows employers to tweak filters (salary, grade, format, skills) and preserve
the ranked candidate recommendations state as permanent snapshots so they can return
to previous searches without losing candidates or ranking history.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.company import SelectionSnapshot, ShortlistItem


def compute_filters_hash(filters: dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash of query filters."""
    normalized_json = json.dumps(filters, sort_keys=True, default=str)
    return hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()[:32]


class SelectionSnapshotService:
    """Service to create, store and restore selection snapshots and shortlists."""

    @classmethod
    def save_snapshot(
        cls,
        db: Session,
        need_id: str,
        filters: dict[str, Any],
        ranked_candidates: list[dict[str, Any]],
    ) -> SelectionSnapshot:
        """Saves a selection snapshot with its ranked candidates and shortlists."""
        filters_hash = compute_filters_hash(filters)

        snapshot = SelectionSnapshot(
            need_id=need_id,
            query_filters_hash=filters_hash,
            ranked_candidates_payload=ranked_candidates,
            created_at=datetime.now(timezone.utc),
        )
        db.add(snapshot)
        db.flush()

        # Create ShortlistItem records for top candidates (up to 20)
        for cand in ranked_candidates[:20]:
            cand_id = cand.get("candidate_id") or cand.get("candidate_card", {}).get("id")
            if not cand_id:
                continue

            shortlist_item = ShortlistItem(
                snapshot_id=snapshot.id,
                candidate_profile_id=cand_id,
                score=float(cand.get("total_score", 0.0)),
                rank=int(cand.get("rank", 1)),
                explanation=cand.get("bullet_points", []),
                created_at=datetime.now(timezone.utc),
            )
            db.add(shortlist_item)

        db.commit()
        db.refresh(snapshot)
        return snapshot

    @classmethod
    def get_latest_snapshot(cls, db: Session, need_id: str) -> SelectionSnapshot | None:
        """Retrieves the most recent snapshot for a need."""
        return (
            db.query(SelectionSnapshot)
            .filter(SelectionSnapshot.need_id == need_id)
            .order_by(SelectionSnapshot.created_at.desc())
            .first()
        )

    @classmethod
    def get_snapshot_by_id(cls, db: Session, snapshot_id: str) -> SelectionSnapshot | None:
        """Retrieves a specific snapshot by its unique ID."""
        return db.query(SelectionSnapshot).filter(SelectionSnapshot.id == snapshot_id).first()

    @classmethod
    def list_snapshots(cls, db: Session, need_id: str) -> list[SelectionSnapshot]:
        """Lists all snapshots saved for an employer's need."""
        return (
            db.query(SelectionSnapshot)
            .filter(SelectionSnapshot.need_id == need_id)
            .order_by(SelectionSnapshot.created_at.desc())
            .all()
        )
