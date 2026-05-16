import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_write(
    db: Session,
    table: str,
    record_id: int,
    action: str,
    actor: str,
    changes: Optional[dict] = None,
) -> None:
    """Record a PHI write operation in the audit log.

    Flushes within the caller's open transaction so the audit row and the
    business record commit or roll back together. Never raises — a logging
    failure must not abort a clinical save.

    Args:
        action: "create" or "update"
        actor:  session username of the staff member performing the write
        changes: dict of {field: new_value} — omit fields that didn't change
    """
    from database import AuditLog
    try:
        entry = AuditLog(
            table_name=table,
            record_id=record_id,
            action=action,
            actor=actor,
            changes=json.dumps(changes, default=str) if changes else None,
        )
        db.add(entry)
        db.flush()
    except Exception as exc:
        logger.warning("Audit log failed (non-critical): %s", exc)
