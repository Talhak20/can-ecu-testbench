"""Testwerkzeug: sendet Botschaften, wartet auf Signale und liest den Fehlerspeicher."""
from __future__ import annotations

import time
from typing import Callable

import can
import cantools

from ecu_sim.bms_ecu import DBC_PATH, DIAG_REQUEST_ID, DIAG_RESPONSE_ID


class CanTester:
    def __init__(self, channel: str = "testbench", interface: str = "virtual"):
        self.db = cantools.database.load_file(str(DBC_PATH))
        self.bus = can.Bus(channel=channel, interface=interface, receive_own_messages=False)

    def close(self) -> None:
        self.bus.shutdown()

    # ---------- Senden ----------
    def send(self, message_name: str, signals: dict) -> None:
        m = self.db.get_message_by_name(message_name)
        self.bus.send(can.Message(arbitration_id=m.frame_id, data=m.encode(signals), is_extended_id=False))

    # ---------- Empfangen ----------
    def flush(self) -> None:
        while self.bus.recv(timeout=0) is not None:
            pass

    def collect(self, message_name: str, duration_s: float) -> list[tuple[float, dict]]:
        """Sammelt alle Botschaften eines Typs fuer eine Zeitspanne (Zeitstempel, Signale)."""
        frame_id = self.db.get_message_by_name(message_name).frame_id
        out, end = [], time.perf_counter() + duration_s
        while (left := end - time.perf_counter()) > 0:
            msg = self.bus.recv(timeout=left)
            if msg is not None and msg.arbitration_id == frame_id:
                out.append((time.perf_counter(), self.db.decode_message(frame_id, msg.data)))
        return out

    def wait_for(self, message_name: str, condition: Callable[[dict], bool], timeout_s: float = 2.0) -> dict:
        """Wartet, bis ein Signalzustand erreicht ist; wirft AssertionError bei Timeout."""
        frame_id = self.db.get_message_by_name(message_name).frame_id
        end, last = time.perf_counter() + timeout_s, None
        while (left := end - time.perf_counter()) > 0:
            msg = self.bus.recv(timeout=left)
            if msg is not None and msg.arbitration_id == frame_id:
                last = self.db.decode_message(frame_id, msg.data)
                if condition(last):
                    return last
        raise AssertionError(f"{message_name}: Bedingung nicht erreicht in {timeout_s} s, letzter Wert {last}")

    # ---------- Diagnose (vereinfachtes UDS) ----------
    def _diag(self, payload: list[int], timeout_s: float = 1.0) -> bytes:
        self.flush()
        data = [len(payload)] + payload
        data += [0x00] * (8 - len(data))
        self.bus.send(can.Message(arbitration_id=DIAG_REQUEST_ID, data=data, is_extended_id=False))
        end = time.perf_counter() + timeout_s
        while (left := end - time.perf_counter()) > 0:
            msg = self.bus.recv(timeout=left)
            if msg is not None and msg.arbitration_id == DIAG_RESPONSE_ID:
                return bytes(msg.data[1:1 + msg.data[0]])
        raise AssertionError("Keine Diagnose-Antwort vom Steuergeraet")

    def read_dtcs(self) -> tuple[int, list[int]]:
        r = self._diag([0x19, 0x02, 0xFF])
        assert r[0] == 0x59, f"Negative Antwort: {r.hex()}"
        count, dtcs = r[2], []
        for i in range(3, len(r), 3):
            dtcs.append((r[i] << 16) | (r[i + 1] << 8) | r[i + 2])
        return count, dtcs

    def clear_dtcs(self) -> None:
        r = self._diag([0x14, 0xFF, 0xFF, 0xFF])
        assert r[0] == 0x54, f"Loeschen fehlgeschlagen: {r.hex()}"
