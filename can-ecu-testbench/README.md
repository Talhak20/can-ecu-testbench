# CAN-ECU-Testbench

Testautomatisierung für ein simuliertes Batterie-Steuergerät (BMS) auf einem virtuellen CAN-Bus, mit Python, python-can, cantools und pytest.

Das Projekt bildet das Prinzip eines HIL-Tests komplett in Software nach: Ein simuliertes Steuergerät sendet CAN-Botschaften. Eine automatisierte Testsuite stimuliert es, prüft seine Reaktionen und liest den Fehlerspeicher per vereinfachter UDS-Diagnose aus. Es ist ein privates Lern- und Übungsprojekt und kein Ersatz für echte HIL-Hardware.

## Was getestet wird

| Bereich | Tests |
|---|---|
| Kommunikation | Zykluszeit 100 ms, Alive-Counter, plausible Signalbereiche |
| Funktion | Laden starten und stoppen, Stromrampe auf den Zielwert, Ladezustand steigt |
| Fehlerfälle | Fehlerinjektion Übertemperatur und Unterspannung, Schutzreaktion (Laden abbrechen und sperren) |
| Diagnose | Fehlerspeicher lesen (UDS 0x19) und löschen (0x14), negative Antwort auf nicht unterstützte Dienste |

## Aufbau

```
dbc/battery_ecu.dbc          CAN-Datenbank: BMS_Status, BMS_Faults, Charger_Command
ecu_sim/bms_ecu.py           simuliertes Steuergerät (zyklisches Senden, Logik, Fehlerspeicher, Diagnose)
testbench/can_tester.py      Testwerkzeug: senden, auf Signale warten, Fehlerspeicher lesen
tests/                       pytest-Testfälle
.github/workflows/tests.yml  Tests laufen automatisch bei jedem Push (GitHub Actions)
```

## Ausführen

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pytest --html=report.html --self-contained-html
```

`report.html` ist der Testbericht. Die Simulation lässt sich auch allein starten: `python -m ecu_sim.bms_ecu`.

## Nächste Ausbaustufen

- Grenzwerttests mit `pytest.mark.parametrize` (zum Beispiel Temperatur 59, 60 und 61 °C)
- Mehrrahmen-Diagnose (ISO-TP) für mehrere Fehlereinträge
- Messwerte als CSV mitschreiben und mit pandas auswerten
- Anbindung an echte Hardware über einen USB-CAN-Adapter (python-can unterstützt zum Beispiel PCAN und Vector)
