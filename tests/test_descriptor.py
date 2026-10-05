"""Čtení popisu z PLC (bez HA)."""

import pytest

from custom_components.tecomat_plc.descriptor import read_descriptor
from custom_components.tecomat_plc.modbus_client import ModbusTcpClient

from .mock_plc import MockPlc


@pytest.mark.parametrize("swap", [True, False])
async def test_read_descriptor(swap: bool) -> None:
    plc = MockPlc(swap_bytes=swap)
    await plc.start()
    client = ModbusTcpClient("127.0.0.1", plc.port, 1)
    try:
        d = await read_descriptor(client)
    finally:
        await client.close()
        await plc.stop()

    assert d.plc_model == "CP-1000"
    assert d.prog_version == 3
    assert [g.name for g in d.groups] == ["CP-1000", "Vypínač WSB2-20 A2A8", "Vstupy IM2-140M 9DE4"]
    assert d.groups[1].area == "Stůl"
    assert len(d.objects) == 12
    assert d.objects[0].name == "Test světlo 1 (DO0)"
    assert d.objects[2].name == "Klapka nahoře"
    assert d.objects[11].name == "Porucha akumulátoru"
    assert d.objects[6].type == 4 and d.objects[6].addr == 30050
    assert d.status_base == 30000 and d.mailbox_base == 30100 and d.window_base == 30200
