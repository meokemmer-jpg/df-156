from __future__ import annotations

import json
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
    wait_state: bool
    priority_tier: str
    blocked_by: tuple[str, ...]


def classify_priority_tier(raw_priority: Any) -> str:
    value = str(raw_priority or "").strip().lower()
    if value in {"critical", "p0", "tier-0", "t0"}:
        return "tier-0"
    if value in {"high", "p1", "tier-1", "t1"}:
        return "tier-1"
    if value in {"medium", "p2", "tier-2", "t2"}:
        return "tier-2"
    return "tier-3"


def normalize_pending_items(configs: Iterable[dict[str, Any]]) -> list[PendingItem]:
    items: list[PendingItem] = []

    for config in configs:
        source = str(config.get("source", "unknown"))

        for raw in config.get("pending_phronesis_items", []):
            items.append(
                PendingItem(
                    source=source,
                    item_id=str(raw["id"]),
                    title=str(raw.get("title", "")),
                    kind="pending-phronesis",
                    wait_state=bool(raw.get("wait_state", True)),
                    priority_tier=classify_priority_tier(raw.get("priority")),
                    blocked_by=tuple(str(x) for x in raw.get("blocked_by", [])),
                )
            )

        for raw in config.get("decision_cards", []):
            if str(raw.get("state", "")).lower() != "wait":
                continue
            items.append(
                PendingItem(
                    source=source,
                    item_id=str(raw["id"]),
                    title=str(raw.get("title", "")),
                    kind="decision-card",
                    wait_state=True,
                    priority_tier=classify_priority_tier(raw.get("priority")),
                    blocked_by=tuple(str(x) for x in raw.get("blocked_by", [])),
                )
            )

    return items


def detect_pareto_bottlenecks(items: Iterable[PendingItem]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in items:
        for blocker in item.blocked_by:
            counts[blocker] = counts.get(blocker, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    total = sum(counts.values())

    bottlenecks: list[dict[str, Any]] = []
    running = 0
    for blocker, count in ranked:
        running += count
        share = 0.0 if total == 0 else count / total
        cumulative_share = 0.0 if total == 0 else running / total
        bottlenecks.append(
            {
                "blocker": blocker,
                "count": count,
                "share": round(share, 4),
                "cumulative_share": round(cumulative_share, 4),
                "pareto_front": cumulative_share <= 0.8 or len(bottlenecks) == 0,
            }
        )
    return bottlenecks


def aggregate_pending_dashboard(configs: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = normalize_pending_items(configs)

    by_priority = {"tier-0": 0, "tier-1": 0, "tier-2": 0, "tier-3": 0}
    for item in items:
        by_priority[item.priority_tier] += 1

    return {
        "date": date.today().isoformat(),
        "mission": "DF-156 PVG-Phronesis-Pending-Aggregator",
        "auto_decision": False,
        "visibility_only": True,
        "summary": {
            "total_pending_items": len(items),
            "wait_state_items": sum(1 for item in items if item.wait_state),
            "by_priority_tier": by_priority,
        },
        "items": [
            {
                "source": item.source,
                "id": item.item_id,
                "title": item.title,
                "kind": item.kind,
                "wait_state": item.wait_state,
                "priority_tier": item.priority_tier,
                "blocked_by": list(item.blocked_by),
            }
            for item in items
        ],
        "pareto_bottlenecks": detect_pareto_bottlenecks(items),
    }


def write_report(configs: Iterable[dict[str, Any]], reports_dir: str | Path = "reports") -> Path:
    report = aggregate_pending_dashboard(configs)
    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    output_path = reports_path / f"df-156-{report['date']}.json"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output_path
# [CRUX-MK]
