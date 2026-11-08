from decimal import Decimal
from types import SimpleNamespace
import pytest
from sycophancy.budget import BudgetLedger, BudgetExceeded, usage_cost, estimate_cost


def model(model_id="gpt-6-luna"):
    return SimpleNamespace(model_id=model_id, max_tokens=512)


def response(**kwargs):
    return SimpleNamespace(input_tokens=100, output_tokens=200, cached_input_tokens=0,
                           cache_write_tokens=0, reasoning_tokens=150, service_tier="default", **kwargs)


def test_reasoning_already_in_output_not_double_billed():
    assert usage_cost("gpt-6-luna",100,200) == Decimal("0.00011")


def test_cache_categories_cost():
    expected = (Decimal(50)*2 + Decimal(20)*Decimal('.1') + Decimal(30)*Decimal('2.5') + 10*Decimal(10))/1_000_000
    assert usage_cost("gpt-6.1-sol",100,10,20,30) == expected
    with pytest.raises(ValueError):
        usage_cost("gpt-6-luna",10,10,11)


def test_shared_persistent_cap_and_settlement(tmp_path):
    path = tmp_path/'budget.json'
    ledger = BudgetLedger(path, .001)
    reservation = ledger.reserve(model(),"hello")
    assert ledger.summary()["unresolved_reserved_usd"] > .0001
    assert ledger.settle(reservation,response()) == pytest.approx(.00011)
    assert BudgetLedger(path,.001).summary()["observed_usage_cost_usd"] == pytest.approx(.00011)
    assert ledger.settle(reservation,response()) == pytest.approx(.00011)
    with pytest.raises(ValueError):
        BudgetLedger(path,8).summary()


def test_no_response_keeps_reservation_across_restart(tmp_path):
    path=tmp_path/'budget.json'
    ledger=BudgetLedger(path,.0005)
    ledger.reserve(model(),"hello")
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path,.0005).reserve(model(),"hello")
    assert ledger.summary()["observed_usage_cost_usd"] == 0
    assert ledger.summary()["unresolved_reserved_usd"] > 0


def test_unknown_model_rejected_before_budget_changes(tmp_path):
    ledger=BudgetLedger(tmp_path/'budget.json',8)
    with pytest.raises(ValueError):
        ledger.reserve(model("unknown"),"hello")
    assert not ledger.path.exists()


def test_full_output_reserved_including_reasoning():
    assert estimate_cost(model("gpt-6-astra"),"hi") > 512*50/1_000_000


def test_reservation_audit_rejects_missing_ledger(tmp_path):
    ledger=BudgetLedger(tmp_path/'budget.json',8)
    with pytest.raises(ValueError,match="missing"):
        ledger.validate_reservations(["historic-attempt"])


def test_exceeded_reservation_stops_subsequent_process(tmp_path):
    path=tmp_path/'budget.json'
    ledger=BudgetLedger(path,8)
    reservation=ledger.reserve(model(),"hello")
    huge=SimpleNamespace(input_tokens=100,output_tokens=10000,cached_input_tokens=0,cache_write_tokens=0,
                         service_tier="default",reasoning_tokens=9000)
    with pytest.raises(BudgetExceeded):
        ledger.settle(reservation,huge)
    with pytest.raises(BudgetExceeded,match="audit"):
        BudgetLedger(path,8).reserve(model(),"next")


@pytest.mark.parametrize("input_tokens,output_tokens", [(True,3),(-1,3),(1,None),(1,2.5)])
def test_bad_usage_rejected(input_tokens,output_tokens):
    with pytest.raises(ValueError):
        usage_cost("gpt-6-luna",input_tokens,output_tokens)
