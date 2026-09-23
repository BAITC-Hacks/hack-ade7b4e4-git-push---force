from app import tools


def test_loan_payment_known_value():
    r = tools.loan_payment(1_000_000, 12, 12)
    assert r["monthly_payment_kzt"] == 88848.79
    assert r["overpayment_kzt"] == 66185.46


def test_loan_payment_zero_rate_and_bad_input():
    assert tools.loan_payment(120_000, 0, 12)["monthly_payment_kzt"] == 10000.0
    assert "error" in tools.loan_payment(0, 10, 12)


def test_debt_burden_over_limit():
    r = tools.debt_burden(600_000, 329_306.65)
    assert r["debt_burden_pct"] == 54.88
    assert r["within_limit"] is False


def test_fraud_signals_showcase():
    bad = tools.fraud_signals("T-DEMO-1")
    codes = {s["code"] for s in bad["signals"]}
    assert {"night", "new_recipient", "new_device", "flagged_recipient", "loan_burst"} <= codes
    assert bad["rule_score"] == 100
    good = tools.fraud_signals("T-DEMO-2")
    assert good["signals"] == [] and good["rule_score"] == 0


def test_call_tool_never_raises():
    assert "error" in tools.call_tool("nope", "{}")
    assert "error" in tools.call_tool("loan_payment", "{not json")
    assert "error" in tools.call_tool("client_profile", {"client_id": "C-404"})


def test_schemas_are_strict():
    for schema in tools.openai_tools():
        params = schema["parameters"]
        assert schema["strict"] is True
        assert params["additionalProperties"] is False
        assert set(params["required"]) == set(params["properties"])
