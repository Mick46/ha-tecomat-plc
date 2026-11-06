"""Zápis z HA během běžícího čtení: staré přečtené hodnoty nesmí přepsat zapsanou (relé „cvaklo“ v HA zpět)."""

import time

from custom_components.tecomat_plc.coordinator import TecomatCoordinator


def _coord():
    c = TecomatCoordinator.__new__(TecomatCoordinator)
    c._writes = {}
    return c


def test_read_started_before_write_keeps_written_value():
    c = _coord()
    t0 = time.monotonic()   # čtení začalo
    c._note_write(100, 0)   # během čtení VTherm vypnul relé
    data = {100: 1, 101: 5}   # čtení ještě vidělo zapnuto
    c._apply_writes(data, t0)
    assert data == {100: 0, 101: 5}
    assert 100 in c._writes   # zápis zůstává pro případné další souběžné čtení


def test_read_started_after_write_wins_and_clears():
    c = _coord()
    c._note_write(100, 0)
    t0 = time.monotonic() + 0.001   # další čtení začalo až po zápisu
    data = {100: 1}   # PLC mezitím hodnotu samo změnilo
    c._apply_writes(data, t0)
    assert data == {100: 1}
    assert c._writes == {}


def test_negative_value_masked():
    c = _coord()
    t0 = time.monotonic()
    c._note_write(7, -1)
    data = {7: 0}
    c._apply_writes(data, t0)
    assert data[7] == 0xFFFF
