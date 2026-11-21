"""Deterministic refund checks; the LLM is disabled so only application logic is tested.

Run: .venv/bin/python -m pytest tests  (or)  .venv/bin/python tests/test_refund.py
"""

import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import refund_agent
import refund_tools
from refund_agent import RefundAgent, parse_confirmation
from refund_data import USERS, RefundStore
from refund_tools import validate_refund

UID = "user_123"


def _no_llm(*_, **__):
    raise RuntimeError("LLM disabled in tests")


refund_agent.get_llm = _no_llm


def store_with(**changes_by_id):
    users = deepcopy(USERS)
    for r in users[UID]["recharges"]:
        r.update(changes_by_id.get(r["recharge_id"], {}))
    return RefundStore(users)


def spy_process_refund():
    calls = []
    original = refund_tools.process_refund

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    refund_agent.process_refund = spy
    return calls


def test_scenario1_successful_refund_needs_confirmation():
    calls = spy_process_refund()
    store = RefundStore()
    agent = RefundAgent(store)
    reply = agent.handle("I want a refund of ₹499.")
    assert agent.state == "awaiting_confirmation" and reply.confirm_amount == 499
    assert calls == []
    reply = agent.handle("Yes, proceed")
    assert agent.state == "refund_processed" and "ref_" in reply.text
    assert len(calls) == 1
    assert store.users[UID]["recharges"][1]["refund_status"] == "refunded"
    assert store.users[UID]["recharges"][0]["refund_status"] == "not_refunded"


def test_scenario2_amount_exceeds_recharge():
    calls = spy_process_refund()
    agent = RefundAgent(RefundStore())
    reply = agent.handle("Give me a refund of ₹2,000.")
    assert agent.state == "refund_rejected" and "exceeds" in reply.text
    assert calls == []


def test_scenario3_recharge_too_old():
    calls = spy_process_refund()
    agent = RefundAgent(store_with(rch_457={"recharge_age_days": 15}))
    reply = agent.handle("I want a refund of ₹499.")
    assert agent.state == "refund_rejected" and "7-day" in reply.text
    assert calls == []


def test_scenario4_already_refunded():
    calls = spy_process_refund()
    agent = RefundAgent(store_with(rch_457={"refund_status": "refunded"}))
    reply = agent.handle("I want a refund of ₹499.")
    assert agent.state == "refund_rejected" and "already been refunded" in reply.text
    assert calls == []


def test_scenario6_above_limit_goes_to_support():
    calls = spy_process_refund()
    store = RefundStore()
    agent = RefundAgent(store)
    reply = agent.handle("I want a refund of ₹999.")
    assert agent.state == "refund_submitted_for_review"
    assert "submitted to our Support Team" in reply.text and reply.confirm_amount is None
    assert not any(w in reply.text.lower() for w in ("approved", "rejected", "has been processed"))
    assert calls == [] and len(store.support_requests) == 1
    assert store.users[UID]["recharges"][0]["refund_status"] == "not_refunded"


def test_refunding_one_recharge_leaves_other_refundable():
    store = RefundStore()
    agent = RefundAgent(store)
    agent.handle("I want a refund of ₹499.")
    agent.handle("Yes, proceed")
    assert validate_refund(store, UID, 999)["eligible"]
    assert not validate_refund(store, UID, 499)["eligible"]


def test_rejection_and_ambiguous_confirmation_do_not_execute():
    calls = spy_process_refund()
    agent = RefundAgent(RefundStore())
    agent.handle("I want a refund of ₹499.")
    agent.handle("maybe")
    assert agent.state == "awaiting_confirmation" and calls == []
    reply = agent.handle("No")
    assert agent.state == "refund_cancelled" and calls == [] and "No refund" in reply.text


def test_missing_amount_with_two_recharges_asks_which():
    agent = RefundAgent(RefundStore())
    reply = agent.handle("I want a refund.")
    assert agent.state == "awaiting_amount"
    assert "₹999 and ₹499" in reply.text
    agent.handle("499")
    assert agent.state == "awaiting_confirmation" and agent.pending_amount == 499


def test_missing_amount_with_single_eligible_offers_it():
    agent = RefundAgent(store_with(rch_456={"refund_status": "refunded"}))
    reply = agent.handle("I want a refund.")
    assert agent.state == "awaiting_confirmation" and reply.confirm_amount == 499


def test_zero_amount_rejected():
    assert not validate_refund(RefundStore(), UID, 0)["eligible"]


def test_partial_amount_selects_most_recent_covering_recharge():
    result = validate_refund(RefundStore(), UID, 300)
    assert result["eligible"] and result["recharge_id"] == "rch_457"


def test_exact_amount_identifies_refunded_recharge():
    result = validate_refund(store_with(rch_457={"refund_status": "refunded"}), UID, 499)
    assert not result["eligible"] and result["recharge_id"] == "rch_457"


def test_process_refund_refuses_above_limit_even_if_called():
    store = RefundStore()
    result = refund_tools.process_refund(store, UID, 999)
    assert not result["success"]
    assert store.users[UID]["recharges"][0]["refund_status"] == "not_refunded"


def test_confirmation_parsing():
    for yes in ("Yes, proceed", "yes", "Confirm", "go ahead", "Yes please"):
        assert parse_confirmation(yes) == "yes", yes
    for no in ("No", "cancel", "don't do it", "no thanks"):
        assert parse_confirmation(no) == "no", no
    for unclear in ("maybe", "I think so", "hmm", "what?", "ok"):
        assert parse_confirmation(unclear) == "ambiguous", unclear


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print(f"\n{len(tests)} passed")
