"""Universal Test-Template fuer Welle-25 DFs (DF-113 bis DF-137) [CRUX-MK]"""
import importlib.util, sys, os, re
from pathlib import Path

DF_DIR = Path(__file__).parent.parent
DF_NAME = "df-156"  # wird substituiert pro DF
ENGINE = DF_DIR / f"{DF_NAME}-engine.py"


def _load():
    spec = importlib.util.spec_from_file_location("engine", str(ENGINE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["engine"] = mod  # Python 3.14 dataclasses Workaround
    spec.loader.exec_module(mod)
    return mod


def test_engine_imports():
    """Engine kann ohne Fehler geladen werden."""
    mod = _load()
    assert hasattr(mod, "collect_tracker_output")


def test_iso_now():
    mod = _load()
    assert hasattr(mod, "iso_now")
    ts = mod.iso_now()
    assert "T" in ts and ":" in ts


def test_file_stable_helper():
    mod = _load()
    assert hasattr(mod, "_file_stable")
    # Non-existent file -> not stable
    assert not mod._file_stable(Path("/nonexistent/abc"))


def test_k16_lock_acquire_release():
    """K16: Concurrent-Spawn-Mutex via acquire_lock_with_identity + release_lock."""
    mod = _load()
    assert hasattr(mod, "acquire_lock_with_identity")
    assert hasattr(mod, "release_lock")
    mod.release_lock()
    assert mod.acquire_lock_with_identity()
    mod.release_lock()


def test_k17_pav_detects_missing_anchor():
    """K17: Pre-Action-Verification erkennt fehlende Anker."""
    mod = _load()
    assert hasattr(mod, "k17_pre_action_verification")
    res = mod.k17_pre_action_verification([Path("/nonexistent/anchor")])
    assert isinstance(res, dict)
    # Either "ok"=False oder "missing_anchors" oder "failed_anchors" key
    assert res.get("ok") is False or len(res.get("missing_anchors", res.get("failed_anchors", []))) > 0


def test_mock_mode_default():
    """Activation-Gate default false (Mock-Mode)."""
    mod = _load()
    assert hasattr(mod, "_is_real_api_enabled")
    # Clear any matching env var
    for k in list(os.environ.keys()):
        if k.startswith("DF_") and "REAL_API_ENABLED" in k:
            os.environ.pop(k, None)
    assert mod._is_real_api_enabled() is False


def test_decision_keyword_scanner_exists():
    """Patch P4: Q_0-Sperr-Negative-Scan vorhanden."""
    mod = _load()
    assert hasattr(mod, "scan_output_for_decision_keywords")
    assert hasattr(mod, "assert_no_decision_keywords")


def test_decision_keyword_scanner_detects_verb_stems():
    """FINDING-2-FIX: Verb-Stem-Pattern detected conjugated forms."""
    mod = _load()
    test_phrases = ["Wir entscheiden uns", "empfehlen wir", "Du solltest"]
    detected = sum(1 for p in test_phrases if mod.scan_output_for_decision_keywords(p))
    assert detected >= 1, f"Stem-Pattern detected {detected}/3 phrases"


def test_collect_tracker_output_returns_valid():
    """Engine produziert valid TrackerOutput ohne Decision-Keywords."""
    mod = _load()
    out = mod.collect_tracker_output()
    assert out is not None
    assert hasattr(out, "welle") or hasattr(out, "df") or hasattr(out, "iso_timestamp")


def test_tracker_output_no_decision_keywords():
    """Q_0-Sperr enforced via assert_no_decision_keywords im collect."""
    mod = _load()
    # collect_tracker_output ruft assert_no_decision_keywords intern auf
    # Wenn keine Exception -> OK
    try:
        out = mod.collect_tracker_output()
        assert out is not None
    except (ValueError, AssertionError) as e:
        if "Q_0" in str(e) or "decision" in str(e).lower():
            assert False, f"Q_0-Sperr triggered im collect: {e}"
        raise


def test_main_returns_exit_code():
    """main() returns int (0 normal, 3 lock-failed)."""
    mod = _load()
    assert hasattr(mod, "main")
    mod.release_lock()
    rc = mod.main()
    assert rc in (0, 3, 1)  # 0=ok, 3=lock-fail, 1=non-compliant


# K_0/Q_0-Sperr NEGATIVE-Tests (3)
def test_no_auto_decision_in_source():
    """Source darf keine Auto-Decision-Patterns enthalten."""
    src = ENGINE.read_text(encoding="utf-8").lower()
    forbidden = ["def auto_decide", "def auto_recommend", "def auto_apply", "def execute_decision"]
    for f in forbidden:
        assert f not in src, f"Forbidden auto-decision: {f}"


def test_no_real_api_call_without_env():
    """Real-API-Calls nur via _is_real_api_enabled gated."""
    mod = _load()
    os.environ.pop(f"DF_{DF_NAME.replace('df-', '')}_REAL_API_ENABLED", None)
    assert not mod._is_real_api_enabled()


def test_engine_handles_lock_collision():
    """Lock-Collision: 2 Acquires hintereinander, 2. failed."""
    mod = _load()
    mod.release_lock()
    assert mod.acquire_lock_with_identity()
    # 2nd acquire should fail (lock already held)
    assert not mod.acquire_lock_with_identity()
    mod.release_lock()
