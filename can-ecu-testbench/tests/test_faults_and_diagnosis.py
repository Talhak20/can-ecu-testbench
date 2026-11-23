"""Fehlerfaelle per Fehlerinjektion und Auslesen des Fehlerspeichers (vereinfachtes UDS)."""
from ecu_sim.bms_ecu import DTC_OVER_TEMPERATURE, DTC_UNDER_VOLTAGE


def test_fault_memory_empty_at_start(tester):
    count, dtcs = tester.read_dtcs()
    assert count == 0 and dtcs == []


def test_overtemperature_sets_dtc_and_stops_charging(ecu, tester):
    tester.send("Charger_Command", {"ChargeEnable": 1, "TargetCurrent": 100})
    tester.wait_for("BMS_Status", lambda s: s["ChargingActive"] == 1)

    ecu.set_temperature(75)  # Fehlerinjektion: Zelle zu heiss

    tester.wait_for("BMS_Faults", lambda f: f["OverTemperature"] == 1)
    s = tester.wait_for("BMS_Status", lambda s: s["ChargingActive"] == 0)
    assert s["PackCurrent"] == 0, "Schutzreaktion: Ladestrom muss abgeschaltet sein"
    count, dtcs = tester.read_dtcs()
    assert count == 1 and dtcs == [DTC_OVER_TEMPERATURE]


def test_charging_blocked_while_overtemperature(ecu, tester):
    ecu.set_temperature(80)
    tester.wait_for("BMS_Faults", lambda f: f["OverTemperature"] == 1)
    tester.send("Charger_Command", {"ChargeEnable": 1, "TargetCurrent": 50})
    frames = tester.collect("BMS_Status", duration_s=0.5)
    assert all(f[1]["ChargingActive"] == 0 for f in frames)


def test_undervoltage_dtc(ecu, tester):
    ecu.set_voltage(280.0)
    tester.wait_for("BMS_Faults", lambda f: f["UnderVoltage"] == 1)
    count, dtcs = tester.read_dtcs()
    assert count >= 1 and dtcs[0] == DTC_UNDER_VOLTAGE


def test_clear_fault_memory(ecu, tester):
    ecu.set_temperature(70)
    tester.wait_for("BMS_Faults", lambda f: f["DtcCount"] >= 1)
    ecu.set_temperature(25)  # Ursache beheben, sonst wird der Fehler sofort neu gesetzt
    tester.clear_dtcs()
    tester.wait_for("BMS_Faults", lambda f: f["DtcCount"] == 0)
    count, _ = tester.read_dtcs()
    assert count == 0


def test_unsupported_service_gives_negative_response(tester):
    r = tester._diag([0x22, 0xF1, 0x90])  # ReadDataByIdentifier, hier nicht implementiert
    assert list(r[:3]) == [0x7F, 0x22, 0x11]


import pytest


@pytest.mark.parametrize("temperatur, fehler_erwartet", [
    (59, 0),
    (60, 0),
    (61, 1),
])
def test_overtemperature_threshold(ecu, tester, temperatur, fehler_erwartet):
    ecu.set_temperature(temperatur)
    frames = tester.collect("BMS_Faults", duration_s=0.5)
    letzter_wert = frames[-1][1]["OverTemperature"]
    assert letzter_wert == fehler_erwartet
