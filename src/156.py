from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PendingItem:
    source: str
    item_id: str
    title: str
    kind: str
    priority_tier: str
    wait_state: bool
    blocked_by: tuple[str, ...]


def classify_priority_tier(priority_score: int) -> str:
    if priority_score >= 80:
        return "T1"
    if priority_score >= 50:
        return "T2"
    return "T3"


def _normalize_pending_items(configs: Iterable[dict[str, Any]]) -> list[PendingItem]:
    items: list[PendingItem] = []

    for config in configs:
        source = str(config.get("source", "unknown"))

        for raw in config.get("pending_phronesis_items", []):
            items.append(
                PendingItem(
                    source=source,
                    item_id=str(raw["id"]),
                    title=str(raw["title"]),
                    kind="pending_phronesis",
                    priority_tier=classify_priority_tier(int(raw.get("priority_score", 0))),
                    wait_state=bool(raw.get("wait_state", True)),
                    blocked_by=tuple(str(x) for x in raw.get("blocked_by", ())),
                )
            )

        for raw in config.get("decision_cards", []):
            if str(raw.get("state", "")).lower() != "wait":
                continue
            items.append(
                PendingItem(
                    source=source,
                    item_id=str(raw["id"]),
                    title=str(raw["title"]),
                    kind="decision_card",
                    priority_tier=classify_priority_tier(int(raw.get("priority_score", 0))),
                    wait_state=True,
                    blocked_by=tuple(str(x) for x in raw.get("blocked_by", ())),
                )
            )

    return items


def aggregate_pending_visibility(configs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = _normalize_pending_items(configs)

    tier_counts = Counter(item.priority_tier for item in items)
    blocker_counts: dict[str, int] = defaultdict(int)
    for item in items:
        for blocker in item.blocked_by:
            blocker_counts[blocker] += 1

    pareto_blockers = sorted(
        (
            {"blocker": blocker, "count": count}
            for blocker, count in blocker_counts.items()
        ),
        key=lambda x: (-x["count"], x["blocker"]),
    )

    return {
        "auto_decision": False,
        "summary": {
            "total_pending_items": len(items),
            "wait_state_items": sum(1 for item in items if item.wait_state),
            "by_priority_tier": {
                "T1": tier_counts.get("T1", 0),
                "T2": tier_counts.get("T2", 0),
                "T3": tier_counts.get("T3", 0),
            },
        },
        "items": [
            {
                "source": item.source,
                "id": item.item_id,
                "title": item.title,
                "kind": item.kind,
                "priority_tier": item.priority_tier,
                "wait_state": item.wait_state,
                "blocked_by": list(item.blocked_by),
            }
            for item in items
        ],
        "pareto_engpass": pareto_blockers,
    }


def build_report(configs: Iterable[dict[str, Any]], report_date: date | None = None) -> dict[str, Any]:
    report_date = report_date or date.today()
    report = aggregate_pending_visibility(configs)
    report["report_date"] = report_date.isoformat()
    return report


def write_report(
    configs: Iterable[dict[str, Any]],
    output_dir: str | Path = "reports",
    report_date: date | None = None,
) -> Path:
    report = build_report(configs, report_date=report_date)
    output_path = Path(output_dir) / f"df-156-{report['report_date']}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


__all__ = [
    "PendingItem",
    "aggregate_pending_visibility",
    "build_report",
    "classify_priority_tier",
    "write_report",
]
# [CRUX-MK]
