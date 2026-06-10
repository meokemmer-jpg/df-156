import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# [CRUX-MK]
import importlib

m156 = importlib.import_module("156")
aggregate_pending_dashboard = m156.aggregate_pending_dashboard
write_report = m156.write_report


def test_df_156_aggregates_pending_and_detects_pareto_bottleneck(tmp_path):
    configs = [
        {
            "source": "df-alpha",
            "pending_phronesis_items": [
                {
                    "id": "p-1",
                    "title": "Need Martin input on roadmap",
                    "priority": "critical",
                    "wait_state": True,
                    "blocked_by": ["martin"],
                },
                {
                    "id": "p-2",
                    "title": "Clarify budget envelope",
                    "priority": "high",
                    "wait_state": True,
                    "blocked_by": ["finance", "martin"],
                },
            ],
            "decision_cards": [
                {
                    "id": "d-1",
                    "title": "Approve partner shortlist",
                    "state": "wait",
                    "priority": "medium",
                    "blocked_by": ["martin"],
                },
                {
                    "id": "d-2",
                    "title": "Already decided card",
                    "state": "done",
                    "priority": "critical",
                    "blocked_by": ["martin"],
                },
            ],
        },
        {
            "source": "df-beta",
            "pending_phronesis_items": [
                {
                    "id": "p-3",
                    "title": "Resolve legal review",
                    "priority": "low",
                    "wait_state": True,
                    "blocked_by": ["legal"],
                }
            ],
            "decision_cards": [
                {
                    "id": "d-3",
                    "title": "Wait for hiring signal",
                    "state": "wait",
                    "priority": "high",
                    "blocked_by": ["martin"],
                }
            ],
        },
    ]

    dashboard = aggregate_pending_dashboard(configs)

    assert dashboard["auto_decision"] is False
    assert dashboard["visibility_only"] is True
    assert dashboard["summary"]["total_pending_items"] == 5
    assert dashboard["summary"]["wait_state_items"] == 5
    assert dashboard["summary"]["by_priority_tier"] == {
        "tier-0": 1,
        "tier-1": 2,
        "tier-2": 1,
        "tier-3": 1,
    }

    ids = {item["id"] for item in dashboard["items"]}
    assert ids == {"p-1", "p-2", "p-3", "d-1", "d-3"}
    assert "d-2" not in ids

    top_bottleneck = dashboard["pareto_bottlenecks"][0]
    assert top_bottleneck["blocker"] == "martin"
    assert top_bottleneck["count"] == 4
    assert top_bottleneck["pareto_front"] is True

    report_path = write_report(configs, tmp_path / "reports")
    assert report_path.exists()
    assert report_path.name.startswith("df-156-")
    assert report_path.read_text(encoding="utf-8")

