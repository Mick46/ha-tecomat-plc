"""Simulátor PLC s programem z generátoru (protokol 2, nastroje/generator.py).

Rozložení paměti, schránka (tlačítka 0.., korekce 10000.., parametry 20000..),
čtecí okno (hodnota na registr) a kontrolní součet odpovídají gen_dum.ST.
"""

from __future__ import annotations

from .mock_plc import MockPlc

DESC = 20000
META = 20050
TST = 23300
STRS = 23350
STATUS = 30000
MAILBOX = 30100
WINDOW = 30200
DATA = 30300
AREA_OFS = 64
OBJ_OFS = 128

# skupina 0 = PLC, 1.. = oblasti
GROUPS2 = [("CP-1000", "Admin"), ("Kuchyň", "Kuchyň"), ("Chodba", "Chodba")]
# typ, skupina, adresa, p1, p2, p3, flags, uid, název
OBJECTS2 = [
    (1, 1, 30300, 0, 1, 0, 0, 20, "Bodovky"),
    (7, 1, 30301, 0, 2, 0, 0, 2, "Pod linkou"),          # stmívač: +0 žádaný, +1 skutečný
    (4, 1, 30303, 0, 0, 0, 0, 402, "Teplota"),           # teplota, korekce index 0
    (3, 1, 30306, 0, 0, 0, 0, 2091, "Vypínač Nahoře"),   # tlačítko b = 0
    (3, 2, 30307, 0, 0, 0, 0, 203, "Levé"),              # tlačítko b = 1
    (10, 1, 30308, 0, 1440, 0, 10 << 8, 30101, "Bodovky max. doba"),       # parametr 0, min
    (10, 1, 30309, 0, 600, 1, 1 | (9 << 8) | 0x10, 30013, "Pod linkou náběh"),    # parametr 1, 0,1 s, i jako entita
]


class MockPlcV2(MockPlc):
    def __init__(self, prog_version: int = 7) -> None:
        self.box: dict[int, int] = {}
        super().__init__(prog_version=prog_version, objects=OBJECTS2)

    def _build(self, prog_version: int) -> None:
        hdr = [0] * 32
        hdr[0:20] = [0x5443, 2, self.plc_type, prog_version, len(GROUPS2), len(self.objects), 2, 8,
                     STATUS, MAILBOX, WINDOW, META, 8, STRS, OBJ_OFS + 400, TST, OBJ_OFS, AREA_OFS, 1, 2]
        for i, v in enumerate(hdr):
            self.reg[DESC + i] = v
        self._put_string(TST, 0, "TECO")
        self._put_string(TST, 1, "TECO")
        for g, (name, area) in enumerate(GROUPS2):
            self._put_string(STRS, g, name)
            self._put_string(STRS, AREA_OFS + g, area)
        for i, o in enumerate(self.objects):
            for k, v in enumerate(o[:8]):
                self.reg[META + i * 8 + k] = v
            self._put_string(STRS, OBJ_OFS + i, o[8])
        # výchozí konfigurace: tlačítko 0 krátce přepne bodovky, dlouze stmívač na 50 %
        self.box.update({0: 20, 1: 1 * 256, 8: 2, 9: 4 * 256 + 50})
        self.box[20000] = 0
        self.box[20001] = 20
        self.raw_temp = 223
        self.cycle()

    def checksum(self) -> int:
        chk = 0
        for k, v in self.box.items():
            chk = (chk + (v & 0xFFFF) * (k % 251 + 1)) % 65536
        return chk

    def cycle(self) -> None:
        r = self.reg
        seq = r.get(MAILBOX, 0)
        if seq != self.seq_old:
            self.seq_old = seq
            n = min(r.get(MAILBOX + 1, 0), 32)
            for k in range(n):
                self.box[r.get(MAILBOX + 2 + 2 * k, 0)] = r.get(MAILBOX + 3 + 2 * k, 0)
            r[STATUS + 5] = seq
        r[STATUS + 6] = self.checksum()
        req = r.get(STATUS + 7, 0) % 32768
        r[WINDOW] = r.get(STATUS + 7, 0)
        for k in range(1, 33):
            r[WINDOW + k] = self.box.get(req + k - 1, 0)
        # teplota s korekcí (index 0 = 10000)
        corr = self.box.get(10000, 0)
        corr = corr - 65536 if corr > 32767 else corr
        r[30303] = self.raw_temp
        r[30304] = (self.raw_temp + corr) & 0xFFFF
        r[30305] = corr & 0xFFFF
        # stmívač: skutečný jas = žádaný (bez rampy)
        r[30302] = r.get(30301, 0)
        # parametry
        r[30308] = self.box.get(20000, 0)
        r[30309] = self.box.get(20001, 0)
        r[STATUS + 4] = 1 if r.get(STATUS + 0, 0) else 0
