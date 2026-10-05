"""Konstanty integrace Tecomat PLC."""

from __future__ import annotations

DOMAIN = "tecomat_plc"

CONF_UNIT_ID = "unit_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SHOW_IN_SIDEBAR = "show_in_sidebar"

DEFAULT_PORT = 502
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 1.0

# Deskriptor v PLC (pevná adresa, vše ostatní si integrace přečte z hlavičky)
DESC_BASE = 24000
DESC_MAGIC = 0x5443  # 'TC'
DESC_PROTOCOL = 1

# Hlavička deskriptoru (index v hdr[])
H_MAGIC = 0
H_PROTOCOL = 1
H_PLC_TYPE = 2
H_PROG_VERSION = 3
H_GROUPS = 4
H_OBJECTS = 5
H_MAX_B = 6
H_MAX_C = 7
H_STATUS_BASE = 8
H_MAILBOX_BASE = 9
H_WINDOW_BASE = 10
H_META_BASE = 11
H_META_STRIDE = 12
H_STRS_BASE = 13
H_STRS_COUNT = 14
H_TST_BASE = 15
H_OBJ_NAME_OFS = 16
H_AREA_OFS = 17

# Stavový blok (offset od status base)
S_HB_IN = 0        # HA -> PLC heartbeat
S_HB_OUT = 1       # PLC -> HA heartbeat (sekundy)
S_HA_ONLINE = 4    # PLC vidí HA
S_CFG_ACK = 5      # potvrzení schránky
S_CFG_CHECKSUM = 6 # kontrolní součet konfigurace
S_WINDOW_REQ = 7   # požadavek na čtecí okno
STATUS_LEN = 8

# Typy objektů
T_LIGHT = 1
T_SWITCH = 2
T_BUTTON = 3
T_TEMP = 4
T_BINARY = 5

NO_MATRIX = 0xFFFF

# Konfigurace (schránka)
CORR_INDEX_BASE = 10000
MAILBOX_BATCH = 32
WINDOW_BYTES = 64
WINDOW_REGS = 33

PANEL_URL = "tecomat-plc"
PANEL_COMPONENT = "tecomat-plc-panel"
STATIC_URL = "/tecomat_plc_static"

BUTTON_EVENTS = {1: "short", 2: "long", 3: "double"}

PLATFORMS = ["binary_sensor", "event", "light", "number", "sensor", "switch"]
