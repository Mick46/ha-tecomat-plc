"""Ochrana měřáků (energie, plyn) před nesmyslnými hodnotami: pokles a velký skok až po potvrzení."""

from custom_components.tecomat_plc.sensor import TecomatValue


def _guard(jump=50):
    s = TecomatValue.__new__(TecomatValue)
    s._jump, s._last, s._pend = jump, None, None
    return s


def test_normal_growth():
    s = _guard()
    assert [s._check_total(v) for v in (3277.3, 3277.4, 3280.0)] == [3277.3, 3277.4, 3280.0]


def test_glitch_ignored():
    s = _guard()
    s._check_total(3277.3)
    assert s._check_total(214748364.8) == 3277.3   # skok: drží poslední
    assert s._check_total(-214748364.8) == 3277.3   # záporná
    assert s._check_total(3270.0) == 3277.3   # jednorázový pokles
    assert s._check_total(3277.5) == 3277.5   # zpět normálně
    assert s._last == 3277.5


def test_reset_confirmed():
    s = _guard()
    s._check_total(12.3)   # denní měřák před půlnocí
    assert s._check_total(0.0) == 12.3   # první nula: čeká
    assert s._check_total(0.1) == 0.1   # potvrzeno dalším čtením
    assert s._check_total(0.2) == 0.2


def test_big_jump_confirmed():
    s = _guard()
    s._check_total(100.0)
    assert s._check_total(500.0) == 100.0
    assert s._check_total(500.2) == 500.2   # skok trvá: přijat


def test_no_jump_limit():
    s = _guard(jump=None)
    s._check_total(1.0)
    assert s._check_total(1e9) == 1e9
    assert s._check_total(5.0) == 1e9
