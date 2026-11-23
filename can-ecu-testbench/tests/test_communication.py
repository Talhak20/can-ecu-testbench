"""Kommunikation: Zykluszeit, Alive-Counter und Signalbereiche."""
import statistics


def test_status_cycle_time_is_100ms(tester):
    frames = tester.collect("BMS_Status", duration_s=1.5)
    assert len(frames) >= 12, f"Zu wenige Botschaften: {len(frames)}"
    gaps = [b[0] - a[0] for a, b in zip(frames, frames[1:])]
    mean = statistics.mean(gaps)
    assert 0.090 <= mean <= 0.110, f"Mittlere Zykluszeit {mean*1000:.1f} ms"


def test_alive_counter_increments(tester):
    frames = tester.collect("BMS_Status", duration_s=0.8)
    counters = [f[1]["AliveCounter"] for f in frames]
    for a, b in zip(counters, counters[1:]):
        assert b == (a + 1) % 16, f"Alive-Counter springt von {a} auf {b}"


def test_signals_in_plausible_range(tester):
    _, s = tester.collect("BMS_Status", duration_s=0.3)[-1]
    assert 300 <= s["PackVoltage"] <= 450
    assert 0 <= s["StateOfCharge"] <= 100
    assert -40 <= s["CellTempMax"] <= 60
    assert s["ChargingActive"] == 0
