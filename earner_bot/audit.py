"""
audit.py — Ouroboros Bot 3.1 Audit Logger
Logs every bot event to JSONL for complete traceability.
"""
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any

AUDIT_FILE = os.path.join("output", "audit_log.jsonl")


def audit(event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """
    Append a timestamped event to the audit log.
    Uses None default instead of mutable {} to avoid shared-state bugs.
    """
    entry: Dict[str, Any] = {
        "ts":    datetime.now(timezone.utc).isoformat(),
        "event": event_type,
    }
    if data:
        entry.update(data)
    os.makedirs("output", exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")
