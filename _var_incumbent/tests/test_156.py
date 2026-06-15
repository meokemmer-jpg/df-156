import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
# [CRUX-MK]
# NOTE: `from 156 import ...` is invalid Python syntax because module names in import
# statements must be valid identifiers. This test uses importlib to load `156.py`
# while still testing the real module file the spec requires.

import importlib

m156 = importlib.import_module("156")
aggregate_pending_visibility = m156.aggregate_pending_visibility
build_report = m156.build_report
write_report = m156.write_report


def test_aggregate_pending_visibility_and_report_write(tmp_path):
    configs = [
        {
            "source": "df-a",
            "pending_phronesis_items": [
                {
                    "id": "p-1",
                    "title": "Escalate supplier choice",
                    "priority_score": 90,
                    "wait_state": True,
                    "blocked_by": ["martin", "budget"],
                },
                {
                    "id": "p-2",
                    "title": "Confirm launch window",
                    "priority_score": 55,
                    "wait_state": True,
                    "blocked_by": ["martin"],
                },
            ],
            "decision_cards": [
                {
                    "id": "d-1",
                    "title": "Approve vendor",
                    "state": "wait",
                    "priority_score": 85,
                    "blocked_by": ["budget"],
                },
                {
                    "id": "d-2",
                    "title": "Ignore done decision",
                    "state": "done",
                    "priority_score": 99,
                    "blocked_by": ["nobody"],
                },
            ],
        },
        {
            "source": "df-b",
            "pending_phronesis_items": [
                {
                    "id": "p-3",
                    "title": "Review legal wording",
                    "priority_score": 10,
                    "wait_state": True,
                    "blocked_by": ["legal"],
                }
            ],
            "decision_cards": [],
        },
    ]

    result = aggregate_pending_visibility(configs)

    assert result["auto_decision"] is False
    assert result["summary"]["total_pending_items"] == 4
    assert result["summary"]["wait_state_items"] == 4
    assert result["summary"]["by_priority_tier"] == {"T1": 2, "T2": 1, "T3": 1}

    ids = {item["id"] for item in result["items"]}
    assert ids == {"p-1", "p-2", "p-3", "d-1"}
    assert "d-2" not in ids

    assert result["pareto_engpass"][0] == {"blocker": "budget", "count": 2}
    assert result["pareto_engpass"][1] == {"blocker": "martin", "count": 2}
    assert result["pareto_engpass"][2] == {"blocker": "legal", "count": 1}

    report = build_report(configs)
    assert "report_date" in report
    assert report["summary"]["total_pending_items"] == 4

    output_path = write_report(configs, output_dir=tmp_path, report_date=__import__("datetime").date(2026, 6, 14))
    assert output_path.name == "df-156-2026-06-14.json"
    assert output_path.exists()

    written = output_path.read_text(encoding="utf-8")
    assert '"auto_decision": false' in written
    assert '"total_pending_items": 4' in written

