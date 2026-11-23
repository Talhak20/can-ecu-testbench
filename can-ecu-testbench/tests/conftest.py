import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ecu_sim.bms_ecu import BmsEcu  # noqa: E402
from testbench.can_tester import CanTester  # noqa: E402


@pytest.fixture
def ecu():
    """Startet fuer jeden Test ein frisches Steuergeraet (sauberer Ausgangszustand)."""
    e = BmsEcu().start()
    yield e
    e.stop()


@pytest.fixture
def tester(ecu):
    t = CanTester()
    t.flush()
    yield t
    t.close()
