# Tecomat PLC pro Home Assistant

Integrace pro PLC Tecomat Foxtrot (CP-1000, CP-2000, …) přes **Modbus TCP**.

**PLC samo popisuje, co obsahuje.** Program v PLC má v paměti *deskriptor*: seznam zařízení (skupin), objektů (světla, spínače, tlačítka, teploty, binární vstupy), jejich názvy a Modbus adresy. Integrace si ho po připojení přečte a podle něj vytvoří zařízení a entity. Nic se nedefinuje v YAML. Stejná integrace funguje pro libovolné PLC s programem, který deskriptor obsahuje.

## Funkce

- **Přidání přes UI:** *Nastavení → Zařízení a služby → Přidat integraci → Tecomat PLC* (IP, port, unit ID).
- **Zařízení podle skupin v PLC** (skupina 0 = samotné PLC, ostatní připojené přes něj) s navrženou oblastí.
- **Entity:**
  - `light`, `switch`,
  - `event` (tlačítka: `short` / `long` / `double`),
  - `sensor` (teploty s korekcí, diagnostika),
  - `number` (korekce teploty v sekci Konfigurace),
  - `binary_sensor` (vstupy, poruchy, spojení HA ↔ PLC).
- **Konfigurace ovladačů** (jen pro administrátory, vzhled podle motivu HA). Je dostupná:
  - z *Nastavení → Zařízení a služby → Tecomat PLC → Nastavit* (odkaz „Otevřít konfiguraci ovladačů“),
  - ze stránky zařízení PLC (tlačítko *Navštívit*),
  - volitelně z bočního menu (*Nastavit → Zobrazení → Přidat do bočního menu*).

  Obsahuje:
  - matice *tlačítko × okruh* (krátký / dlouhý stisk: přepni / vypni / zapni, stmívání),
  - korekce teplot,
  - **ruční verze konfigurace** (uložit / obnovit / smazat, sdílené pro všechny uživatele, součást záloh HA),
  - export a import JSON.
- **PLC je zdroj pravdy:** konfigurace se čte z PLC a ukládá v PLC (RETAIN). Integrace nikdy nic nezapisuje automaticky (kromě heartbeatu).
- **Heartbeat** HA → PLC každých 30 s. PLC pozná výpadek HA a přejde do záložního režimu.
- **Změna programu v PLC** (vyšší verze v deskriptoru) se pozná automaticky a integrace se znovu načte.
- **Přechod na jiné PLC** (např. CP-1000 → CP-2000): *Nastavit → Připojení k PLC*, změnit IP. Entity zůstanou, pokud nový program používá stejná `uid` objektů.
- Jedno spojení Modbus TCP, čtení po blocích (CP-1000 povolí max. 2 Modbus klienty současně).

## Instalace

### Ručně
1. Zkopírujte složku `custom_components/tecomat_plc` do `/config/custom_components/` (např. přes Studio Code Server).
2. Restartujte HA.
3. Přidejte integraci *Tecomat PLC*.

### HACS (vlastní repozitář)
1. Nahrajte tento repozitář na GitHub.
2. HACS → ⋮ → *Vlastní repozitáře* → URL repozitáře, typ *Integrace*.
3. Nainstalujte *Tecomat PLC*, restartujte HA a přidejte integraci.

> **Před přidáním integrace odeberte YAML package s Modbusem pro stejné PLC** (např. `cp1000_milnik1b.yaml`). CP-1000 obslouží jen 2 Modbus klienty současně a průvodce si při ověření otevírá vlastní spojení.

## Protokol deskriptoru (verze 1)

Adresy jsou Modbus holding registry (v PLC Tecomat platí `%RW(2·N)` = adresa `N`).

**Hlavička `hdr[0..31]` na adrese 24000**

| idx | význam | idx | význam |
|---|---|---|---|
| 0 | magic `0x5443` ('TC') | 9 | základ schránky konfigurace |
| 1 | verze protokolu (1) | 10 | základ čtecího okna |
| 2 | typ PLC (1000, 2000, …) | 11 | základ meta tabulky |
| 3 | verze programu (při změně objektů zvýšit) | 12 | délka meta záznamu (8) |
| 4 | počet skupin | 13 | základ tabulky řetězců |
| 5 | počet objektů | 14 | počet řetězců |
| 6 | max. tlačítek v matici (`maxB`) | 15 | adresa testovacích řetězců `'TECO','TECO'` |
| 7 | max. okruhů v matici | 16 | offset názvů objektů v tabulce řetězců (64) |
| 8 | základ stavového bloku | 17 | offset oblastí skupin (32) |

**Meta záznam objektu** (8 registrů): `typ, skupina, adresa, p1, p2, p3, flags, uid`

| typ | objekt | adresa | p1 | p2 / flags |
|---|---|---|---|---|
| 1 | LIGHT | stav/povel (0/1) | řádek matice (okruh), `0xFFFF` = mimo matici | flags bit1 = stmívatelné |
| 2 | SWITCH | stav/povel (0/1) | řádek matice | |
| 3 | BUTTON | událost `čítač·256 + typ` (1 short, 2 long, 3 double) | sloupec matice (tlačítko) | |
| 4 | TEMP | surová ×10 (INT), +1 korigovaná, +2 korekce | index korekce | |
| 5 | BINARY | registr | číslo bitu | p2 = třída (0 –, 1 problem, 2 connectivity, 3 power, 4 door, 5 window, 6 motion, 7 opening); flags bit0 = invertovat |

**Řetězce:** pole `STRING[n]` v kódování cp1250. Skupiny `0..31`, oblasti `32..63`, objekty `64..`. Délka položky a pořadí bajtů se zjistí z testovacích řetězců `'TECO','TECO'`.

**Stavový blok** (offset od základu):
- 0 heartbeat HA → PLC
- 1 heartbeat PLC (s)
- 4 PLC vidí HA (0/1)
- 5 potvrzení schránky (`seq`)
- 6 kontrolní součet konfigurace
- 7 požadavek čtecího okna

**Schránka konfigurace:** `[seq, n, idx1, val1, …]`, max. 32 dvojic.
- Index `okruh·maxB + tlačítko`: kód `bity 0–1 krátký, 2–3 dlouhý (0 nic, 1 přepni, 2 vypni, 3 zapni), 4–5 stmívání (1 přidej, 2 uber)`.
- Index `10000 + k`: korekce teploty ×10 (INT).
- PLC potvrdí zápisem `seq` do stavového bloku (offset 5).

**Čtecí okno:** po zápisu začátku bloku do stavového bloku (offset 7) PLC plní `[ozvěna, 32 registrů]`.
- Konfigurace: 2 bajty na registr (nižší = sudý index).
- Korekce (`10000+`): 1 INT na registr.

**Kontrolní součet:** `Σ kód·(index mod 251 + 1)` + `Σ korekce_u16·((10000+k) mod 251 + 1)`, vše mod 65536.

## Vývoj a testy

```bash
uv venv --python 3.13 .venv && uv pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

Testy běží ve skutečném Home Assistant proti simulátoru PLC (`tests/mock_plc.py`), který napodobuje program `prgMain_milnik1c.ST`.

## Licence

[MIT](LICENSE). Integrace není oficiálním produktem Teco a.s. Tecomat® a Foxtrot® jsou ochranné známky Teco a.s.
