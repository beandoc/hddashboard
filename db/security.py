import os
import hmac as _hmac
import hashlib as _hashlib
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# PHI PSEUDONYMISATION
#
# compute_patient_id_hash returns an HMAC-SHA256 hex digest of the integer
# patient_id.  Store this on AuditLog and MLPrediction rows so analytics /
# reporting can correlate records without ever joining back to patients.id.
#
# Key priority: AUDIT_HMAC_KEY > SECRET_KEY > "" (returns None when absent).
# ─────────────────────────────────────────────────────────────────────────────

def _audit_hmac_key() -> bytes:
    raw = os.environ.get("AUDIT_HMAC_KEY") or os.environ.get("SECRET_KEY") or ""
    return raw.encode()


def compute_patient_id_hash(patient_id: Optional[int]) -> Optional[str]:
    """HMAC-SHA256(patient_id) — safe for audit/ML tables, never re-linkable to PHI by itself."""
    if patient_id is None:
        return None
    key = _audit_hmac_key()
    if not key:
        return None
    return _hmac.new(key, str(patient_id).encode(), _hashlib.sha256).hexdigest()
