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
DESC_BASE = 24000       # protokol 1
DESC_BASES = (20000, 24000)  # kde hledat hlavičku: protokol 2, protokol 1
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
H_AUTOS = 20          # protokol 2: počet automatik
H_AUTO_NAME_OFS = 21  # protokol 2: index prvního názvu automatiky v řetězcích
H_FLOOR_OFS = 22      # protokol 2: index podlaží skupiny v řetězcích (0 = není)

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
T_VALUE = 6   # měřená hodnota: p1 desetinná místa, p2 jednotka, p3 třída; flags bit0 = 32 bit (addr = vyšší slovo), bit1 = bez znaménka

T_DIMMER = 7  # stmívač: +0 žádaný jas 0–100 (zápis z HA), +1 skutečný jas
T_COVER = 8   # žaluzie/markýza: +0 povel (1 otevřít, 2 zavřít, 3 stop, 4 na polohu), +1 cílová poloha, +2 poloha, +3 lamely, +4 pohyb; p1 UID výstupu dolů; flags bit0 = lamely
T_GATE = 9    # vrata: +0 povel (1 otevřít, 2 zavřít, 3 impulz), +1 stav (1 otevřeno)
T_NUMBER = 10 # parametr v PLC: +0 hodnota; p1 min, p2 max, p3 index (schránka 20000+p3); flags bity 0–2 desetinná místa, 8–15 jednotka
T_SELECT = 11 # volba: +0 index volby; p1 řetězec „A|B|C“, p2 počet, p3 index parametru; flags 0x20 = jen stav (ne parametr)
T_ACTION = 12 # akce: +0 povel (zápis 1, PLC vynuluje)
T_TEXT = 13   # text: +0..19 STRING[39] v CP1250 (např. popis poruchy kotle)
TEXT_REGS = 20

F_VALUE_SET = 0x04     # VALUE: čítač nastavitelný z panelu (schránka 9000 + 2·i nižší, +1 vyšší slovo)
AUTO_INDEX_BASE = 4000
AUTO_REGS = 20
GAS_INDEX_BASE = 9000
UNIT_BOOL = 11
F_PARAM_ENTITY = 0x10  # NUMBER/SELECT: zobrazit jako entitu (jinak jen v panelu)
F_READONLY = 0x20      # LIGHT/SWITCH: řídí logika PLC (v HA binary_sensor); SELECT: jen stav
F_DIRECT = 0x40        # SELECT/NUMBER: přímý zápis (+0 přečtená hodnota, +1 požadovaná, +2 povel 1), ne parametr v PLC
UNIT_TIME = 13         # parametr: minuty od půlnoci (panel hh:mm)

# role technologie (meta p3): výstupy a teploty
ROLE_OUT = {1: "kotel", 2: "heads", 3: "pump", 4: "tuv", 5: "pool_filter", 6: "pool_heat", 7: "circuit"}
ROLE_TEMP = {1: "outdoor", 2: "tuv_top", 3: "tuv_bottom", 4: "pool"}
# technologie: parametr n má UID 30000 + base·5 + n
TECH_PARAM_BASES = {"heat": 65000, "tuv": 65050, "pool": 65100, "fve": 65150, "export": 65200}
TECH_FVE_STATUS = 7030
# role měřené hodnoty (VALUE flags bity 8–15)
VALUE_ROLES = {1: "grid1", 2: "grid2", 3: "grid3", 4: "ssr1", 5: "ssr2", 6: "ssr3", 7: "soc", 8: "pv", 9: "explim",
               10: "exp15", 11: "e_imp", 12: "e_exp", 13: "e_imp_day", 14: "e_exp_day", 15: "grid", 16: "inv_age",
               17: "gavg1", 18: "gavg2", 19: "gavg3", 20: "gavg", 21: "bpw1", 22: "bpw2", 23: "bpw3", 24: "bpw",
               25: "inv_writes", 26: "inv_flast",
               # karta Střídač
               27: "inv_card", 28: "bat_pw", 29: "house_pw", 30: "backup_pw", 31: "inv_temp", 32: "bat_temp", 33: "soh",
               34: "pv_day", 35: "house_day", 36: "bat_chg_day", 37: "bat_dis_day", 38: "rtc_off", 39: "end_soc"}
F_VALUE_DIAG = 0x40  # VALUE: diagnostika, ve výchozím stavu vypnutá (rychle se mění)
TECH_HEAT_STATUS, TECH_TUV_STATUS, TECH_TUV_DAYS, TECH_TUV_ACTION = 7000, 7010, 7011, 7012

# podtyp výstupu (protokol 2, meta p2 u LIGHT/SWITCH/DIMMER)
SUBTYPES = {
    1: "Světlo",
    2: "Stmívač",
    3: "Zásuvka",
    4: "Čerpadlo",
    5: "Ventilátor",
    6: "Spínač",
    7: "Kotel",
    8: "TUV",
    9: "Napájení hlavic",
    10: "Topný okruh",
}

F_VALUE_32 = 0x01
F_VALUE_UNSIGNED = 0x02
F_VALUE_NA = 0x80  # VALUE: vyšší slovo 0x8000 (32 bit 0x8000_0000) = neplatná hodnota (např. střídač ještě nepřečten)

NO_MATRIX = 0xFFFF

# Konfigurace (schránka)
CORR_INDEX_BASE = 10000
PARAM_INDEX_BASE = 20000
BTN_SLOTS = 16  # protokol 2: registry konfigurace na tlačítko (8 akcí × 2)
MAILBOX_BATCH = 32
WINDOW_BYTES = 64
WINDOW_REGS = 33

PANEL_URL = "tecomat-plc"
PANEL_COMPONENT = "tecomat-plc-panel"
STATIC_URL = "/tecomat_plc_static"

BUTTON_EVENTS = {1: "short", 2: "long", 3: "double"}

PLATFORMS = ["binary_sensor", "button", "cover", "event", "light", "number", "select", "sensor", "switch"]
