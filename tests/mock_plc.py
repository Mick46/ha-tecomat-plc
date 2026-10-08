"""Simulátor PLC Tecomat s programem prgMain_milnik1c.ST (Modbus TCP server).

Napodobuje paměť PLC: deskriptor (hlavička, meta, řetězce STRING[23]),
stavový blok, schránku konfigurace, čtecí okno, světla, tlačítka a teploty.
"""

from __future__ import annotations

import asyncio
import struct

DESC = 24000
META = 24100
TST = 25750
STRS = 25800
STATUS = 30000
MAILBOX = 30100
WINDOW = 30200
MAX_B = 40
STR_SIZE = 24  # STRING[23] = 23 znaků + nulový ukončovač

GROUPS = [("CP-1000", "Stůl"), ("Vypínač WSB2-20 A2A8", "Stůl"), ("Vstupy IM2-140M 9DE4", "Stůl")]
# typ, skupina, adresa, p1, p2, p3, flags, uid, název
OBJECTS = [
    (1, 0, 30002, 0, 0, 0, 0, 1, "Test světlo 1 (DO0)"),
    (1, 0, 30003, 1, 0, 0, 0, 2, "Test světlo 2 (DO1)"),
    (3, 1, 30010, 0, 0, 0, 0, 3, "Klapka nahoře"),
    (3, 1, 30011, 1, 0, 0, 0, 4, "Klapka dole"),
    (3, 2, 30012, 2, 0, 0, 0, 5, "Vstup IN10"),
    (3, 2, 30013, 3, 0, 0, 0, 6, "Vstup IN11"),
    (4, 1, 30050, 0, 0, 0, 0, 7, "Teplota"),
    (5, 0, 30021, 5, 0, 0, 0, 8, "HDO"),
    (5, 0, 30021, 4, 3, 0, 0, 9, "Vstup 230 V"),
    (5, 0, 30022, 1, 1, 0, 0, 10, "Porucha CIB1"),
    (5, 0, 30022, 5, 1, 0, 0, 11, "Porucha zdroje"),
    (5, 0, 30022, 7, 1, 0, 0, 12, "Porucha akumulátoru"),
]


class MockPlc:
    def __init__(self, swap_bytes: bool = True, prog_version: int = 3, plc_type: int = 1000) -> None:
        self.plc_type = plc_type
        self.swap = swap_bytes  # True = bajty ve slově jako little-endian (nižší adresa = nižší bajt)
        self.reg: dict[int, int] = {}
        self.cfg = [0] * 1920
        self.tcorr = [0] * 40
        self.seq_old = 0
        self.raw_temp = 223
        self.btn_count = [0, 0, 0, 0]
        self.writes: list[tuple[int, list[int]]] = []
        self.server: asyncio.base_events.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._dead: set[asyncio.StreamWriter] = set()  # spojení „před restartem“
        self.port = 0
        self._build(prog_version)

    # ------------------------------------------------------------- paměť
    def _put_string(self, addr: int, index: int, text: str) -> None:
        raw = text.encode("cp1250")[: STR_SIZE - 1].ljust(STR_SIZE, b"\x00")
        byte_ofs = index * STR_SIZE
        for i, b in enumerate(raw):
            pos = byte_ofs + i
            a = addr + pos // 2
            w = self.reg.get(a, 0)
            lo_first = self.swap
            hi = (pos % 2 == 0) != lo_first  # pozice bajtu ve slově
            w = (w & 0x00FF) | (b << 8) if hi else (w & 0xFF00) | b
            self.reg[a] = w

    def _build(self, prog_version: int) -> None:
        hdr = [0] * 32
        hdr[0:18] = [0x5443, 1, self.plc_type, prog_version, len(GROUPS), len(OBJECTS), MAX_B, 48,
                     STATUS, MAILBOX, WINDOW, META, 8, STRS, 264, TST, 64, 32]
        for i, v in enumerate(hdr):
            self.reg[DESC + i] = v
        self._put_string(TST, 0, "TECO")
        self._put_string(TST, 1, "TECO")
        for g, (name, area) in enumerate(GROUPS):
            self._put_string(STRS, g, name)
            self._put_string(STRS, 32 + g, area)
        for i, o in enumerate(OBJECTS):
            for k, v in enumerate(o[:8]):
                self.reg[META + i * 8 + k] = v
            self._put_string(STRS, 64 + i, o[8])
        # výchozí konfigurace jako v PLC
        self.cfg[0] = 9
        self.cfg[41] = 9
        self.cfg[1] = 8
        self.cfg[40] = 8
        self.reg[30021] = 0b100000  # HDO aktivní
        self.reg[30022] = 0
        self.cycle()

    def checksum(self) -> int:
        chk = 0
        for k, v in enumerate(self.cfg):
            if v:
                chk = (chk + v * (k % 251 + 1)) % 65536
        for k, v in enumerate(self.tcorr):
            u = v + 65536 if v < 0 else v
            chk = (chk + u * ((10000 + k) % 251 + 1)) % 65536
        return chk

    def cycle(self) -> None:
        """Jeden cyklus programu PLC."""
        r = self.reg
        seq = r.get(MAILBOX, 0)
        if seq != self.seq_old:
            self.seq_old = seq
            n = min(r.get(MAILBOX + 1, 0), 32)
            for k in range(n):
                idx = r.get(MAILBOX + 2 + 2 * k, 0)
                v = r.get(MAILBOX + 3 + 2 * k, 0)
                if 0 <= idx <= 1919 and v <= 63:
                    self.cfg[idx] = v
                elif 10000 <= idx <= 10039:
                    self.tcorr[idx - 10000] = v - 65536 if v > 32767 else v
            r[STATUS + 5] = seq
        r[STATUS + 6] = self.checksum()
        req = r.get(STATUS + 7, 0)
        if req > 10039:
            req = 0
        r[WINDOW] = req
        for k in range(1, 33):
            if req >= 10000:
                i = req - 10000 + k - 1
                v = self.tcorr[i] if i <= 39 else 0
                r[WINDOW + k] = v + 65536 if v < 0 else v
            else:
                i = req + 2 * (k - 1)
                lo = self.cfg[i] if i <= 1919 else 0
                hi = self.cfg[i + 1] if i + 1 <= 1919 else 0
                r[WINDOW + k] = lo + 256 * hi
        r[30050] = self.raw_temp
        r[30051] = (self.raw_temp + self.tcorr[0]) & 0xFFFF
        r[30052] = self.tcorr[0] & 0xFFFF
        r[STATUS + 4] = 1 if r.get(STATUS + 0, 0) else 0

    def press(self, button: int, typ: int) -> None:
        self.btn_count[button] = (self.btn_count[button] + 1) % 256
        self.reg[30010 + button] = self.btn_count[button] * 256 + typ

    # ------------------------------------------------------------ server
    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            for w in list(self._clients):
                w.close()
            await self.server.wait_closed()

    def restart(self) -> None:
        """Restart PLC: stará TCP spojení zůstanou otevřená, ale PLC na ně neodpovídá."""
        self._dead |= self._clients

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        try:
            while True:
                head = await reader.readexactly(7)
                tid, proto, length, unit = struct.unpack(">HHHB", head)
                pdu = await reader.readexactly(length - 1)
                if writer in self._dead:
                    continue
                resp = self._process(pdu)
                writer.write(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            self._clients.discard(writer)
            self._dead.discard(writer)
            writer.close()

    def _process(self, pdu: bytes) -> bytes:
        fc = pdu[0]
        if fc == 3:
            addr, cnt = struct.unpack(">HH", pdu[1:5])
            self.cycle()
            vals = [self.reg.get(addr + i, 0) & 0xFFFF for i in range(cnt)]
            return struct.pack(f">BB{cnt}H", 3, cnt * 2, *vals)
        if fc == 6:
            addr, val = struct.unpack(">HH", pdu[1:5])
            self.reg[addr] = val
            self.writes.append((addr, [val]))
            self.cycle()
            return pdu[:5]
        if fc == 16:
            addr, cnt, _bc = struct.unpack(">HHB", pdu[1:6])
            vals = list(struct.unpack(f">{cnt}H", pdu[6 : 6 + cnt * 2]))
            for i, v in enumerate(vals):
                self.reg[addr + i] = v
            self.writes.append((addr, vals))
            self.cycle()
            return struct.pack(">BHH", 16, addr, cnt)
        return bytes([fc | 0x80, 1])
