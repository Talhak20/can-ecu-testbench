"""Funktion: Reaktion auf den Ladebefehl."""


def test_charging_starts_and_current_ramps_to_target(tester):
    tester.send("Charger_Command", {"ChargeEnable": 1, "TargetCurrent": 80})
    s = tester.wait_for("BMS_Status", lambda s: s["ChargingActive"] == 1, timeout_s=1.0)
    assert s["ChargingActive"] == 1
    s = tester.wait_for("BMS_Status", lambda s: abs(s["PackCurrent"] - 80) < 0.5, timeout_s=2.0)
    assert abs(s["PackCurrent"] - 80) < 0.5


def test_charging_stops_on_disable(tester):
    tester.send("Charger_Command", {"ChargeEnable": 1, "TargetCurrent": 50})
    tester.wait_for("BMS_Status", lambda s: s["ChargingActive"] == 1)
    tester.send("Charger_Command", {"ChargeEnable": 0, "TargetCurrent": 0})
    s = tester.wait_for("BMS_Status", lambda s: s["ChargingActive"] == 0 and s["PackCurrent"] == 0)
    assert s["PackCurrent"] == 0


def test_state_of_charge_rises_while_charging(tester):
    start = tester.collect("BMS_Status", duration_s=0.3)[-1][1]["StateOfCharge"]
    tester.send("Charger_Command", {"ChargeEnable": 1, "TargetCurrent": 200})
    s = tester.wait_for("BMS_Status", lambda s: s["StateOfCharge"] > start, timeout_s=3.0)
    assert s["StateOfCharge"] > start
