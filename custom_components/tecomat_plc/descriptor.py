"""Načtení popisu (deskriptoru), kterým PLC samo popisuje své objekty."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .const import (
    DESC_BASE,
    DESC_MAGIC,
    H_AREA_OFS,
    H_GROUPS,
    H_MAGIC,
    H_MAILBOX_BASE,
    H_MAX_B,
    H_MAX_C,
    H_META_BASE,
    H_META_STRIDE,
    H_OBJ_NAME_OFS,
    H_OBJECTS,
    H_PLC_TYPE,
    H_PROG_VERSION,
    H_PROTOCOL,
    H_STATUS_BASE,
    H_STRS_BASE,
    H_TST_BASE,
    H_WINDOW_BASE,
)
from .modbus_client import ModbusTcpClient


class InvalidDescriptor(Exception):
    """PLC neobsahuje platný popis pro integraci."""


@dataclass
class PlcGroup:
    id: int
    name: str
    area: str


@dataclass
class PlcObject:
    index: int
    type: int
    group: int
    addr: int
    p1: int
    p2: int
    p3: int
    flags: int
    uid: int
    name: str


@dataclass
class Descriptor:
    protocol: int
    plc_type: int
    prog_version: int
    max_b: int
    max_c: int
    status_base: int
    mailbox_base: int
    window_base: int
    groups: list[PlcGroup] = field(default_factory=list)
    objects: list[PlcObject] = field(default_factory=list)

    @property
    def plc_model(self) -> str:
        return f"CP-{self.plc_type}" if self.plc_type else "Tecomat"

    def objects_of(self, *types: int) -> list[PlcObject]:
        return [o for o in self.objects if o.type in types]

    def group(self, gid: int) -> PlcGroup:
        for g in self.groups:
            if g.id == gid:
                return g
        return PlcGroup(gid, f"Skupina {gid}", "")


def _regs_to_bytes(regs: list[int], swap: bool) -> bytes:
    fmt = "<H" if swap else ">H"
    return b"".join(struct.pack(fmt, r) for r in regs)


def _detect_strings(regs: list[int]) -> tuple[bool, int, int]:
    """Z testovacích řetězců 'TECO','TECO' zjistí pořadí bajtů, délku položky a offset textu."""
    for swap in (False, True):
        raw = _regs_to_bytes(regs, swap)
        first = raw.find(b"TECO")
        if first < 0:
            continue
        second = raw.find(b"TECO", first + 4)
        if second < 0:
            continue
        return swap, second - first, first
    raise InvalidDescriptor("Testovací řetězec 'TECO' nenalezen")


def _decode(raw: bytes) -> str:
    raw = raw.split(b"\x00", 1)[0]
    return raw.decode("cp1250", errors="replace").strip()


async def read_header(client: ModbusTcpClient) -> list[int]:
    hdr = await client.read_holding(DESC_BASE, 32)
    if hdr[H_MAGIC] != DESC_MAGIC:
        raise InvalidDescriptor("V PLC chybí popis pro integraci (magic)")
    return hdr


async def read_descriptor(client: ModbusTcpClient) -> Descriptor:
    hdr = await read_header(client)
    n_groups = hdr[H_GROUPS]
    n_obj = hdr[H_OBJECTS]
    stride = hdr[H_META_STRIDE] or 8

    desc = Descriptor(
        protocol=hdr[H_PROTOCOL],
        plc_type=hdr[H_PLC_TYPE],
        prog_version=hdr[H_PROG_VERSION],
        max_b=hdr[H_MAX_B],
        max_c=hdr[H_MAX_C],
        status_base=hdr[H_STATUS_BASE],
        mailbox_base=hdr[H_MAILBOX_BASE],
        window_base=hdr[H_WINDOW_BASE],
    )

    # řetězce
    tst = await client.read_holding(hdr[H_TST_BASE], 40)
    swap, sstride, sofs = _detect_strings(tst)
    obj_ofs = hdr[H_OBJ_NAME_OFS] or 64
    area_ofs = hdr[H_AREA_OFS] or 32
    n_strs = obj_ofs + n_obj
    nbytes = n_strs * sstride + sofs
    sregs = await client.read_many(hdr[H_STRS_BASE], (nbytes + 1) // 2)
    sraw = _regs_to_bytes(sregs, swap)

    def s(i: int) -> str:
        start = i * sstride + sofs
        return _decode(sraw[start : start + sstride - sofs])

    for g in range(n_groups):
        desc.groups.append(PlcGroup(g, s(g) or f"Skupina {g}", s(area_ofs + g)))

    meta = await client.read_many(hdr[H_META_BASE], n_obj * stride) if n_obj else []
    for i in range(n_obj):
        m = meta[i * stride : i * stride + 8]
        if not m or m[0] == 0:
            continue
        desc.objects.append(
            PlcObject(
                index=i,
                type=m[0],
                group=m[1],
                addr=m[2],
                p1=m[3],
                p2=m[4],
                p3=m[5],
                flags=m[6],
                uid=m[7] or (i + 1),
                name=s(obj_ofs + i) or f"Objekt {i + 1}",
            )
        )
    return desc
