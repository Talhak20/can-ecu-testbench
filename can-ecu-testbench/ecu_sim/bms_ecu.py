"""Simuliertes Batterie-Steuergeraet (BMS) auf einem virtuellen CAN-Bus.

Das Steuergeraet
- sendet alle 100 ms BMS_Status und BMS_Faults,
- reagiert auf Charger_Command (Laden ein/aus, Zielstrom),
- erkennt Uebertemperatur und Unterspannung und legt dafuer Fehler (DTCs) im Fehlerspeicher ab,
- beantwortet eine vereinfachte UDS-Diagnose auf 0x7E0/0x7E8:
  0x19 02 (Fehlerspeicher lesen) und 0x14 FF FF FF (Fehlerspeicher loeschen).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import can
import cantools

DBC_PATH = Path(__file__).resolve().parent.parent / "dbc" / "battery_ecu.dbc"

DIAG_REQUEST_ID = 0x7E0
DIAG_RESPONSE_ID = 0x7E8

# Fehlercodes (3 Byte, vereinfachtes UDS-DTC-Format)
DTC_OVER_TEMPERATURE = 0x0A1B00
DTC_UNDER_VOLTAGE = 0x0A0C00

TEMP_LIMIT_C = 60
UNDERVOLTAGE_LIMIT_V = 300.0
CYCLE_TIME_S = 0.100


@dataclass
class BmsState:
    voltage: float = 400.0
    current: float = 0.0
    soc: float = 50.0
    temperature: int = 25
    charging: bool = False
    target_current: float = 0.0
    alive: int = 0
    dtcs: list[int] = field(default_factory=list)


class BmsEcu:
    """Startet das simulierte Steuergeraet in einem eigenen Thread."""

    def __init__(self, channel: str = "testbench", interface: str = "virtual"):
        self.db = cantools.database.load_file(str(DBC_PATH))
        self.bus = can.Bus(channel=channel, interface=interface, receive_own_messages=False)
        self.state = BmsState()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ---------- Steuerung von aussen (Fehlerinjektion fuer Tests) ----------
    def set_temperature(self, celsius: int) -> None:
        with self._lock:
            self.state.temperature = celsius

    def set_voltage(self, volts: float) -> None:
        with self._lock:
            self.state.voltage = volts

    # ---------- Lebenszyklus ----------
    def start(self) -> "BmsEcu":
        for target in (self._cyclic_tx, self._rx_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        return self

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=1)
        self.bus.shutdown()

    # ---------- Logik ----------
    def _update(self, dt: float) -> None:
        s = self.state
        if s.charging:
            # Strom faehrt in Rampen auf den Zielwert (20 A pro Zyklus)
            step = 20.0
            s.current = min(s.target_current, s.current + step) if s.current < s.target_current else s.target_current
            s.soc = min(100.0, s.soc + s.current * dt / 360.0)
        else:
            s.current = 0.0
        if s.temperature > TEMP_LIMIT_C:
            self._store_dtc(DTC_OVER_TEMPERATURE)
            s.charging = False  # Schutzreaktion: Laden abbrechen
            s.current = 0.0
        if s.voltage < UNDERVOLTAGE_LIMIT_V:
            self._store_dtc(DTC_UNDER_VOLTAGE)
        s.alive = (s.alive + 1) % 16

    def _store_dtc(self, dtc: int) -> None:
        if dtc not in self.state.dtcs:
            self.state.dtcs.append(dtc)

    def _cyclic_tx(self) -> None:
        next_t = time.perf_counter()
        while not self._stop.is_set():
            with self._lock:
                self._update(CYCLE_TIME_S)
                s = self.state
                status = self.db.encode_message("BMS_Status", {
                    "PackVoltage": round(s.voltage, 1),
                    "PackCurrent": round(s.current, 1),
                    "StateOfCharge": round(s.soc * 2) / 2,
                    "CellTempMax": s.temperature,
                    "ChargingActive": int(s.charging),
                    "AliveCounter": s.alive,
                })
                faults = self.db.encode_message("BMS_Faults", {
                    "OverTemperature": int(DTC_OVER_TEMPERATURE in s.dtcs and s.temperature > TEMP_LIMIT_C),
                    "UnderVoltage": int(s.voltage < UNDERVOLTAGE_LIMIT_V),
                    "DtcCount": len(s.dtcs),
                })
            self.bus.send(can.Message(arbitration_id=0x100, data=status, is_extended_id=False))
            self.bus.send(can.Message(arbitration_id=0x101, data=faults, is_extended_id=False))
            next_t += CYCLE_TIME_S
            time.sleep(max(0.0, next_t - time.perf_counter()))

    def _rx_loop(self) -> None:
        while not self._stop.is_set():
            msg = self.bus.recv(timeout=0.05)
            if msg is None:
                continue
            if msg.arbitration_id == 0x200:
                cmd = self.db.decode_message("Charger_Command", msg.data)
                with self._lock:
                    blocked = self.state.temperature > TEMP_LIMIT_C
                    self.state.charging = bool(cmd["ChargeEnable"]) and not blocked
                    self.state.target_current = float(cmd["TargetCurrent"])
            elif msg.arbitration_id == DIAG_REQUEST_ID:
                self._handle_diag(bytes(msg.data))

    def _handle_diag(self, data: bytes) -> None:
        length, sid = data[0], data[1]
        if sid == 0x19 and length >= 2 and data[2] == 0x02:  # ReadDTCInformation, reportDTCByStatusMask
            with self._lock:
                dtcs = list(self.state.dtcs)[:1]  # Einzelrahmen: hoechstens ein DTC pro Antwort
                count = len(self.state.dtcs)
            payload = [0x59, 0x02, count]
            for d in dtcs:
                payload += [(d >> 16) & 0xFF, (d >> 8) & 0xFF, d & 0xFF]
            self._diag_reply(payload)
        elif sid == 0x14:  # ClearDiagnosticInformation
            with self._lock:
                self.state.dtcs.clear()
            self._diag_reply([0x54])
        else:
            self._diag_reply([0x7F, sid, 0x11])  # serviceNotSupported

    def _diag_reply(self, payload: list[int]) -> None:
        data = [len(payload)] + payload
        data += [0xAA] * (8 - len(data))
        self.bus.send(can.Message(arbitration_id=DIAG_RESPONSE_ID, data=data[:8], is_extended_id=False))


if __name__ == "__main__":
    ecu = BmsEcu().start()
    print("BMS-Simulation laeuft auf virtuellem CAN-Bus 'testbench'. Strg+C zum Beenden.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ecu.stop()
