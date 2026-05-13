"""PVG-Phronesis-Pending-Aggregator DF-156 engine."""

import re
import os
import json
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime, timezone

DF_DIR = Path(__file__).parent
LOCK_DIR = Path("/tmp/df-156.lock")
DF_ID = "156"
DECISION_KEYWORDS_REGEX = re.compile(
    r"\b(entscheid[a-z]*|empfehl(?:e|en|t|st)|sollt(?:e|en|est)|recommend[a-z]*|decid[a-z]*|advis[a-z]*|propos[a-z]*)\b",
    re.IGNORECASE,
)

_LOCK_IDENTITY = f"{os.getpid()}:{time.time_ns()}"


@dataclass
class TrackerOutput:
    welle: str = "25"
    df: str = "DF-156"
    iso_timestamp: str = ""
    source: str = "mock"
    pending_items_total: int = 0
    pending_per_domain: dict = field(default_factory=dict)
    oldest_pending: list = field(default_factory=list)
    urgent_pending: list = field(default_factory=list)
    average_age_days: float = 0


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _file_stable(path, min_age_sec=300) -> bool:
    p = Path(path)
    try:
        st = p.stat()
    except FileNotFoundError:
        return False
    if not p.is_file():
        return False
    return (time.time() - st.st_mtime) >= min_age_sec


def acquire_lock_with_identity() -> bool:
    stale_after_sec = 6 * 60 * 60

    try:
        LOCK_DIR.mkdir(mode=0o700)
        (LOCK_DIR / "identity").write_text(_LOCK_IDENTITY, encoding="utf-8")
        return True
    except FileExistsError:
        pass

    try:
        age = time.time() - LOCK_DIR.stat().st_mtime
    except FileNotFoundError:
        return acquire_lock_with_identity()

    if age <= stale_after_sec:
        return False

    try:
        identity = LOCK_DIR / "identity"
        if identity.exists():
            identity.unlink()
        LOCK_DIR.rmdir()
    except OSError:
        return False

    try:
        LOCK_DIR.mkdir(mode=0o700)
        (LOCK_DIR / "identity").write_text(_LOCK_IDENTITY, encoding="utf-8")
        return True
    except FileExistsError:
        return False


def release_lock() -> None:
    try:
        identity_path = LOCK_DIR / "identity"
        identity = identity_path.read_text(encoding="utf-8").strip()
        if identity != _LOCK_IDENTITY:
            return
        identity_path.unlink(missing_ok=True)
        LOCK_DIR.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        return


def k17_pre_action_verification(anchors) -> dict:
    env_tag = os.environ.get("DF_156_ENV_TAG", "local")
    missing = []

    for anchor in anchors or []:
        if isinstance(anchor, Path):
            exists = anchor.exists()
            label = str(anchor)
        else:
            label = str(anchor)
            exists = bool(os.environ.get(label)) or (DF_DIR / label).exists()
        if not exists:
            missing.append(label)

    return {
        "ok": not missing,
        "missing_anchors": missing,
        "env_tag": env_tag,
    }


def _is_real_api_enabled() -> bool:
    return os.environ.get("DF_156_REAL_API_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def scan_output_for_decision_keywords(text) -> list:
    if text is None:
        return []
    return sorted({m.group(0).lower() for m in DECISION_KEYWORDS_REGEX.finditer(str(text))})


def assert_no_decision_keywords(output) -> None:
    if not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False, sort_keys=True)
    hits = scan_output_for_decision_keywords(output)
    if hits:
        raise ValueError(f"Q_0/K_0 blocked terms present: {', '.join(hits)}")


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_pending_items_from_reports() -> list:
    pending = []
    reports_dir = DF_DIR / "reports"
    if not reports_dir.exists():
        return pending

    for path in sorted(reports_dir.glob("*.json")):
        if path.name.startswith("df-156-") or not _file_stable(path, min_age_sec=1):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        items = payload.get("pending_items")
        if isinstance(items, list):
            pending.extend(item for item in items if isinstance(item, dict))
        elif payload.get("status") == "pending":
            pending.append(payload)

    return pending


def _summarize_pending_items(items) -> TrackerOutput:
    now = datetime.now(timezone.utc)
    per_domain = {}
    ages = []

    normalized = []
    for index, item in enumerate(items):
        domain = str(item.get("domain") or item.get("df") or "unknown")
        created = (
            item.get("created_at")
            or item.get("iso_timestamp")
            or item.get("timestamp")
            or item.get("date")
        )
        created_dt = _parse_iso_datetime(created)
        age_days = 0.0
        if created_dt:
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - created_dt).total_seconds() / 86400)
            ages.append(age_days)

        urgency = str(item.get("urgency") or item.get("priority") or "").lower()
        entry = {
            "id": str(item.get("id") or item.get("key") or f"pending-{index + 1}"),
            "domain": domain,
            "age_days": round(age_days, 3),
        }
        if urgency in {"urgent", "high", "critical", "p0", "p1"}:
            entry["urgency"] = urgency

        per_domain[domain] = per_domain.get(domain, 0) + 1
        normalized.append(entry)

    oldest = sorted(normalized, key=lambda x: x.get("age_days", 0), reverse=True)[:10]
    urgent = [item for item in normalized if "urgency" in item][:10]

    return TrackerOutput(
        iso_timestamp=iso_now(),
        source="real" if _is_real_api_enabled() else "mock",
        pending_items_total=len(normalized),
        pending_per_domain=dict(sorted(per_domain.items())),
        oldest_pending=oldest,
        urgent_pending=urgent,
        average_age_days=round(sum(ages) / len(ages), 3) if ages else 0,
    )


def collect_tracker_output() -> TrackerOutput:
    if not _is_real_api_enabled():
        return TrackerOutput(
            iso_timestamp=iso_now(),
            source="mock",
            pending_items_total=0,
            pending_per_domain={},
            oldest_pending=[],
            urgent_pending=[],
            average_age_days=0,
        )

    return _summarize_pending_items(_load_pending_items_from_reports())


def main() -> int:
    if not acquire_lock_with_identity():
        return 3

    try:
        anchors = [DF_DIR]
        pav = k17_pre_action_verification(anchors)
        if not pav.get("ok"):
            return 3

        tracker_output = collect_tracker_output()
        report = {
            "df-156": asdict(tracker_output),
            "k17_pav": pav,
        }
        assert_no_decision_keywords(report)

        reports_dir = DF_DIR / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        date_tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_path = reports_dir / f"df-156-{date_tag}.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    sys.exit(main())