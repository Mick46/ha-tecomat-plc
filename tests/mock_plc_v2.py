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
    (8, 2, 30310, 5702, 0, 0, 1, 5701, "Žaluzie"),        # žaluzie: +0 povel, +1 cíl, +2 poloha, +3 lamely, +4 pohyb
    (9, 2, 30315, 0, 0, 0, 0, 226, "Vrata"),              # vrata: +0 povel, +1 stav
    (5, 2, 30317, 0, 6, 0, 0, 216, "Vchod"),              # pohyb
    (6, 2, 30318, 2, 8, 8, 1 | 2 | 4, 241, "Plyn"),       # plynoměr (32 bit, nastavitelný)
    (10, 2, 30320, 0, 1, 2, 11 << 8, 40455, "Levý signalizace vrat"),  # parametr ano/ne (bez objektu)
    # část 3: technologie
    (2, 1, 30321, 0, 7, 1, 0x20, 227, "Kotel"),                    # výstup jen ke čtení, role kotel
    (11, 1, 30322, "O0", 3, 3, 0x10, 65000, "Topení režim"),       # volba = parametr 3, entita
    (11, 1, 30323, "O1", 4, 0, 0x20, 7000, "Topení stav"),         # stav (jen ke čtení)
    (12, 1, 30324, 0, 0, 0, 0, 7012, "Teplá voda dezinfikovat"),   # akce
    (10, 2, 30325, 0, 1, 4, (11 << 8) | 0x10, 65103, "Bazén ohřev"),  # parametr ano/ne jako entita (switch)
    # část 4: výkon fáze L1 z EM03 (role grid1), odběr jako nastavitelné měřidlo (role e_imp, schránka 9002/9003)
    (6, 2, 30326, 0, 1, 1, 1 | (1 << 8), 311, "Výkon L1"),
    (6, 2, 30328, 3, 2, 2, 1 | 2 | 4 | (11 << 8), 314, "Odběr"),
]
AUTO_NAMES = ["PIR vstup"]
OPTIONS = ["Vypnuto|Zapnuto|Auto", "Vyp|Teplo|Řídí HA|Záloha"]  # simulátor má kratší řetězce než PLC
OPT_OFS = OBJ_OFS + len(OBJECTS2) + len(AUTO_NAMES)
OBJECTS2 = [tuple(OPT_OFS + int(x[1:]) if isinstance(x, str) and x[:1] == "O" and x[1:].isdigit() else x for x in o)
            for o in OBJECTS2]


class MockPlcV2(MockPlc):
    def __init__(self, prog_version: int = 7) -> None:
        self.box: dict[int, int] = {}
        super().__init__(prog_version=prog_version, objects=OBJECTS2)

    def _build(self, prog_version: int) -> None:
        hdr = [0] * 32
        hdr[0:22] = [0x5443, 2, self.plc_type, prog_version, len(GROUPS2), len(self.objects), 2, 8,
                     STATUS, MAILBOX, WINDOW, META, 8, STRS, OBJ_OFS + 400, TST, OBJ_OFS, AREA_OFS, 1, 3,
                     len(AUTO_NAMES), OBJ_OFS + len(self.objects)]
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
        for i, n in enumerate(AUTO_NAMES):
            self._put_string(STRS, OBJ_OFS + len(self.objects) + i, n)
        for i, n in enumerate(OPTIONS):
            self._put_string(STRS, OPT_OFS + i, n)
        # výchozí konfigurace: tlačítko 0 krátce přepne bodovky, dlouze stmívač na 50 %
        self.box.update({0: 20, 1: 1 * 256, 8: 2, 9: 4 * 256 + 50})
        self.box[20000] = 0
        self.box[20001] = 20
        self.box[20002] = 1
        self.box[20003] = 2      # režim topení Auto
        self.box[20004] = 0      # ohřev bazénu vypnut
        self.presses = 0
        self.e_imp = 123456
        self.box.update({4000: 1, 4001: 216, 4006: 20, 4007: 400, 4016: 20})
        for r in range(8, 16):
            self.box[4000 + r] = 0xFFFF
        self.gas = 1192265
        self.cover_pos = 100
        self.gate_open = 0
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
        r[30320] = self.box.get(20002, 0)
        # plynoměr: 9000 nižší, 9001 vyšší slovo (nastaví se zápisem 9001)
        if 9001 in self.box:
            self.gas = self.box.pop(9001) * 65536 + self.box.pop(9000, 0)
        r[30318], r[30319] = self.gas >> 16, self.gas & 0xFFFF
        # žaluzie: povel se hned provede
        cmd = r.get(30310, 0)
        if cmd == 1:
            self.cover_pos = 100
        elif cmd == 2:
            self.cover_pos = 0
        elif cmd == 4:
            self.cover_pos = r.get(30311, 0)
        r[30310] = 0
        r[30312], r[30313], r[30314] = self.cover_pos, 100, 0
        # vrata: impulz přepne stav
        if r.get(30315, 0) in (1, 2, 3):
            self.gate_open = {1: 1, 2: 0, 3: 1 - self.gate_open}[r[30315]]
        r[30315] = 0
        r[30316] = self.gate_open
        # technologie: kotel běží v režimu Zapnuto, stav „Řídí HA“, akce se spočítá a vynuluje
        r[30322] = self.box.get(20003, 0)
        r[30325] = self.box.get(20004, 0)
        r[30321] = 1 if r[30322] == 1 else 0
        r[30323] = 2 if r[30322] else 0
        if r.get(30324, 0) == 1:
            self.presses += 1
        r[30324] = 0
        # elektroměr: výkon L1 -250 W (dodávka), odběr Wh nastavitelný 9002/9003
        r[30326], r[30327] = 0xFFFF, (-250) & 0xFFFF
        if 9003 in self.box:
            self.e_imp = self.box.pop(9003) * 65536 + self.box.pop(9002, 0)
        r[30328], r[30329] = self.e_imp >> 16, self.e_imp & 0xFFFF
        r[STATUS + 4] = 1 if r.get(STATUS + 0, 0) else 0
