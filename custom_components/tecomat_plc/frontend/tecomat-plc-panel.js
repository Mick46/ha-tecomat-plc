// Tecomat PLC: konfigurace ovladačů (stránka dodávaná integrací tecomat_plc)
//
// Vzhled podle Home Assistant: barvy a rozměry z proměnných aktivního motivu
// (světlý / tmavý / vlastní), horní lišta, karty, tlačítka, ikony mdi a dialogy.
//
// Data přes websocket API integrace:
//   tecomat_plc/entries, /info (protokol 1: matice, 2: akce tlačítek), /config/get, /config/set,
//   /live (aktuální hodnoty), /press (akce PLC),
//   /versions/list, /versions/save, /versions/restore, /versions/delete, /versions/import
//
// PLC je zdroj pravdy: konfigurace se čte z PLC, verze se ukládají ručně.

const GROUPS = [
  { key: "s", shift: 0, title: "Krátký stisk", opts: [[1, "Přepni"], [2, "Vypni"], [3, "Zapni"]] },
  { key: "l", shift: 2, title: "Dlouhý stisk", opts: [[1, "Přepni"], [2, "Vypni"], [3, "Zapni"]] },
  { key: "d", shift: 4, title: "Stmívání", opts: [[1, "Přidej"], [2, "Uber"]] },
];
const CORR_BASE = 10000;
// protokol 2: na tlačítko 16 registrů = 8 akcí (0–3 krátký, 4–7 dlouhý stisk), akce = [UID cíle, povel·256 + hodnota]
const SLOTS = 16;
const CMDS = [[1, "Přepni"], [2, "Zapni"], [3, "Vypni"], [4, "Jas na %", true], [5, "Jas přidat %", true]];

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const zmen = (n) => `${n} ${n === 1 ? "změna" : n >= 2 && n <= 4 ? "změny" : "změn"}`;
const polozek = (n) => `${n} ${n === 1 ? "položka" : n >= 2 && n <= 4 ? "položky" : "položek"}`;
const icon = (name, cls = "") => `<ha-icon class="${cls}" icon="${name}"></ha-icon>`;

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--paper-font-body1_-_font-family, var(--ha-font-family-body, Roboto, sans-serif));
    --tp-radius: var(--ha-card-border-radius, 12px);
    --tp-tint: color-mix(in srgb, var(--primary-color) 14%, transparent);
  }
  .toolbar {
    position: sticky; top: 0; z-index: 10;
    display: flex; align-items: center; gap: 8px;
    height: var(--header-height, 56px); padding: 0 12px 0 4px; box-sizing: border-box;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color, #fff));
    border-bottom: var(--app-header-border-bottom, none);
    font-size: 20px;
  }
  .toolbar .title { flex: 1; margin-left: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .toolbar select {
    background: transparent; color: inherit; border: 1px solid currentColor; border-radius: 8px;
    padding: 4px 8px; font-size: 14px; opacity: .9;
  }
  .toolbar select option { color: var(--primary-text-color); background: var(--card-background-color); }
  .iconbtn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 40px; height: 40px; border-radius: 50%; border: none; cursor: pointer;
    background: transparent; color: inherit;
  }
  .iconbtn:hover:not([disabled]) { background: color-mix(in srgb, currentColor 12%, transparent); }
  .iconbtn[disabled] { opacity: .4; cursor: default; }
  .content {
    display: grid; grid-template-columns: minmax(280px, 360px) 1fr; gap: 16px;
    padding: 16px; max-width: 1400px; margin: 0 auto; box-sizing: border-box;
  }
  .content.narrow { grid-template-columns: 1fr; padding: 8px; }
  .col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .card {
    background: var(--ha-card-background, var(--card-background-color));
    border-radius: var(--tp-radius);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color));
    box-shadow: var(--ha-card-box-shadow, none);
    overflow: hidden;
  }
  .card-header {
    display: flex; align-items: center; gap: 12px;
    padding: 16px 16px 8px; font-size: 20px; font-weight: 400;
  }
  .card-header .sub { font-size: 14px; color: var(--secondary-text-color); }
  .card-header ha-icon { color: var(--state-icon-color, var(--primary-color)); }
  .card-content { padding: 0 16px 16px; }
  .card-actions {
    display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end;
    padding: 8px 16px; border-top: 1px solid var(--divider-color);
  }
  .section { padding: 12px 16px 4px; font-size: 12px; font-weight: 500; letter-spacing: .06em;
    text-transform: uppercase; color: var(--secondary-text-color); }
  .item {
    display: flex; align-items: center; gap: 16px; padding: 8px 16px; min-height: 48px;
    cursor: pointer; box-sizing: border-box;
  }
  .item:hover { background: var(--secondary-background-color); }
  .item.sel { background: var(--tp-tint); }
  .item.sel .name { color: var(--primary-color); font-weight: 500; }
  .item ha-icon { color: var(--state-icon-color, var(--secondary-text-color)); }
  .item .text { display: flex; flex-direction: column; min-width: 0; }
  .item .name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .item .secondary { font-size: 12px; color: var(--secondary-text-color); }
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    height: 36px; padding: 0 16px; border-radius: 18px; cursor: pointer;
    font: inherit; font-size: 14px; font-weight: 500; letter-spacing: .02em;
    border: 1px solid transparent; background: transparent; color: var(--primary-color);
  }
  .btn ha-icon { --mdc-icon-size: 18px; }
  .btn:hover:not([disabled]) { background: var(--tp-tint); }
  .btn.filled { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn.filled:hover:not([disabled]) { filter: brightness(1.08); }
  .btn.outlined { border-color: var(--divider-color); }
  .btn.danger { color: var(--error-color); }
  .btn[disabled] { opacity: .45; cursor: default; }
  table { width: 100%; border-collapse: collapse; }
  th { font-weight: 500; font-size: 13px; color: var(--secondary-text-color); padding: 8px 6px; text-align: center; }
  th.left, td.left { text-align: left; }
  th.grp { border-bottom: 2px solid var(--primary-color); color: var(--primary-text-color); }
  td { padding: 8px 6px; border-top: 1px solid var(--divider-color); text-align: center; vertical-align: middle; }
  td.left .secondary { display: block; font-size: 12px; color: var(--secondary-text-color); }
  .scroll { overflow-x: auto; }
  .chip {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 64px; height: 32px; padding: 0 10px; border-radius: 8px; box-sizing: border-box;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color);
    font: inherit; font-size: 13px; cursor: pointer;
  }
  .chip:hover:not([disabled]) { background: var(--secondary-background-color); }
  .chip.on { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .chip[disabled] { opacity: .3; cursor: default; }
  .temp { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; padding: 12px 16px; border-top: 1px solid var(--divider-color); }
  .temp ha-icon { grid-row: span 2; align-self: center; color: var(--state-icon-color, var(--secondary-text-color)); }
  .temp .values { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
  .value { display: flex; flex-direction: column; }
  .value b { font-size: 18px; font-weight: 400; }
  .value small { font-size: 12px; color: var(--secondary-text-color); }
  input[type=number], input[type=text] {
    height: 40px; box-sizing: border-box; padding: 0 12px; border-radius: 8px;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent);
    color: var(--primary-text-color); font: inherit; font-size: 16px;
  }
  input[type=number] { width: 90px; }
  td select {
    height: 40px; max-width: 100%; box-sizing: border-box; padding: 0 8px; border-radius: 8px;
    border: 1px solid var(--divider-color); background: var(--secondary-background-color, transparent);
    color: var(--primary-text-color); font: inherit; font-size: 14px;
  }
  td select.wide { width: 100%; }
  td select option, td select optgroup { color: var(--primary-text-color); background: var(--card-background-color); }
  input:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
  .alert {
    display: flex; align-items: center; gap: 12px; padding: 8px 12px; margin: 0 16px 8px;
    border-radius: 8px; font-size: 14px;
  }
  .alert.success { background: color-mix(in srgb, var(--success-color, #43a047) 15%, transparent); }
  .alert.success ha-icon { color: var(--success-color, #43a047); }
  .alert.warning { background: color-mix(in srgb, var(--warning-color, #ffa600) 15%, transparent); }
  .alert.warning ha-icon { color: var(--warning-color, #ffa600); }
  .alert.error { background: color-mix(in srgb, var(--error-color, #db4437) 15%, transparent); }
  .alert.error ha-icon { color: var(--error-color, #db4437); }
  .alert.info { background: var(--tp-tint); }
  .alert.info ha-icon { color: var(--primary-color); }
  .ver { display: flex; align-items: center; gap: 16px; padding: 8px 8px 8px 16px; border-top: 1px solid var(--divider-color); }
  .ver.cur { background: var(--tp-tint); }
  .ver .text { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .ver .secondary { font-size: 12px; color: var(--secondary-text-color); }
  .ver ha-icon { color: var(--state-icon-color, var(--secondary-text-color)); }
  .note { font-size: 12px; color: var(--secondary-text-color); padding: 8px 16px 16px; line-height: 1.5; }
  .empty { padding: 16px; color: var(--secondary-text-color); }
  .backdrop {
    position: fixed; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center;
    background: var(--mdc-dialog-scrim-color, rgba(0, 0, 0, .32));
  }
  .dialog {
    width: min(480px, calc(100vw - 32px)); background: var(--card-background-color);
    border-radius: var(--ha-dialog-border-radius, 24px); box-shadow: 0 8px 32px rgba(0, 0, 0, .3);
    padding: 24px 24px 12px; box-sizing: border-box;
  }
  .dialog h2 { margin: 0 0 16px; font-size: 22px; font-weight: 400; }
  .dialog p { margin: 0 0 16px; color: var(--secondary-text-color); line-height: 1.5; }
  .dialog input { width: 100%; margin-bottom: 8px; }
  .dialog .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
`;

const STYLE_V2 = `
  .tabs { display: flex; gap: 2px; }
  .tabs button { background: transparent; border: 0; color: inherit; opacity: .75; font: inherit; font-size: 15px;
    padding: 0 12px; height: var(--header-height, 56px); cursor: pointer; border-bottom: 2px solid transparent; }
  .tabs button.on { opacity: 1; border-bottom-color: currentColor; }
  .content.three { grid-template-columns: minmax(200px, 240px) minmax(260px, 320px) 1fr; }
  .content.three.narrow { grid-template-columns: 1fr; }
  .item .count { margin-left: auto; font-size: 12px; color: var(--secondary-text-color); }
  .floor { display: flex; align-items: center; gap: 8px; margin-top: 8px; padding: 8px 16px; font-size: 14px; font-weight: 500;
    color: var(--primary-color); background: var(--secondary-background-color); border-top: 1px solid var(--divider-color);
    border-bottom: 1px solid var(--divider-color); }
  .floor ha-icon { --mdc-icon-size: 18px; }
  .stale { padding: 2px 16px; font-size: 13px; }
  .stale code { color: var(--secondary-text-color); }
  .sw { padding: 12px 16px 16px; border-top: 1px solid var(--divider-color); }
  .swname { margin-bottom: 8px; display: flex; gap: 8px; align-items: baseline; }
  .swname .secondary { font-size: 12px; color: var(--secondary-text-color); }
  .swrow { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .plate { display: inline-flex; gap: 4px; padding: 6px; border-radius: 10px;
    background: var(--secondary-background-color); border: 2px solid var(--divider-color); }
  .rocker { display: flex; flex-direction: column; gap: 4px; }
  .key { width: 64px; height: 44px; border-radius: 6px; cursor: pointer; position: relative; font: inherit; font-size: 11px;
    background: var(--card-background-color); color: var(--secondary-text-color); border: 1px solid var(--divider-color);
    display: flex; align-items: center; justify-content: center; }
  .key:hover { border-color: var(--primary-color); }
  .key.sel { background: var(--primary-color); color: var(--text-primary-color, #fff); border-color: var(--primary-color); }
  .key.round { width: 52px; height: 52px; border-radius: 50%; }
  .key .cnt { position: absolute; top: -7px; right: -7px; min-width: 18px; height: 18px; border-radius: 9px; padding: 0 4px;
    background: var(--success-color, #43a047); color: #fff; font-size: 11px; display: flex; align-items: center; justify-content: center; }
  .tbox { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
  .tbox .big { font-size: 26px; line-height: 1.1; }
  .tbox .lbl { color: var(--secondary-text-color); font-size: 12px; }
  .corr { display: inline-flex; align-items: center; gap: 4px; }
  .mini { width: 26px; height: 26px; border-radius: 6px; border: 1px solid var(--divider-color); background: transparent;
    color: var(--primary-text-color); cursor: pointer; font: inherit; }
  .mini:hover:not([disabled]) { border-color: var(--primary-color); }
  .counters { display: flex; gap: 16px; padding: 0 16px 8px; font-size: 13px; color: var(--secondary-text-color); }
  .counters b { color: var(--primary-text-color); }
  .counters .full b { color: var(--primary-color); }
  .filters { display: flex; gap: 8px; align-items: center; padding: 0 16px 12px; flex-wrap: wrap; }
  .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; }
  .seg button { background: transparent; color: var(--primary-text-color); border: 0; padding: 6px 12px; cursor: pointer; font: inherit; }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .filters select { height: 34px; border-radius: 8px; border: 1px solid var(--divider-color); padding: 0 8px; font: inherit;
    background: var(--secondary-background-color); color: var(--primary-text-color); }
  .three td.left { white-space: nowrap; min-width: 150px; }
  .three .chip { min-width: 0; padding: 0 10px; height: 30px; }
  .three td { padding: 6px 3px; }
  .chip.sm { padding: 0 8px; }
  td.dim { white-space: nowrap; }
  input.pct { width: 70px; height: 30px; margin-left: 4px; padding: 0 6px; }
  input.num { width: 80px; height: 34px; }
  .unit { margin-left: 4px; font-size: 12px; color: var(--secondary-text-color); }
  td.bigtd { font-size: 18px; }
  .title2 { margin-left: 12px; white-space: nowrap; }
  .tabs { margin-left: 16px; }
  .status { display: flex; align-items: center; gap: 6px; cursor: pointer; margin-right: 4px; }
  .st { display: inline-flex; align-items: center; gap: 2px; }
  .st small { font-size: 12px; }
  .st.ok ha-icon { color: var(--success-color, #43a047); }
  .st.warn ha-icon { color: var(--warning-color, #ffa600); }
  .st.bad ha-icon { color: var(--error-color, #db4437); }
  td.pfs { text-align: left; }
  .pf { display: inline-flex; align-items: center; gap: 6px; margin: 2px 16px 2px 0; white-space: nowrap; }
  .pf span:first-child { color: var(--secondary-text-color); font-size: 13px; }
  input.num.wide { width: 120px; }
  .form { display: flex; flex-direction: column; gap: 10px; padding: 4px 16px 12px; }
  .form .row { display: grid; grid-template-columns: 130px 1fr; align-items: center; gap: 12px; }
  .form .row > span:first-child { color: var(--secondary-text-color); }
  .form select, .form input[type=time] { height: 36px; border-radius: 8px; border: 1px solid var(--divider-color); padding: 0 8px; font: inherit;
    background: var(--secondary-background-color); color: var(--primary-text-color); max-width: 100%; }
  .form .row input[type=checkbox] { justify-self: start; width: 20px; height: 20px; }
  .col2 { display: flex; flex-direction: column; gap: 6px; }
  .win { display: flex; align-items: center; gap: 6px; }
  .vers { max-width: 900px; margin: 0 auto; padding: 16px; display: flex; flex-direction: column; gap: 16px; }
  .tech { display: flex; flex-direction: column; gap: 16px; padding: 16px; max-width: 1400px; margin: 0 auto; }
  .tech .tcols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; align-items: start; }
  .tech.narrow .tcols { grid-template-columns: 1fr; }
  .tech .tcol { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .tech .trow { display: grid; grid-template-columns: minmax(150px, 210px) 1fr; align-items: center; gap: 12px; padding: 6px 16px;
    border-top: 1px solid var(--divider-color); }
  .tech .trow > span:first-child { color: var(--secondary-text-color); }
  .tech .trow .pf { margin: 0 12px 0 0; }
  .tech input[type=time], .tech select { height: 34px; border-radius: 8px; border: 1px solid var(--divider-color); padding: 0 6px; font: inherit;
    background: var(--secondary-background-color); color: var(--primary-text-color); }
  .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 8px; overflow: hidden; flex-wrap: wrap; }
  .seg button { background: transparent; color: var(--primary-text-color); border: 0; padding: 7px 14px; cursor: pointer; font: inherit; }
  .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .seg button[disabled] { cursor: default; opacity: .6; }
  .tchips { display: flex; gap: 20px; flex-wrap: wrap; padding: 6px 16px 12px; }
  .tchip { display: flex; flex-direction: column; min-width: 100px; }
  .tchip span { color: var(--secondary-text-color); font-size: 12px; }
  .tchip b { font-size: 20px; font-weight: 400; }
  .dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: var(--disabled-text-color, #888); margin-right: 6px; vertical-align: middle; }
  .dot.on { background: var(--state-climate-heat-color, #ff8100); box-shadow: 0 0 6px var(--state-climate-heat-color, #ff8100); }
  .badge { margin-left: auto; font-size: 12px; padding: 3px 10px; border-radius: 12px; background: var(--secondary-background-color);
    color: var(--secondary-text-color); font-weight: 400; }
  .badge.on { color: var(--success-color, #43a047); }
  .badge.warn { color: var(--warning-color, #ffa600); }
`;

class TecomatPlcPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._entries = [];
    this._entry = null;
    this._info = null;
    this._cfg = null;
    this._versions = [];
    this._base = null;
    this._sel = null;
    this._busy = "";
    this._msg = "";
    this._error = "";
    this._dialog = null;
    this._narrow = false;
    this._draft = null;
    this._room = null;
    this._tab = "ctl";
    this._swKey = null;
    this._pos = 1;
    this._mode = "room";
    this._otherRoom = null;
    this._setRoom = null;
    this._auto = null;
    this._autoDraft = null;
    this._live = null;
    this._liveTimer = null;
    this._stale = null;
  }

  disconnectedCallback() {
    this._stopLive();
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    const mb = this.shadowRoot.querySelector("ha-menu-button");
    if (mb) mb.hass = h;
    if (first) this._init();
  }
  set narrow(n) {
    const changed = this._narrow !== n;
    this._narrow = n;
    if (changed && this._hass) this._render();
  }
  set panel(p) {}

  _ws(type, data = {}) {
    return this._hass.callWS({ type: `tecomat_plc/${type}`, entry_id: this._entry, ...data });
  }

  // ---------------------------------------------------------------- data
  async _init() {
    this._render();
    try {
      this._entries = await this._hass.callWS({ type: "tecomat_plc/entries" });
    } catch (e) {
      this._error = "Integrace Tecomat PLC není dostupná: " + (e.message || e.code);
      this._render();
      return;
    }
    if (!this._entries.length) {
      this._error = "Žádné připojené PLC. Přidejte integraci v Nastavení → Zařízení a služby.";
      this._render();
      return;
    }
    await this._selectEntry(this._entries[0].entry_id);
  }

  async _selectEntry(id) {
    this._entry = id;
    this._stale = null;
    this._info = null;
    this._cfg = null;
    this._error = "";
    this._render();
    try {
      this._info = await this._ws("info");
      const list = this._btnList();
      if (!this._v2() && (this._sel === null || !list.find((b) => b.m === this._sel)))
        this._sel = list.length ? list[0].m : null;
      this._versions = await this._ws("versions/list");
      if (!this._base && this._versions.length) this._base = this._versions[0].id;
    } catch (e) {
      this._error = e.message || String(e);
    }
    await this._readPlc();
  }

  async _readPlc() {
    await this._run("Načítám konfiguraci z PLC…", async () => {
      this._cfg = await this._ws("config/get");
      this._msg = "Načteno z PLC v " + new Date().toLocaleTimeString("cs-CZ");
    });
  }

  async _run(label, fn) {
    this._busy = label;
    this._render();
    try {
      await fn();
      this._error = "";
    } catch (e) {
      this._error = e.message || String(e);
      try {
        this._cfg = await this._ws("config/get");
      } catch (e2) {
        /* PLC nedostupné */
      }
    }
    this._busy = "";
    this._render();
  }

  _v2() {
    return !!(this._info && this._info.protocol >= 2);
  }
  _btnList() {
    if (!this._info) return [];
    return this._v2() ? this._info.buttons2.map((b) => ({ ...b, m: b.b })) : this._info.buttons;
  }
  // protokol 2: akce tlačítka z konfigurace (nebo rozpracovaný koncept)
  _actions(b) {
    if (this._draft && this._draft.b === b) return this._draft.acts;
    const m = (this._cfg && this._cfg.map) || {};
    const acts = [];
    for (let a = 0; a < 8; a++) {
      const uid = Number(m[String(b * SLOTS + a * 2)] || 0);
      const cv = Number(m[String(b * SLOTS + a * 2 + 1)] || 0);
      acts.push({ uid, cmd: uid ? cv >> 8 : 1, val: uid ? cv & 255 : 0 });
    }
    return acts;
  }
  _targetLabel(t, withRoom = true) {
    return `${withRoom ? this._groupName(t.group) + " · " : ""}${t.sub} · ${t.name}`;
  }
  _paramValue(p) {
    const v = Number((this._cfg && this._cfg.map[String(20000 + p.p)]) || 0);
    return (v > 32767 ? v - 65536 : v) / 10 ** p.dec;
  }
  async _saveParam(p, input) {
    let v = parseFloat(String(input).replace(",", "."));
    if (isNaN(v)) return;
    let raw = Math.round(v * 10 ** p.dec);
    raw = Math.max(p.min, Math.min(p.max, raw));
    await this._run("Zapisuji nastavení…", async () => {
      await this._ws("config/set", { pairs: [[20000 + p.p, raw]] });
      this._cfg = await this._ws("config/get");
      this._msg = `${p.name}: zapsáno do PLC`;
    });
  }
  _versionsCard(ready) {
    const versions = this._versions.length
      ? this._versions
          .map(
            (v) => `
        <div class="ver ${this._base === v.id ? "cur" : ""}">
          ${icon(v.source === "import" ? "mdi:file-import" : "mdi:history")}
          <div class="text"><span>${esc(v.name)}</span>
            <span class="secondary">${new Date(v.ts).toLocaleString("cs-CZ")}${v.source === "import" ? " · import" : ""}</span></div>
          <button class="btn" data-restore="${v.id}" ${ready ? "" : "disabled"}>${icon("mdi:restore")}Obnovit</button>
          <button class="iconbtn" style="color:var(--secondary-text-color)" data-del="${v.id}" title="Smazat" ${this._busy ? "disabled" : ""}>${icon("mdi:delete")}</button>
        </div>`
          )
          .join("")
      : `<div class="empty">Zatím žádná uložená verze.</div>`;
    return `
      <div class="card">
        <div class="card-header">${icon("mdi:history")}Verze konfigurace</div>
        ${versions}
        <div class="note">Verze obsahují akce tlačítek, nastavení a korekce teplot. Ukládají se ručně z aktuálního obsahu PLC a jsou společné pro všechny uživatele (součást záloh Home Assistant).</div>
        <div class="card-actions">
          <button class="btn" id="importbtn" ${this._busy ? "disabled" : ""}>${icon("mdi:upload")}Import</button>
          <button class="btn" id="export" ${ready ? "" : "disabled"}>${icon("mdi:download")}Export</button>
          <button class="btn filled" id="savever" ${ready ? "" : "disabled"}>${icon("mdi:content-save")}Uložit verzi</button>
          <input id="importfile" type="file" accept=".json,application/json" style="display:none">
        </div>
      </div>`;
  }

  // ================================================================ protokol 2: záložky
  // Ovladače (grafický vypínač + akce), Nastavení (parametry a korekce po místnostech), Zálohy

  _switches() {
    const map = new Map();
    for (const b of this._info.buttons2) {
      const key = b.sw ? `w${b.sw}` : `b${b.b}`;
      if (!map.has(key)) {
        const name = b.sw ? b.name.replace(/ klapka.*$/, "") : b.name;
        map.set(key, { key, sw: b.sw, name, group: b.group, type: b.sw ? b.swtype : 1, keys: {} });
      }
      map.get(key).keys[b.sw ? b.pos : 1] = b.b;
    }
    return [...map.values()];
  }
  _swTemp(sw) {
    return sw.sw ? this._info.temps.find((t) => t.sw === sw.sw) : null;
  }
  _actCount(b, long) {
    return this._actions(b).filter((a, i) => a.uid && (i >= 4) === long).length;
  }
  async _writeActions(b, acts) {
    // zhutnit: krátký stisk do slotů 0–3, dlouhý do 4–7
    const short = acts.filter((a, i) => a.uid && i < 4);
    const long = acts.filter((a, i) => a.uid && i >= 4);
    const slots = [...short, ...Array(4 - short.length).fill(null), ...long, ...Array(4 - long.length).fill(null)];
    const pairs = [];
    slots.forEach((x, a) => {
      pairs.push([b * SLOTS + a * 2, x ? x.uid : 0]);
      pairs.push([b * SLOTS + a * 2 + 1, x ? x.cmd * 256 + (x.val || 0) : 0]);
    });
    await this._run("Zapisuji do PLC…", async () => {
      await this._ws("config/set", { pairs });
      this._cfg = await this._ws("config/get");
      this._msg = "Zapsáno do PLC";
    });
  }
  async _toggleAct(b, uid, long, cmd, val, fromInput = false) {
    if (!this._cfg || this._busy) return;
    const acts = this._actions(b).map((x) => ({ ...x }));
    const from = long ? 4 : 0;
    const i = acts.findIndex((a, k) => a.uid === uid && k >= from && k < from + 4);
    if (i >= 0 && acts[i].cmd === cmd && !fromInput) acts[i] = { uid: 0, cmd: 1, val: 0 };
    else if (i >= 0) acts[i] = { uid, cmd, val };
    else {
      const free = acts.findIndex((a, k) => !a.uid && k >= from && k < from + 4);
      if (free < 0) {
        this._error = "Na jeden stisk jdou nejvýš 4 akce.";
        this._render();
        return;
      }
      acts[free] = { uid, cmd, val };
    }
    await this._writeActions(b, acts);
  }
  // korekce: kliknutí na −/+ mění jen koncept, do PLC se zapíše 3 s po posledním kliknutí (všechny najednou)
  _corrRaw(idx) {
    const d = this._corrDraft && this._corrDraft[idx];
    return d !== undefined ? d : Number((this._cfg && this._cfg.corr[String(idx)]) || 0);
  }
  _stepCorr(t, d) {
    this._corrDraft = this._corrDraft || {};
    this._corrDraft[t.idx] = Math.max(-100, Math.min(100, this._corrRaw(t.idx) + d));
    clearTimeout(this._corrTimer);
    this._corrTimer = setTimeout(() => this._flushCorr(), 3000);
    this._render();
  }
  async _flushCorr() {
    const draft = this._corrDraft || {};
    this._corrDraft = null;
    const pairs = Object.entries(draft).map(([idx, v]) => [CORR_BASE + Number(idx), v]);
    if (!pairs.length) return;
    await this._run("Zapisuji korekce…", async () => {
      await this._ws("config/set", { pairs });
      this._cfg = await this._ws("config/get");
      this._msg = pairs.length > 1 ? `Korekce zapsány do PLC (${pairs.length})` : "Korekce zapsána do PLC";
    });
  }
  _exportVersion(ver) {
    const map = ver ? ver.map : this._cfg.map;
    const corr = ver ? ver.corr : this._cfg.corr;
    const data = {
      type: "tecomat-plc-ovladace",
      exported: new Date().toISOString(),
      plc: this._info ? this._info.model : "",
      protocol: this._info ? this._info.protocol : 1,
      name: ver ? ver.name : "aktuální konfigurace",
      current: { map, corr },
      versions: [],
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    const d = new Date();
    const p = (x) => String(x).padStart(2, "0");
    const slug = (ver ? ver.name : "aktualni").normalize("NFKD").replace(/[^\w-]+/g, "-").replace(/-+/g, "-").slice(0, 40);
    a.href = URL.createObjectURL(blob);
    a.download = `tecomat-${slug}-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  _drawSwitch(sw) {
    const k = (pos, label, cls = "") => {
      const b = sw.keys[pos];
      if (b === undefined) return "";
      const n = this._actCount(b, false) + this._actCount(b, true);
      const sel = this._swKey === sw.key && this._pos === pos ? "sel" : "";
      return `<button class="key ${cls} ${sel}" data-sw="${sw.key}" data-pos="${pos}">${label}${n ? `<span class="cnt">${n}</span>` : ""}</button>`;
    };
    if (sw.type === 1) return `<div class="plate">${k(1, "", "round")}</div>`;
    if (sw.type === 2) return `<div class="plate"><div class="rocker">${k(1, "UP")}${k(2, "DOWN")}</div></div>`;
    return `<div class="plate"><div class="rocker">${k(1, "UP")}${k(2, "DOWN")}</div><div class="rocker">${k(3, "UP")}${k(4, "DOWN")}</div></div>`;
  }
  _tempBox(t, ready) {
    const tv = (this._cfg && this._cfg.temps[String(t.idx)]) || {};
    const corr = this._corrRaw(t.idx) / 10;
    const f = (v) => (v === null || v === undefined || v <= -999 ? "–" : `${(v / 10).toFixed(1)} °C`);
    const dis = ready ? "" : "disabled";
    return `<div class="tbox">
      <span class="big">${f(tv.cor)}</span>
      <span class="lbl">naměřeno ${f(tv.raw)}</span>
      <span class="lbl corr">korekce <button class="mini" data-corr="${t.idx}" data-d="-1" ${dis}>−</button><span>${corr > 0 ? "+" : ""}${corr.toFixed(1)}</span><button class="mini" data-corr="${t.idx}" data-d="1" ${dis}>+</button></span>
    </div>`;
  }

  _tabCtl(ready) {
    const info = this._info;
    const sws = this._switches();
    const per = {};
    for (const x of sws) per[x.group] = (per[x.group] || 0) + 1;
    const rooms = this._sortRooms(info.groups.filter((g) => per[g.id]));
    if (this._room === null || !per[this._room]) this._room = rooms.length ? rooms[0].id : null;
    const list = sws.filter((x) => x.group === this._room);
    let sw = list.find((x) => x.key === this._swKey);
    if (!sw) {
      sw = list[0] || null;
      this._swKey = sw ? sw.key : null;
      this._pos = 1;
    }
    const roomCard = `<div class="card"><div class="card-header">${icon("mdi:floor-plan")}Místnosti</div>
      ${this._roomItems(rooms, this._room, per, "data-room")}
      <div style="height:8px"></div></div>`;
    const swCard = `<div class="card"><div class="card-header">${icon("mdi:light-switch")}<div style="display:flex;flex-direction:column">Ovladače<span class="sub">${esc(this._groupName(this._room))}</span></div></div>
      ${list
        .map((x) => {
          const t = this._swTemp(x);
          return `<div class="sw"><div class="swname">${esc(x.name)}<span class="secondary">${x.type === 4 ? "WSB2-40" : x.type === 2 ? "WSB2-20" : "tlačítko na vstupu"}</span></div>
            <div class="swrow">${this._drawSwitch(x)}${t ? this._tempBox(t, ready) : ""}</div></div>`;
        })
        .join("")}</div>`;
    let right = `<div class="card"><div class="card-header">${icon("mdi:gesture-tap-button")}Akce</div>${this._alerts(false)}<div class="empty">Vyberte ovladač.</div></div>`;
    if (sw && this._cfg) {
      const b = sw.keys[this._pos] ?? sw.keys[1];
      const keyName = sw.type === 1 ? "tlačítko" : sw.type === 2 ? (this._pos === 1 ? "klapka UP" : "klapka DOWN")
        : ["", "klapka levá UP", "klapka levá DOWN", "klapka pravá UP", "klapka pravá DOWN"][this._pos];
      const acts = this._actions(b);
      const sN = this._actCount(b, false), lN = this._actCount(b, true);
      const targetRoom = this._otherRoom ?? sw.group;
      let targets = info.targets;
      if (this._mode === "room") targets = targets.filter((t) => t.group === targetRoom);
      if (this._mode === "sel") targets = targets.filter((t) => acts.some((a) => a.uid === t.uid));
      const cell = (t, long) => {
        const a = acts.find((x, i) => x.uid === t.uid && (i >= 4) === long);
        const cmd = a ? a.cmd : 0;
        const dis = ready ? "" : "disabled";
        const L = long ? 1 : 0;
        if (t.kind === "cover" || t.kind === "gate") {
          const c = t.kind === "cover" ? 6 : 7;
          const l = t.kind === "cover" ? (long ? "Do konce" : "Krok / stop") : "Impulz";
          return `<td colspan="3"><button class="chip ${cmd === c ? "on" : ""}" data-t="${t.uid}" data-l="${L}" data-c="${c}" ${dis}>${l}</button></td><td></td>`;
        }
        let h = [[1, "Přepni"], [3, "Vypni"], [2, "Zapni"]]
          .map(([c, l]) => `<td><button class="chip ${cmd === c ? "on" : ""}" data-t="${t.uid}" data-l="${L}" data-c="${c}" ${dis}>${l}</button></td>`)
          .join("");
        h += t.dimmer
          ? `<td class="dim"><button class="chip sm ${cmd === 4 ? "on" : ""}" data-t="${t.uid}" data-l="${L}" data-c="4" ${dis}>Jas</button><button class="chip sm ${cmd === 5 ? "on" : ""}" data-t="${t.uid}" data-l="${L}" data-c="5" ${dis}>+</button>${cmd >= 4 ? `<input class="pct" data-t="${t.uid}" data-l="${L}" data-c="${cmd}" type="number" min="0" max="100" value="${a.val}" ${dis}>%` : ""}</td>`
          : "<td></td>";
        return h;
      };
      right = `<div class="card">
        <div class="card-header">${icon("mdi:gesture-tap-button")}<div style="display:flex;flex-direction:column">${esc(this._groupName(sw.group))} · ${esc(sw.name)}<span class="sub">${esc(keyName)}</span></div></div>
        ${this._alerts(false)}
        <div class="counters"><span class="${sN >= 4 ? "full" : ""}">Krátký stisk <b>${sN}/4</b></span><span class="${lN >= 4 ? "full" : ""}">Dlouhý stisk <b>${lN}/4</b></span></div>
        <div class="filters">
          <div class="seg">${[["room", "Místnost"], ["all", "Vše"], ["sel", "Vybrané"]].map(([m, l]) => `<button data-mode="${m}" class="${this._mode === m ? "on" : ""}">${l}</button>`).join("")}</div>
          ${this._mode === "room" ? `<select id="otherroom">${this._roomOptions(info.groups.filter((g) => info.targets.some((t) => t.group === g.id)), targetRoom)}</select>` : ""}
        </div>
        <div class="scroll"><table>
          <tr><th class="left"></th><th class="grp" colspan="4">Krátký stisk</th><th class="grp" colspan="4">Dlouhý stisk</th></tr>
          ${targets.map((t) => `<tr><td class="left">${esc(t.sub)} · ${esc(t.name)}${this._mode !== "room" ? `<span class="secondary">${esc(this._groupName(t.group))}</span>` : ""}</td>${cell(t, false)}${cell(t, true)}</tr>`).join("") || `<tr><td class="left" colspan="9">Žádné cíle.</td></tr>`}
        </table></div>
        <div class="note">Klik akci zapne nebo vypne a hned ji zapíše do PLC. U stmívače „Jas“ nastaví jas na %, „+“ přidá %. Víc akcí „Přepni“ na jednom stisku = skupina: svítí-li něco, vše zhasne, jinak se vše rozsvítí. Tlačítka fungují podle této konfigurace i bez Home Assistant.</div>
      </div>`;
    }
    return `<div class="content three ${this._narrow ? "narrow" : ""}"><div class="col">${roomCard}</div><div class="col">${swCard}</div><div class="col">${right}</div></div>`;
  }

  _tabSet(ready) {
    const info = this._info;
    // okruhy topení a výstupy řízené PLC (doběh čerpadla) mají nastavení v záložce Technologie
    const tout = (info.tech || {}).outputs || {};
    const circ = new Set([...((info.tech || {}).circuits || []), ...Object.values(tout).flat()].map((c) => c.uid));
    const params = (info.params || []).filter((p) => !p.tech && !circ.has(p.target));  // ty jsou v záložce Technologie
    const objByUid = {};
    for (const t of info.targets) if (t.obj === t.uid) objByUid[t.uid] = t;
    // parametry podle objektu; bez objektu (např. signalizace na vypínači) zvlášť
    const rows = {};
    const loose = [];
    for (const p of params) {
      const t = objByUid[p.target];
      if (t) (rows[t.uid] ||= { t, ps: [] }).ps.push(p);
      else loose.push(p);
    }
    const meters = info.meters || [];
    const cnt = {};
    const add = (g) => (cnt[g] = (cnt[g] || 0) + 1);
    Object.values(rows).forEach((r) => add(r.t.group));
    loose.forEach((p) => add(p.group));
    info.temps.forEach((t) => add(t.group));
    meters.forEach((m) => add(m.group));
    const rooms = this._sortRooms(info.groups.filter((g) => cnt[g.id]));
    if (this._setRoom === null || !cnt[this._setRoom]) this._setRoom = rooms.length ? rooms[0].id : null;
    const dis = ready ? "" : "disabled";
    const label = (p, t) => {
      const n = t && p.name.startsWith(t.name + " ") ? p.name.slice(t.name.length + 1) : p.name;
      return n.charAt(0).toUpperCase() + n.slice(1);
    };
    const field = (p, t) => {
      if (p.bool) {
        const on = this._cfg && this._paramValue(p) !== 0;
        return `<label class="pf"><input type="checkbox" data-parb="${p.p}" ${on ? "checked" : ""} ${dis}> ${esc(label(p, t))}</label>`;
      }
      return `<label class="pf"><span>${esc(label(p, t))}</span><input class="num" data-par="${p.p}" type="number" step="${1 / 10 ** p.dec}"
        min="${p.min / 10 ** p.dec}" max="${p.max / 10 ** p.dec}" value="${this._cfg ? this._paramValue(p) : ""}" ${dis}><span class="unit">${esc(p.unit)}</span></label>`;
    };
    const mine = Object.values(rows).filter((r) => r.t.group === this._setRoom);
    const objRows = mine
      .map((r) => `<tr><td class="left">${esc(r.t.sub)} · ${esc(r.t.name)}</td><td class="pfs">${r.ps.map((p) => field(p, r.t)).join("")}</td></tr>`)
      .join("");
    const looseRows = loose
      .filter((p) => p.group === this._setRoom)
      .map((p) => `<tr><td class="left" colspan="2">${field(p, null)}</td></tr>`)
      .join("");
    const temps = info.temps.filter((t) => t.group === this._setRoom);
    const f = (v) => (v === null || v === undefined || v <= -999 ? "–" : `${(v / 10).toFixed(1)} °C`);
    const trows = temps
      .map((t) => {
        const tv = (this._cfg && this._cfg.temps[String(t.idx)]) || {};
        const c = this._corrRaw(t.idx) / 10;
        const pend = this._corrDraft && this._corrDraft[t.idx] !== undefined;
        const res = pend && tv.raw !== null && tv.raw !== undefined ? tv.raw + this._corrDraft[t.idx] : tv.cor;
        return `<tr><td class="left">${esc(t.name)}<span class="secondary">naměřeno ${f(tv.raw)}</span></td>
          <td><span class="corr"><button class="mini" data-corr="${t.idx}" data-d="-1" ${dis}>−</button><span style="${pend ? "color:var(--primary-color)" : ""}" title="${pend ? "zapíše se za 3 s" : ""}">${c > 0 ? "+" : ""}${c.toFixed(1)}</span><button class="mini" data-corr="${t.idx}" data-d="1" ${dis}>+</button></span></td>
          <td class="bigtd" style="${pend ? "opacity:.6" : ""}">${f(res)}</td></tr>`;
      })
      .join("");
    const mrows = meters
      .filter((m) => m.group === this._setRoom)
      .map((m) => {
        const v = this._cfg && this._cfg.meters ? this._cfg.meters[String(m.i)] : null;
        const cur = v === null || v === undefined ? "–" : (v / 10 ** m.dec).toFixed(m.dec);
        return `<tr><td class="left">${esc(m.name)}<span class="secondary">teď ${cur} ${esc(m.unit || "m³")}</span></td>
          <td><input class="num wide" id="meter-${m.i}" type="number" step="${1 / 10 ** m.dec}" value="${v === null || v === undefined ? "" : cur}" ${dis}> ${esc(m.unit || "m³")}</td>
          <td><button class="btn outlined" data-meter="${m.i}" ${dis}>Nastavit</button></td></tr>`;
      })
      .join("");
    const roomCard = `<div class="card"><div class="card-header">${icon("mdi:floor-plan")}Místnosti</div>
      ${this._roomItems(rooms, this._setRoom, cnt, "data-setroom")}
      <div style="height:8px"></div></div>`;
    let main = `<div class="card"><div class="card-header">${icon("mdi:tune-variant")}${esc(this._groupName(this._setRoom))}</div>${this._alerts(false)}`;
    if (objRows || looseRows)
      main += `<div class="scroll"><table>${objRows}${looseRows}</table></div>
        <div class="note">Hodnota se zapíše do PLC po opuštění pole. Max. doba 0 = bez omezení. Náběh = rozsvícení stmívače z 0 na 100 %. Žaluzie: doby jízdy a náklonu lamel změřte stopkami.</div>`;
    main += `</div>`;
    if (trows)
      main += `<div class="card"><div class="card-header">${icon("mdi:thermometer")}Teploty</div>
        <div class="scroll"><table><tr><th class="left"></th><th>Korekce</th><th>Výsledek</th></tr>${trows}</table></div></div>`;
    if (mrows)
      main += `<div class="card"><div class="card-header">${icon("mdi:counter")}Měřidla</div>
        <div class="scroll"><table>${mrows}</table></div>
        <div class="note">Stav nastavte podle fyzického měřidla (nebo podle čítače v původním programu CP-2000). Dál ho PLC počítá samo i bez Home Assistant.</div></div>`;
    return `<div class="content ${this._narrow ? "narrow" : ""}"><div class="col">${roomCard}</div><div class="col">${main}</div></div>`;
  }

  _tabList() {
    const t = [["ctl", "Ovladače"], ["set", "Nastavení"], ["auto", "Automatiky"]];
    const tech = (this._info && this._info.tech) || {};
    if ((this._info.params || []).some((p) => p.tech) || (tech.circuits || []).length || Object.keys(tech.values || {}).length)
      t.push(["tech", "Technologie"]);
    t.push(["ver", "Zálohy"]);
    return t;
  }

  // ---------------------------------------------------------------- technologie (topení, teplá voda, bazén)
  _startLive() {
    if (this._liveTimer) return;
    const tick = async () => {
      try {
        this._live = await this._ws("live");
      } catch (e) {
        return;
      }
      // nepřekreslovat, když uživatel zrovna něco vyplňuje
      const a = this.shadowRoot.activeElement;
      if (this._tab === "tech" && !this._busy && !this._dialog && !(a && /INPUT|SELECT/.test(a.tagName))) this._render();
    };
    this._liveTimer = setInterval(tick, 5000);
  }
  _stopLive() {
    if (this._liveTimer) clearInterval(this._liveTimer);
    this._liveTimer = null;
  }
  async _press(addr, label) {
    await this._run("Odesílám povel…", async () => {
      await this._ws("press", { addr });
      this._msg = `${label}: odesláno do PLC`;
    });
  }

  _otHtml(tech, lv, tp, field, row) {
    // kotel přes OpenTherm (UC-1204): ekviterm a data kotle (UID 7060.. z generátoru)
    if (!tp("heat", 9)) return "";
    const ex = tech.extra || {};
    const num = (uid) => {
      const o = ex[uid];
      const v = o ? lv(o.addr) : null;
      return v === null || v === undefined ? "–" : `${(v / 10 ** (o.dec || 0)).toFixed(o.dec || 0)}${o.unit ? " " + (o.unit === "C" ? "°C" : o.unit) : ""}`;
    };
    const bit = (uid, on, off) => {
      const o = ex[uid];
      const v = o ? lv(o.addr) : null;
      return o ? `<div class="tchip"><span>${esc(o.name)}</span><b><span class="dot ${v ? "on" : ""}"></span>${v === null || v === undefined ? "–" : v ? on : off}</b></div>` : "";
    };
    const chip = (uid, suffix = "") =>
      ex[uid] ? `<div class="tchip"><span>${esc(ex[uid].name)}</span><b>${num(uid)}${num(uid) !== "–" ? suffix : ""}</b></div>` : "";
    return `<div class="trow"><span><b>Kotel (OpenTherm)</b></span><span></span></div>
      ${row("Teplota vody při +10 °C / −15 °C venku", field(tp("heat", 9)) + field(tp("heat", 10)))}
      ${row("Teplota vody min. / max.", field(tp("heat", 11)) + field(tp("heat", 12)))}
      ${row("Ručně (0 = ekviterm)", field(tp("heat", 13)))}
      <div class="tchips">${chip(7060)}${chip(7061)}${chip(7063)}</div>
      <div class="tchips">${chip(7067)}${chip(7065)}${chip(7066, " h")}</div>
      <div class="tchips">${bit(7070, "připojeno", "odpojeno")}${bit(7071, "hoří", "nehoří")}${bit(7072, "topí", "ne")}${bit(7073, "ohřívá", "ne")}${bit(7074, "porucha", "OK")}${ex[7074] && lv(ex[7074].addr) ? chip(7064) : ""}</div>
      <div class="note">PLC posílá kotli povolení topení (podle okruhů jako dřív relé) a teplotu vody z ekvitermu: přímka mezi +10 °C a −15 °C venku, omezená min. a max. (min. 45 °C kvůli podlahovce). Ruční hodnota nad 0 ekviterm přebije.
        Starty a hodiny hoření počítá PLC z plamene (kotel je neposílá); hodně startů za den = kotel cykluje, pomůže delší min. pauza.</div>`;
  }

  _tabTech(ready) {
    const info = this._info;
    const tech = info.tech || {};
    const live = this._live || (this._cfg && this._cfg.live) || {};
    const dis = ready ? "" : "disabled";
    const tp = (sec, n) => (info.params || []).find((p) => p.tech === sec && p.n === n);
    const val = (p) => (p && this._cfg ? this._paramValue(p) : null);
    const lv = (addr) => (addr === undefined || addr === null ? null : live[String(addr)]);
    const temp = (t) => {
      const v = t ? lv(t.addr) : null;
      return v === null || v === undefined || v <= -999 ? "–" : `${(v / 10).toFixed(1)} °C`;
    };
    const tempOf = (uid) => (info.temps || []).find((t) => t.uid === uid);
    const hhmm = (m) => (m === null ? "" : `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
    const field = (p, label, opts = {}) => {
      if (!p) return "";
      if (p.options) {
        const v = val(p);
        if (opts.dropdown)
          return `<select data-sel="${p.p}" ${dis}>${p.options.map((o, i) => `<option value="${i}" ${v === i ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
        return `<div class="seg">${p.options.map((o, i) => `<button data-sel="${p.p}" data-v="${i}" class="${v === i ? "on" : ""}" ${dis}>${esc(o)}</button>`).join("")}</div>`;
      }
      if (p.bool)
        return `<label class="pf"><input type="checkbox" data-parb="${p.p}" ${val(p) ? "checked" : ""} ${dis}>${label ? ` ${esc(label)}` : ""}</label>`;
      if (p.time) return `<input type="time" data-part="${p.p}" value="${hhmm(val(p))}" ${dis}>`;
      return `<label class="pf">${label ? `<span>${esc(label)}</span>` : ""}<input class="num" data-par="${p.p}" type="number" step="${1 / 10 ** p.dec}"
        min="${p.min / 10 ** p.dec}" max="${p.max / 10 ** p.dec}" value="${val(p) ?? ""}" ${dis}><span class="unit">${esc(p.unit)}</span></label>`;
    };
    const row = (label, html) => (html ? `<div class="trow"><span>${esc(label)}</span><span>${html}</span></div>` : "");
    const onOff = (o, on = "běží", off = "stojí") => {
      const v = lv(o.addr);
      return `<div class="tchip"><span>${esc(o.name)}</span><b><span class="dot ${v ? "on" : ""}"></span>${v === null || v === undefined ? "–" : v ? on : off}</b></div>`;
    };
    const state = (uid) => {
      const s = (tech.states || {})[uid];
      const v = s ? lv(s.addr) : null;
      return s && v !== null && v !== undefined ? s.options[v] || "" : "";
    };
    const outs = tech.outputs || {};
    const T = tech.temps || {};
    const C = {};

    // topení
    if (tp("heat", 0)) {
      const st = state(7000);
      const cls = st === "Řídí HA" ? "on" : st === "Záloha PLC" ? "warn" : "";
      const chips = [...(outs.kotel || []), ...(outs.heads || []), ...(outs.pump || [])].map((o) => onOff(o)).join("");
      C.heat = (`<div class="card"><div class="card-header">${icon("mdi:radiator")}Topení<span class="badge ${cls}">${esc(st || "–")}</span></div>
        ${row("Režim", field(tp("heat", 0)))}
        ${row("Auto: topit, když je venku pod", field(tp("heat", 1)) + (T.outdoor ? `<span class="secondary">teď venku ${temp(T.outdoor)}</span>` : ""))}
        ${row("Hystereze venku", field(tp("heat", 2)))}
        ${row("Záloha PLC po výpadku HA", field(tp("heat", 3)))}
        ${row("Den od / noc od", field(tp("heat", 4)) + " " + field(tp("heat", 5)))}
        ${row("Hystereze v místnosti", field(tp("heat", 6)))}
        ${row("Kotel min. běh / pauza", field(tp("heat", 7)) + field(tp("heat", 8)))}
        ${(outs.pump || []).map((o) => row(`${o.name}: doběh čerpadla`, field((info.params || []).find((p) => p.target === o.uid && p.kind === 1)))).join("")}
        <div class="tchips">${chips}</div>
        ${this._otHtml(tech, lv, tp, field, row)}
        <div class="note">Kotel běží, když chce topit aspoň jeden okruh. S ním se zapne napájení hlavic, s podlahovkou čerpadlo.
          Čerpadlo po vypnutí okruhu ještě doběhne (rozvede teplo, necyklí). Když Home Assistant neodpovídá déle než nastavenou dobu, řídí okruhy PLC podle teplot den / noc.</div></div>`);
    }
    // teplá voda
    if (tp("tuv", 0)) {
      const ex = tech.extra || {};
      const days = ex[7011] ? lv(ex[7011].addr) : null;
      const act = ex[7012];
      const fc = tp("tuv", 5);
      const gas = (outs.tuv || []).map((o) => lv(o.addr)).some((v) => v);
      C.tuv = (`<div class="card"><div class="card-header">${icon("mdi:water-boiler")}Teplá voda<span class="badge ${gas ? "on" : ""}">${gas ? "ohřívá plyn" : "plyn neohřívá"}</span></div>
        <div class="tchips">
          ${T.tuv_top ? `<div class="tchip"><span>Bojler nahoře</span><b>${temp(T.tuv_top)}</b></div>` : ""}
          ${T.tuv_bottom ? `<div class="tchip"><span>Bojler dole</span><b>${temp(T.tuv_bottom)}</b></div>` : ""}
          ${fc ? `<div class="tchip"><span>Předpověď FVE</span><b>${val(fc) === null ? "–" : val(fc).toFixed(1) + " kWh"}</b></div>` : ""}
        </div>
        ${row("Režim plynu", field(tp("tuv", 0)))}
        ${row("Teď platí", esc(state(7010) || "–"))}
        ${row("Léto min / max", field(tp("tuv", 1)) + field(tp("tuv", 2)))}
        ${row("Zima min / max", field(tp("tuv", 3)) + field(tp("tuv", 4)))}
        ${row("Léto: předpověď stačí od", field(tp("tuv", 6)))}
        ${row("Dezinfekce", field(tp("tuv", 7)) + field(tp("tuv", 9), "každých"))}
        ${row("Splněno, když je dole", field(tp("tuv", 8)))}
        ${row("Kdy spustit", field(tp("tuv", 10), "", { dropdown: true }) + " " + field(tp("tuv", 11)))}
        ${row("Od poslední dezinfekce", (days === null || days === undefined ? "–" : `${(days / 10).toFixed(1)} dne`) +
          (act ? ` <button class="btn outlined" data-press="${act.addr}" data-label="Dezinfekce" ${dis}>${icon("mdi:play")}Dezinfikovat teď</button>` : ""))}
        <div class="note">Plyn ohřívá horní polovinu bojleru podle horního čidla. V létě jen jako záloha, když předpověď FVE (posílá Home Assistant) nestačí.
          Dezinfekce se spustí v nastavený den a čas, jen když voda dole za poslední interval nedosáhla teploty „splněno“.</div></div>`);
    }
    // okruhy
    const circuits = [...(tech.circuits || [])].sort((a, b) => this._groupName(a.group).localeCompare(this._groupName(b.group), "cs"));
    if (circuits.length) {
      const cp = (c, kind) => (info.params || []).find((p) => p.target === c.uid && p.kind === kind);
      const rows = circuits
        .map((c) => {
          const on = lv(c.addr);
          return `<tr><td class="left">${esc(this._groupName(c.group))}</td><td class="bigtd">${temp(tempOf(c.temp))}</td>
            <td>${field(cp(c, 1))}</td><td>${field(cp(c, 2))}</td><td>${field(cp(c, 3))}</td>
            <td><span class="dot ${on ? "on" : ""}"></span>${on === null || on === undefined ? "–" : on ? "topí" : "netopí"}</td></tr>`;
        })
        .join("");
      const backup = state(7000) === "Záloha PLC";
      C.zones = (`<div class="card wide"><div class="card-header">${icon("mdi:home-thermometer")}Okruhy
          <span class="badge ${backup ? "warn" : ""}">${backup ? "řídí záloha PLC" : "řídí Home Assistant (VTherm), PLC jako záloha"}</span></div>
        <div class="scroll"><table><tr><th class="left">Místnost</th><th>Teplota</th><th>Den</th><th>Noc</th><th>V záloze</th><th>Okruh</th></tr>${rows}</table></div>
        <div class="note">Teploty den / noc platí jen pro zálohu v PLC. Běžně topí podle VTherm v Home Assistant (plány, okna, nepřítomnost).</div></div>`);
    }
    // bazén
    if (tp("pool", 0)) {
      const chips = [...(outs.pool_filter || []), ...(outs.pool_heat || [])].map((o) => onOff(o)).join("");
      C.pool = (`<div class="card"><div class="card-header">${icon("mdi:pool")}Bazén</div>
        <div class="tchips">${T.pool ? `<div class="tchip"><span>Voda</span><b>${temp(T.pool)}</b></div>` : ""}${chips}</div>
        ${row("Filtrace", field(tp("pool", 0)))}
        ${row("Auto: od / do", field(tp("pool", 1)) + " " + field(tp("pool", 2)))}
        ${row("Ohřev tepelným čerpadlem", field(tp("pool", 3), "zapnuto"))}
        ${row("Ohřev min / max", field(tp("pool", 4)) + field(tp("pool", 5)))}
        <div class="note">Tepelné čerpadlo běží jen při běžící filtraci.</div></div>`);
    }
    // FVE: bojler z přebytků, omezení dodávky, elektroměr
    const V = tech.values || {};
    const vv = (role) => {
      const x = V[role];
      const v = x ? lv(x.addr) : null;
      return v === null || v === undefined ? null : v / 10 ** x.dec;
    };
    const fmt = (role, d = 0, unit = "") => {
      const v = vv(role);
      return v === null ? "–" : `${v.toFixed(d)}${unit ? " " + unit : ""}`;
    };
    const watts = (v) => (v === null ? "–" : `<span style="color:${v <= 0 ? "var(--success-color, #43a047)" : "var(--error-color)"}">${v > 0 ? "+" : ""}${Math.round(v)} W</span>`);
    if (tp("fve", 0)) {
      const st = state(7030);
      const cls = st === "Topí" ? "on" : /Chyba/.test(st) ? "warn" : "";
      const rows = [1, 2, 3]
        .map((ph) => {
          const d = vv(`ssr${ph}`);
          // průměr za 10 s ze sald po 1 s (jako elektroměr distributora); okamžitá hodnota EM03 jen bez průměru
          const g = V[`gavg${ph}`] ? vv(`gavg${ph}`) : vv(`grid${ph}`);
          return `<tr><td class="left">L${ph}</td><td>${watts(g)}</td><td>${V[`bpw${ph}`] ? fmt(`bpw${ph}`, 0, "W") : ""}</td>
            <td style="text-align:left"><span style="display:inline-block;width:110px;height:8px;border-radius:4px;background:var(--secondary-background-color);vertical-align:middle;margin-right:8px;overflow:hidden">
            <span style="display:block;height:100%;width:${d || 0}%;background:var(--primary-color)"></span></span>${d === null ? "–" : d + " %"}</td></tr>`;
        })
        .join("");
      C.fve = (`<div class="card"><div class="card-header">${icon("mdi:solar-power-variant")}Bojler z přebytků FVE<span class="badge ${cls}">${esc(st || "–")}</span></div>
        <div class="tchips">
          ${T.tuv_bottom ? `<div class="tchip"><span>Bojler dole</span><b>${temp(T.tuv_bottom)}</b></div>` : ""}
          ${T.tuv_top ? `<div class="tchip"><span>Bojler nahoře</span><b>${temp(T.tuv_top)}</b></div>` : ""}
          ${V.soc ? `<div class="tchip"><span>Baterie</span><b>${fmt("soc", 0, "%")}</b></div>` : ""}
          ${V.pv ? `<div class="tchip"><span>Výkon panelů</span><b>${vv("pv") === null ? "–" : (vv("pv") / 1000).toFixed(2) + " kW"}</b></div>` : ""}
        </div>
        <div class="scroll"><table><tr><th class="left">Fáze</th><th>Síť (průměr, + odběr)</th><th>Do bojleru</th><th>SSR výkon</th></tr>${rows}
          ${V.gavg ? `<tr><td class="left">Celkem</td><td>${watts(vv("gavg"))}</td><td>${fmt("bpw", 0, "W")}</td><td></td></tr>` : ""}</table></div>
        ${row("Ohřev z FVE", field(tp("fve", 0), "zapnuto"))}
        ${row("Cílový přetok na fázi", field(tp("fve", 1)))}
        ${row("Max. teplota dole / hystereze", field(tp("fve", 2)) + field(tp("fve", 3)))}
        ${row("Průměrování měření", field(tp("fve", 4)))}
        ${row("Regulátor Ki / Kp", field(tp("fve", 9)) + field(tp("fve", 10)))}
        ${row("Výkon tělesa na fázi", field(tp("fve", 11)))}
        ${row("Ruční test", field(tp("fve", 5), "zapnuto") + field(tp("fve", 6), "L1") + field(tp("fve", 7), "L2") + field(tp("fve", 8), "L3"))}
        <div class="note">Síť = průměr za 10 s ze sald po 1 s (jako elektroměr distributora), do bojleru = odhad z výkonu SSR. PI regulátor na každé fázi drží malý přetok do sítě (fakturace je po fázích). Výkon z elektroměru EM03 se průměruje přes celé periody PWM
          (průměrování = počet sekund, PWM má periodu 1 s). Když se měření 30 s nemění (výpadek CIB) nebo vypadne čidlo dole, SSR se vypnou.
          Ruční test nastaví pevný výkon SSR pro porovnání měření se Shelly (max. teplota platí i v testu).
          Ki = jak rychle se výkon SSR posouvá k cíli (vyšší = rychlejší, ale může kmitat; když kmitá, snižte), Kp = okamžitá reakce na změnu přetoku.</div></div>`);
    }
    if (tp("export", 0)) {
      const age = vv("inv_age");
      const ok = age !== null && age < 30;
      C.exp = (`<div class="card"><div class="card-header">${icon("mdi:transmission-tower-export")}Omezení dodávky do sítě
          <span class="badge ${ok ? "on" : "warn"}">${ok ? "střídač · limit " + fmt("explim", 1, "%") : "střídač neodpovídá"}</span></div>
        ${row("Řízení omezení z PLC", field(tp("export", 0), "zapnuto"))}
        ${row("Režim", field(tp("export", 6)))}
        ${row("Režim Baterie: plný export od", field(tp("export", 1)))}
        ${row("Omezený export", field(tp("export", 2)))}
        ${row("Pojistka v 15min intervalu", field(tp("export", 3)))}
        ${row("Pojistka 2 (limit distributora)", field(tp("export", 4)) + field(tp("export", 5), "export"))}
        ${row("Dodáno v tomto intervalu", fmt("exp15", 2, "kWh"))}
        ${row("Zápis do střídače nejdříve po", field(tp("export", 7)))}
        ${V.inv_writes ? row("Zápisů do střídače celkem", fmt("inv_writes", 0)) : ""}
        <div class="note">Režim Bojler: 100 %, dokud bojler bere přebytky; ohřátý bojler nebo vypnutý ohřev z FVE → omezený export (strop ~6 kW, slabší slunce neomezí).
          Jen pojistky: vždy 100 %. Baterie: pod hranicí SOC omezený export (hystereze 2 %). Když se v 15min intervalu (podle EM03) dodá víc než pojistka, omezený export do konce intervalu;
          nad pojistkou 2 (6,16 kW × 15 min ≈ 1,54 kWh) export podle pojistky 2 (výchozí 0 %) do konce intervalu.
          Do střídače se zapisuje jen při změně. Zapněte až po vypnutí automatizace exportu v Home Assistant, jinak by se přetahovaly.</div></div>`);
    }
    if (V.e_imp || V.e_exp) {
      C.em = (`<div class="card"><div class="card-header">${icon("mdi:meter-electric")}Elektroměr EM03</div>
        <div class="scroll"><table><tr><th class="left"></th><th>Celkem</th><th>Dnes</th></tr>
          <tr><td class="left">Odběr</td><td>${fmt("e_imp", 1, "kWh")}</td><td>${fmt("e_imp_day", 2, "kWh")}</td></tr>
          <tr><td class="left">Dodávka</td><td>${fmt("e_exp", 1, "kWh")}</td><td>${fmt("e_exp_day", 2, "kWh")}</td></tr></table></div>
        <div class="note">PLC počítá energii z výkonu fází po fázích jako elektroměr distributora. Stav celkem jde nastavit v záložce Nastavení (Měřidla).</div></div>`);
    }
    // pevné rozložení: Topení | Teplá voda, Okruhy přes celou šířku, Bazén + Bojler | Omezení + Elektroměr
    const cols = (l, r) => (l.length || r.length ? `<div class="tcols"><div class="tcol">${l.join("")}</div><div class="tcol">${r.join("")}</div></div>` : "");
    const has = (...k) => k.map((x) => C[x]).filter(Boolean);
    return `${this._alerts(false)}<div class="tech ${this._narrow ? "narrow" : ""}">
      ${cols(has("heat"), has("tuv"))}${C.zones || ""}${cols(has("pool", "fve"), has("exp", "em"))}</div>`;
  }

  async _setMeter(m, input) {
    const v = parseFloat(String(input).replace(",", "."));
    if (isNaN(v) || v < 0) return;
    const raw = Math.round(v * 10 ** m.dec);
    await this._run("Nastavuji stav měřidla…", async () => {
      await this._ws("config/set", { pairs: [[9000 + 2 * m.i, raw % 65536], [9001 + 2 * m.i, Math.floor(raw / 65536)]] });
      this._cfg = await this._ws("config/get");
      this._msg = `${m.name}: stav zapsán do PLC`;
    });
  }

  // ---------------------------------------------------------------- automatiky
  _autoCfg(a) {
    if (this._autoDraft && this._autoDraft.a === a) return this._autoDraft.c;
    const m = (this._cfg && this._cfg.map) || {};
    const c = [];
    for (let r = 0; r < 20; r++) c.push(Number(m[String(4000 + a * 20 + r)] ?? 0));
    return c;
  }
  _autoEdit(a, r, v) {
    if (!this._autoDraft || this._autoDraft.a !== a) this._autoDraft = { a, c: this._autoCfg(a).slice() };
    this._autoDraft.c[r] = v;
    this._render();
  }
  async _autoSave(a) {
    if (!this._autoDraft || this._autoDraft.a !== a) return;
    const pairs = this._autoDraft.c.map((v, r) => [4000 + a * 20 + r, v & 0xffff]);
    await this._run("Zapisuji automatiku…", async () => {
      await this._ws("config/set", { pairs });
      this._cfg = await this._ws("config/get");
      this._autoDraft = null;
      this._msg = "Automatika zapsána do PLC";
    });
  }
  _tabAuto(ready) {
    const info = this._info;
    const autos = info.autos || [];
    if (!autos.length)
      return `<div class="vers"><div class="card"><div class="card-header">${icon("mdi:motion-sensor")}Automatiky</div><div class="empty">PLC nemá žádné automatiky (list Automatiky v xlsx).</div></div></div>`;
    if (this._auto === null || this._auto >= autos.length) this._auto = 0;
    const a = this._auto;
    const c = this._autoCfg(a);
    const dis = ready ? "" : "disabled";
    const hm = (m) => (m === 0xffff ? "" : `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`);
    const outT = info.targets.find((t) => t.uid === c[16]);
    const sensorSel = (r) =>
      `<select data-ar="${r}" ${dis}><option value="0">— nic —</option>${info.sensors
        .map((x) => `<option value="${x.uid}" ${x.uid === c[r] ? "selected" : ""}>${esc(this._groupName(x.group))} · ${esc(x.name)}</option>`)
        .join("")}</select>`;
    const outSel = `<select data-ar="16" ${dis}><option value="0">— nic —</option>${info.targets
      .filter((t) => t.kind === "output" || t.kind === "dimmer")
      .map((t) => `<option value="${t.uid}" ${t.uid === c[16] ? "selected" : ""}>${esc(this._groupName(t.group))} · ${esc(t.sub)} · ${esc(t.name)}</option>`)
      .join("")}</select>`;
    const list = autos
      .map((x) => {
        const on = this._autoCfg(x.a)[0];
        return `<div class="item ${x.a === a ? "sel" : ""}" data-auto="${x.a}">${icon(on ? "mdi:motion-sensor" : "mdi:motion-sensor-off")}<div class="text"><span class="name">${esc(x.name)}</span><span class="secondary">${on ? "aktivní" : "vypnutá"}</span></div></div>`;
      })
      .join("");
    const wins = [0, 1, 2, 3]
      .map((i) => `<div class="win">od <input type="time" data-aw="${8 + 2 * i}" value="${hm(c[8 + 2 * i])}" ${dis}> do <input type="time" data-aw="${9 + 2 * i}" value="${hm(c[9 + 2 * i])}" ${dis}></div>`)
      .join("");
    const dirty = this._autoDraft && this._autoDraft.a === a;
    const lux = this._cfg ? this._cfg.lux : null;
    const form = `<div class="card">
      <div class="card-header">${icon("mdi:motion-sensor")}${esc(autos[a].name)}</div>
      ${this._alerts(false)}
      <div class="form">
        <label class="row"><span>Aktivní</span><input type="checkbox" data-ab="0" ${c[0] ? "checked" : ""} ${dis}></label>
        <div class="row"><span>Čidla</span><div class="col2">${[1, 2, 3, 4].map(sensorSel).join("")}</div></div>
        <label class="row"><span>Spouští</span><select data-ar="5" ${dis}><option value="0" ${c[5] ? "" : "selected"}>sepnutí (pohyb)</option><option value="1" ${c[5] ? "selected" : ""}>rozepnutí (otevření dveří)</option></select></label>
        <label class="row"><span>Doba svícení</span><span><input class="num" data-am="6" type="number" min="0" max="999" value="${Math.floor(c[6] / 60)}" ${dis}> min <input class="num" data-as="6" type="number" min="0" max="59" value="${c[6] % 60}" ${dis}> s</span></label>
        <label class="row"><span>Soumrak</span><span><input class="num" data-ar="7" type="number" min="0" max="65000" value="${c[7]}" ${dis}> lx <small class="secondary">(0 = vždy${lux !== null && lux !== undefined ? `, teď ${lux} lx` : ""})</small></span></label>
        <div class="row"><span>Časová okna</span><div class="col2">${wins}<small class="secondary">prázdné = kdykoli</small></div></div>
        <label class="row"><span>Výstup</span>${outSel}</label>
        ${outT && outT.dimmer ? `<label class="row"><span>Jas</span><span><input class="num" data-ar="17" type="number" min="0" max="100" value="${c[17]}" ${dis}> % <small class="secondary">(0 = maximum)</small></span></label>` : ""}
      </div>
      <div class="card-actions">
        <button class="btn" id="autocancel" ${dirty && ready ? "" : "disabled"}>Zrušit změny</button>
        <button class="btn filled" id="autosave" ${dirty && ready ? "" : "disabled"}>${icon("mdi:content-save")}Zapsat do PLC</button>
      </div>
      <div class="note">Automatika rozsvítí výstup, když čidlo sepne (nebo rozepne) a je splněný soumrak i časové okno. Zhasne po uplynutí doby od posledního spuštění. Běží v PLC i bez Home Assistant.</div>
    </div>`;
    return `<div class="content ${this._narrow ? "narrow" : ""}"><div class="col"><div class="card"><div class="card-header">${icon("mdi:robot")}Automatiky</div>${list}<div style="height:8px"></div></div></div><div class="col">${form}</div></div>`;
  }

  _tabVer(ready) {
    const base = this._version(this._base);
    const vers = this._versions.length
      ? this._versions
          .map((v) => `
        <div class="ver ${this._base === v.id ? "cur" : ""}">
          ${icon(v.source === "import" ? "mdi:file-import" : "mdi:history")}
          <div class="text"><span>${esc(v.name)}</span>
            <span class="secondary">${new Date(v.ts).toLocaleString("cs-CZ")}${v.source === "import" ? " · import" : ""}${(v.protocol || 1) !== this._info.protocol ? " · jiný formát programu" : ""}</span></div>
          <button class="btn" data-restore="${v.id}" ${ready && (v.protocol || 1) === this._info.protocol ? "" : "disabled"}>${icon("mdi:restore")}Obnovit do PLC</button>
          <button class="btn" data-exportver="${v.id}">${icon("mdi:download")}Export</button>
          <button class="iconbtn" style="color:var(--secondary-text-color)" data-del="${v.id}" title="Smazat" ${this._busy ? "disabled" : ""}>${icon("mdi:delete")}</button>
        </div>`)
          .join("")
      : `<div class="empty">Zatím žádná uložená verze.</div>`;
    return `<div class="vers">
      <div class="card">
        <div class="card-header">${icon("mdi:memory")}<div style="display:flex;flex-direction:column">Aktuální konfigurace v PLC<span class="sub">akce tlačítek, nastavení a korekce teplot</span></div></div>
        ${this._alerts()}
        <div class="card-actions">
          <button class="btn" id="importbtn" ${this._busy ? "disabled" : ""}>${icon("mdi:upload")}Import ze souboru</button>
          <button class="btn" id="exportcur" ${ready ? "" : "disabled"}>${icon("mdi:download")}Export aktuální</button>
          <button class="btn filled" id="savever" ${ready ? "" : "disabled"}>${icon("mdi:content-save")}Uložit jako novou verzi</button>
          <input id="importfile" type="file" accept=".json,application/json" style="display:none">
        </div>
      </div>
      <div class="card">
        <div class="card-header">${icon("mdi:history")}<div style="display:flex;flex-direction:column">Uložené verze<span class="sub">společné pro všechny uživatele, součást záloh Home Assistant</span></div></div>
        ${vers}
        <div class="note">Obnovení zapíše verzi do PLC. Import uloží soubor jako novou verzi, do PLC se zapíše až tlačítkem Obnovit.${base ? "" : ""}</div>
      </div>
      ${this._staleCard()}</div>`;
  }

  _staleCard() {
    const st = this._stale;
    if (!st) return "";
    const n = st.entities.length + st.devices.length;
    const list = [
      ...st.devices.map((d) => `<div class="stale">${icon("mdi:devices")} zařízení ${esc(d.name)}</div>`),
      ...st.entities.map((e) => `<div class="stale">${esc(e.name || e.entity_id)} <code>${esc(e.entity_id)}</code></div>`),
    ].join("");
    return `<div class="card">
      <div class="card-header">${icon("mdi:broom")}<div style="display:flex;flex-direction:column">Neplatné entity<span class="sub">${n ? `${n} z předchozích verzí programu` : "žádné, vše odpovídá programu v PLC"}</span></div></div>
      ${list}
      ${n ? `<div class="note">Tyto entity a zařízení integrace vytvořila pro dřívější program PLC a aktuální program je už nemá. Jsou nedostupné.
        Před odstraněním zkontrolujte, že je nepoužívá dashboard ani automatizace.</div>
        <div class="card-actions"><button class="btn danger" id="staleremove" ${this._busy ? "disabled" : ""}>${icon("mdi:delete-sweep")}Odstranit (${n})</button></div>` : ""}
    </div>`;
  }
  async _loadStale() {
    try {
      this._stale = await this._ws("stale");
    } catch (e) {
      this._stale = null;
    }
    if (this._tab === "ver") this._render();
  }
  async _removeStale() {
    const n = this._stale ? this._stale.entities.length + this._stale.devices.length : 0;
    const ok = await this._ask({ title: "Odstranit neplatné entity?", text: `Odstraní se ${n} položek z registru Home Assistant. Nelze vrátit.`, ok: "Odstranit", danger: true });
    if (!ok) return;
    await this._run("Odstraňuji neplatné entity…", async () => {
      const r = await this._ws("stale/remove");
      this._msg = `Odstraněno: ${r.entities} entit, ${r.devices} zařízení`;
      this._stale = await this._ws("stale");
    });
  }

  _statusIcons() {
    if (!this._cfg || this._busy) return "";
    const ok = this._cfg.checksum_plc === this._cfg.checksum_calc;
    const base = this._version(this._base);
    const d = base ? this._diff(base) : null;
    const plc = ok
      ? `<span class="st ok" title="Zobrazená konfigurace odpovídá PLC">${icon("mdi:check-circle")}</span>`
      : `<span class="st bad" title="Kontrolní součet nesedí, načtěte znovu z PLC">${icon("mdi:alert")}</span>`;
    const ver = !base
      ? `<span class="st warn" title="Zatím žádná uložená verze">${icon("mdi:content-save-off")}</span>`
      : d
        ? `<span class="st warn" title="Neuloženo: ${zmen(d)} oproti verzi „${esc(base.name)}“">${icon("mdi:content-save-alert")}<small>${d}</small></span>`
        : `<span class="st ok" title="Odpovídá verzi „${esc(base.name)}“">${icon("mdi:content-save-check")}</span>`;
    return `<div class="status" data-tab="ver">${plc}${ver}</div>`;
  }

  _renderV2() {
    const info = this._info;
    const ready = !!(info && this._cfg && !this._busy);
    const tab = this._tab || "ctl";
    const entrySel =
      this._entries.length > 1
        ? `<select id="entry">${this._entries.map((e) => `<option value="${e.entry_id}" ${e.entry_id === this._entry ? "selected" : ""}>${esc(e.title)}</option>`).join("")}</select>`
        : "";
    const body =
      tab === "set" ? this._tabSet(ready) : tab === "ver" ? this._tabVer(ready) : tab === "auto" ? this._tabAuto(ready)
        : tab === "tech" ? this._tabTech(ready) : this._tabCtl(ready);
    if (tab === "tech") this._startLive();
    else this._stopLive();
    if (tab === "ver" && this._stale === null) {
      this._stale = undefined;  // načítá se
      this._loadStale();
    }
    const dlg = this._dialog
      ? `<div class="backdrop" id="dlg-bg"><div class="dialog" role="dialog">
          <h2>${esc(this._dialog.title)}</h2>
          ${this._dialog.text ? `<p>${this._dialog.text}</p>` : ""}
          ${this._dialog.input !== null ? `<input id="dlg-input" type="text" value="${esc(this._dialog.input)}">` : ""}
          <div class="actions"><button class="btn" id="dlg-cancel">Zrušit</button>
            <button class="btn ${this._dialog.danger ? "danger" : "filled"}" id="dlg-ok">${esc(this._dialog.ok)}</button></div></div></div>`
      : "";
    this.shadowRoot.innerHTML = `
      <style>${STYLE}${STYLE_V2}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title2">Tecomat PLC <span style="opacity:.7;font-size:14px">${esc(info.model)} · program ${info.program}</span></div>
        <div class="tabs">${this._tabList().map(([t, l]) => `<button data-tab="${t}" class="${tab === t ? "on" : ""}">${l}</button>`).join("")}</div>
        <div style="flex:1"></div>
        ${this._statusIcons()}
        ${entrySel}
        <button class="iconbtn" id="reload" title="Načíst z PLC" ${this._busy || !this._entry ? "disabled" : ""}>${icon("mdi:refresh")}</button>
      </div>
      ${body}
      ${dlg}`;
    const root = this.shadowRoot;
    const mb = root.querySelector("ha-menu-button");
    if (mb) {
      mb.hass = this._hass;
      mb.narrow = this._narrow;
    }
    const on = (sel, fn) => root.querySelectorAll(sel).forEach((el) => el.addEventListener("click", () => fn(el)));
    on("[data-tab]", (el) => {
      this._tab = el.dataset.tab;
      this._error = "";
      this._render();
    });
    on("[data-room]", (el) => {
      this._room = Number(el.dataset.room);
      this._swKey = null;
      this._otherRoom = null;
      this._render();
    });
    on("[data-setroom]", (el) => {
      this._setRoom = Number(el.dataset.setroom);
      this._render();
    });
    on(".key", (el) => {
      this._swKey = el.dataset.sw;
      this._pos = Number(el.dataset.pos);
      this._render();
    });
    on("[data-mode]", (el) => {
      this._mode = el.dataset.mode;
      this._render();
    });
    const other = root.getElementById("otherroom");
    if (other) other.addEventListener("change", () => ((this._otherRoom = Number(other.value)), this._render()));
    const curBtn = () => {
      const sw = this._switches().find((x) => x.key === this._swKey);
      return sw ? sw.keys[this._pos] ?? sw.keys[1] : null;
    };
    on(".chip[data-t]:not([disabled])", (el) => {
      const c = Number(el.dataset.c);
      this._toggleAct(curBtn(), Number(el.dataset.t), el.dataset.l === "1", c, c === 4 ? 100 : c === 5 ? 25 : 0);
    });
    root.querySelectorAll("input.pct").forEach((el) =>
      el.addEventListener("change", () =>
        this._toggleAct(curBtn(), Number(el.dataset.t), el.dataset.l === "1", Number(el.dataset.c), Math.max(0, Math.min(100, Number(el.value) || 0)), true)
      )
    );
    on("button[data-corr]:not([disabled])", (el) => {
      const t = this._info.temps.find((x) => x.idx === Number(el.dataset.corr));
      if (t) this._stepCorr(t, Number(el.dataset.d));
    });
    root.querySelectorAll("input[data-par]").forEach((el) =>
      el.addEventListener("change", () => {
        const p = this._info.params.find((x) => x.p === Number(el.dataset.par));
        if (p) this._saveParam(p, el.value);
      })
    );
    root.querySelectorAll("input[data-parb]").forEach((el) =>
      el.addEventListener("change", () => {
        const p = this._info.params.find((x) => x.p === Number(el.dataset.parb));
        if (p) this._saveParam(p, el.checked ? 1 : 0);
      })
    );
    on(".seg button[data-sel]:not([disabled])", (el) => {
      const p = this._info.params.find((x) => x.p === Number(el.dataset.sel));
      if (p) this._saveParam(p, Number(el.dataset.v));
    });
    root.querySelectorAll("select[data-sel]").forEach((el) =>
      el.addEventListener("change", () => {
        const p = this._info.params.find((x) => x.p === Number(el.dataset.sel));
        if (p) this._saveParam(p, Number(el.value));
      })
    );
    root.querySelectorAll("input[data-part]").forEach((el) =>
      el.addEventListener("change", () => {
        const p = this._info.params.find((x) => x.p === Number(el.dataset.part));
        const m = /^(\d\d):(\d\d)/.exec(el.value);
        if (p && m) this._saveParam(p, Number(m[1]) * 60 + Number(m[2]));
      })
    );
    on("button[data-press]:not([disabled])", (el) => this._press(Number(el.dataset.press), el.dataset.label));
    on("button[data-meter]:not([disabled])", (el) => {
      const m = this._info.meters.find((x) => x.i === Number(el.dataset.meter));
      if (m) this._setMeter(m, root.getElementById(`meter-${m.i}`).value);
    });
    on("[data-auto]", (el) => {
      this._auto = Number(el.dataset.auto);
      this._autoDraft = null;
      this._render();
    });
    const A = () => this._auto;
    root.querySelectorAll("select[data-ar], input[data-ar]").forEach((el) =>
      el.addEventListener("change", () => this._autoEdit(A(), Number(el.dataset.ar), Number(el.value) || 0))
    );
    root.querySelectorAll("input[data-ab]").forEach((el) =>
      el.addEventListener("change", () => this._autoEdit(A(), Number(el.dataset.ab), el.checked ? 1 : 0))
    );
    root.querySelectorAll("input[data-am], input[data-as]").forEach((el) =>
      el.addEventListener("change", () => {
        const mi = Number(root.querySelector("input[data-am]").value) || 0;
        const se = Number(root.querySelector("input[data-as]").value) || 0;
        this._autoEdit(A(), 6, Math.max(0, mi * 60 + se));
      })
    );
    root.querySelectorAll("input[data-aw]").forEach((el) =>
      el.addEventListener("change", () => {
        const m = /^(\d\d):(\d\d)/.exec(el.value);
        this._autoEdit(A(), Number(el.dataset.aw), m ? Number(m[1]) * 60 + Number(m[2]) : 0xffff);
      })
    );
    on("#autosave", () => this._autoSave(this._auto));
    on("#autocancel", () => {
      this._autoDraft = null;
      this._render();
    });
    on("button[data-restore]:not([disabled])", (el) => this._restore(el.dataset.restore));
    on("button[data-exportver]", (el) => this._exportVersion(this._version(el.dataset.exportver)));
    on("button[data-del]", (el) => this._delete(el.dataset.del));
    on("#exportcur", () => this._exportVersion(null));
    on("#staleremove", () => this._removeStale());
    on("#savever", () => this._saveVersion());
    on("#reload", () => this._readPlc());
    const fileIn = root.getElementById("importfile");
    on("#importbtn", () => fileIn && fileIn.click());
    if (fileIn) fileIn.addEventListener("change", () => fileIn.files[0] && this._import(fileIn.files[0]));
    const es = root.getElementById("entry");
    if (es) es.addEventListener("change", () => this._selectEntry(es.value));
    if (this._dialog) {
      const input = root.getElementById("dlg-input");
      const okVal = () => (this._dialog.input !== null ? input.value : true);
      on("#dlg-ok", () => this._closeDialog(okVal()));
      on("#dlg-cancel", () => this._closeDialog(this._dialog.input !== null ? null : false));
      const bg = root.getElementById("dlg-bg");
      bg.addEventListener("click", (ev) => {
        if (ev.target === bg) this._closeDialog(this._dialog.input !== null ? null : false);
      });
      if (input)
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._closeDialog(input.value);
          if (ev.key === "Escape") this._closeDialog(null);
        });
    }
  }

  _code(c, b) {
    return (this._cfg && this._cfg.map[`${c},${b}`]) || 0;
  }
  _version(id) {
    return this._versions.find((v) => v.id === id) || null;
  }
  _diff(ver) {
    if (!ver || !this._cfg) return null;
    let n = 0;
    // předpověď FVE posílá automatizace z HA průběžně, není to nastavení
    const skip = new Set(((this._info && this._info.params) || []).filter((p) => p.tech === "tuv" && p.n === 5).map((p) => String(20000 + p.p)));
    const keys = new Set([...Object.keys(ver.map), ...Object.keys(this._cfg.map)]);
    for (const k of keys) if (!skip.has(k) && (ver.map[k] || 0) !== (this._cfg.map[k] || 0)) n++;
    const vc = ver.corr || {};
    const cc = this._cfg.corr || {};
    for (const k of new Set([...Object.keys(vc), ...Object.keys(cc)])) if ((vc[k] || 0) !== (cc[k] || 0)) n++;
    return n;
  }
  // místnosti podle podlaží v HA (úroveň, bez podlaží na konec) a uvnitř abecedně
  _sortRooms(rooms) {
    // venkovní podlaží vždy na konec (za patra), místnosti bez podlaží úplně na konec
    const out = (g) => /venk|outdoor|outside|exter/i.test(g.floor || "");
    const lvl = (g) => (!g.floor ? 9999 : out(g) ? 5000 + (g.flevel ?? 0) : g.flevel === null || g.flevel === undefined ? 900 : g.flevel);
    return [...rooms].sort((a, b) => lvl(a) - lvl(b) || (a.floor || "").localeCompare(b.floor || "", "cs") || a.name.localeCompare(b.name, "cs"));
  }
  _roomItems(rooms, sel, cnt, attr) {
    let last;
    return this._sortRooms(rooms)
      .map((r) => {
        const fi = r.ficon || (/venk|outdoor/i.test(r.floor || "") ? "mdi:tree" : r.floor ? `mdi:home-floor-${Math.max(0, Math.min(3, r.flevel ?? 0))}` : "mdi:help-circle-outline");
        const head = r.floor !== last ? `<div class="floor">${icon(fi)}${esc(r.floor || "Bez podlaží")}</div>` : "";
        last = r.floor;
        return `${head}<div class="item ${r.id === sel ? "sel" : ""}" ${attr}="${r.id}"><div class="text"><span class="name">${esc(r.name)}</span></div><span class="count">${cnt[r.id]}</span></div>`;
      })
      .join("");
  }
  _roomOptions(rooms, sel) {
    let last;
    let html = "";
    for (const g of this._sortRooms(rooms)) {
      if (g.floor !== last) html += `${last !== undefined ? "</optgroup>" : ""}<optgroup label="${esc(g.floor || "Bez podlaží")}">`;
      last = g.floor;
      html += `<option value="${g.id}" ${g.id === sel ? "selected" : ""}>${esc(g.name)}</option>`;
    }
    return html + (last !== undefined ? "</optgroup>" : "");
  }
  _groupName(id) {
    const g = this._info.groups.find((x) => x.id === id);
    return g ? g.name : `Skupina ${id}`;
  }

  // ---------------------------------------------------------------- dialogy
  _ask({ title, text = "", input = null, ok = "OK", danger = false }) {
    return new Promise((resolve) => {
      this._dialog = { title, text, input, ok, danger, resolve };
      this._render();
      const el = this.shadowRoot.getElementById("dlg-input");
      if (el) {
        el.focus();
        el.select();
      }
    });
  }
  _closeDialog(result) {
    const d = this._dialog;
    this._dialog = null;
    this._render();
    if (d) d.resolve(result);
  }

  // ---------------------------------------------------------------- akce
  async _toggleOpt(c, b, gkey, v) {
    if (!this._cfg || this._busy) return;
    const grp = GROUPS.find((x) => x.key === gkey);
    let code = this._code(c, b);
    const cur = (code >> grp.shift) & 3;
    code = (code & ~(3 << grp.shift)) | ((cur === v ? 0 : v) << grp.shift);
    this._cfg.map[`${c},${b}`] = code;
    await this._run("Zapisuji do PLC…", async () => {
      await this._ws("config/set", { pairs: [[c * this._info.max_b + b, code]] });
      this._cfg = await this._ws("config/get");
      this._msg = "Zapsáno do PLC";
    });
  }

  async _saveCorr(idx, input) {
    let v = Math.round(parseFloat(String(input).replace(",", ".")) * 10);
    if (isNaN(v)) return;
    v = Math.max(-100, Math.min(100, v));
    await this._run("Zapisuji korekci…", async () => {
      await this._ws("config/set", { pairs: [[CORR_BASE + idx, v]] });
      this._cfg = await this._ws("config/get");
      this._msg = "Korekce zapsána do PLC";
    });
  }

  async _saveVersion() {
    const def = new Date().toLocaleString("cs-CZ");
    const name = await this._ask({
      title: "Uložit verzi",
      text: "Uloží se aktuální konfigurace z PLC.",
      input: def,
      ok: "Uložit",
    });
    if (name === null) return;
    await this._run("Ukládám verzi…", async () => {
      const ver = await this._ws("versions/save", { name: name || def });
      this._versions = await this._ws("versions/list");
      this._base = ver.id;
      this._msg = `Verze „${ver.name}“ uložena`;
    });
  }

  async _restore(id) {
    const ver = this._version(id);
    if (!ver) return;
    const ok = await this._ask({
      title: "Obnovit verzi",
      text: `Konfigurace ve verzi „${esc(ver.name)}“ se zapíše do PLC. Změní se ${polozek(this._diff(ver))}.`,
      ok: "Obnovit",
    });
    if (!ok) return;
    await this._run("Obnovuji verzi do PLC…", async () => {
      await this._ws("versions/restore", { version_id: id });
      this._cfg = await this._ws("config/get");
      this._base = id;
      this._msg = `Obnovena verze „${ver.name}“`;
    });
  }

  async _delete(id) {
    const ver = this._version(id);
    if (!ver) return;
    const ok = await this._ask({ title: "Smazat verzi", text: `Smazat verzi „${esc(ver.name)}“?`, ok: "Smazat", danger: true });
    if (!ok) return;
    await this._run("Mažu verzi…", async () => {
      await this._ws("versions/delete", { version_id: id });
      this._versions = await this._ws("versions/list");
      if (this._base === id) this._base = null;
    });
  }

  _export() {
    const data = {
      type: "tecomat-plc-ovladace",
      exported: new Date().toISOString(),
      plc: this._info ? this._info.model : "",
      current: { map: this._cfg.map, corr: this._cfg.corr },
      versions: this._versions,
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    const d = new Date();
    const p = (x) => String(x).padStart(2, "0");
    a.href = URL.createObjectURL(blob);
    a.download = `tecomat-ovladace-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async _import(file) {
    await this._run("Importuji…", async () => {
      const data = JSON.parse(await file.text());
      const cur = data.current || {};
      if (!cur.map) throw new Error("Soubor neobsahuje konfiguraci");
      const map = {};
      for (const [k, v] of Object.entries(cur.map)) map[k] = Number(v);
      const corr = {};
      for (const [k, v] of Object.entries(cur.corr || {})) corr[k] = Number(v);
      await this._ws("versions/import", { name: `Import ${file.name}`, map, corr });
      this._versions = await this._ws("versions/list");
      this._msg = "Importováno jako nová verze. Do PLC se zapíše až tlačítkem Obnovit.";
    });
  }

  // ---------------------------------------------------------------- vykreslení
  _alerts(full = true) {
    const a = (type, ic, text) => `<div class="alert ${type}">${icon(ic)}<span>${text}</span></div>`;
    const out = [];
    if (this._busy) out.push(a("info", "mdi:progress-clock", esc(this._busy)));
    if (this._error) out.push(a("error", "mdi:alert-circle", esc(this._error)));
    if (!full) return out.join("");
    if (this._cfg && !this._busy) {
      if (this._cfg.checksum_plc === this._cfg.checksum_calc)
        out.push(a("success", "mdi:check-circle", "Zobrazená konfigurace odpovídá PLC"));
      else
        out.push(a("error", "mdi:alert", `Kontrolní součet nesedí (PLC ${this._cfg.checksum_plc}, načteno ${this._cfg.checksum_calc}). Načtěte znovu z PLC.`));
      const base = this._version(this._base);
      if (base) {
        const d = this._diff(base);
        out.push(
          d
            ? a("warning", "mdi:content-save-alert", `Neuloženo: ${zmen(d)} oproti verzi „${esc(base.name)}“`)
            : a("success", "mdi:content-save-check", `Odpovídá verzi „${esc(base.name)}“`)
        );
      } else out.push(a("warning", "mdi:content-save-off", "Zatím žádná uložená verze"));
    }
    if (this._msg && !this._busy) out.push(`<div class="note" style="padding-top:0">${esc(this._msg)}</div>`);
    return out.join("");
  }

  _render() {
    if (this._info && this._v2()) {
      this._renderV2();
      return;
    }
    const info = this._info;
    const ready = !!(info && this._cfg && !this._busy);
    const fmtT = (v) => (v === null || v === undefined || v <= -999 ? "–" : `${(v / 10).toFixed(1)} °C`);

    const entrySel =
      this._entries.length > 1
        ? `<select id="entry">${this._entries
            .map((e) => `<option value="${e.entry_id}" ${e.entry_id === this._entry ? "selected" : ""}>${esc(e.title)}</option>`)
            .join("")}</select>`
        : "";

    let left = "";
    let right = `<div class="card"><div class="card-header">${icon("mdi:light-switch")}Načítám…</div>${this._alerts()}</div>`;

    if (info && !this._v2()) {
      // tlačítka
      const byGroup = {};
      for (const b of this._btnList()) (byGroup[b.group] ||= []).push(b);
      const buttons = Object.entries(byGroup)
        .map(
          ([g, list]) => `
          <div class="section">${esc(this._groupName(Number(g)))}</div>
          ${list
            .map(
              (b) => `
            <div class="item ${b.m === this._sel ? "sel" : ""}" data-b="${b.m}">
              ${icon("mdi:gesture-tap-button")}
              <div class="text"><span class="name">${esc(b.name)}</span></div>
            </div>`
            )
            .join("")}`
        )
        .join("");
      left += `
        <div class="card">
          <div class="card-header">${icon("mdi:gesture-tap-button")}Tlačítka</div>
          ${buttons || `<div class="empty">PLC neobsahuje žádná tlačítka.</div>`}
          <div style="height:8px"></div>
        </div>`;

      // teploty
      if (info.temps.length) {
        const temps = info.temps
          .map((t) => {
            const tv = (this._cfg && this._cfg.temps[String(t.idx)]) || {};
            const corr = this._cfg ? (this._cfg.corr[String(t.idx)] || 0) / 10 : 0;
            return `
            <div class="temp">
              ${icon("mdi:thermometer")}
              <div class="name">${esc(t.name)} <span class="secondary" style="color:var(--secondary-text-color);font-size:12px">· ${esc(this._groupName(t.group))}</span></div>
              <div class="values">
                <div class="value"><b>${fmtT(tv.raw)}</b><small>naměřená</small></div>
                <input id="in-${t.idx}" type="number" step="0.1" min="-10" max="10" value="${corr.toFixed(1)}" ${ready ? "" : "disabled"} title="Korekce °C">
                <div class="value"><b>${fmtT(tv.cor)}</b><small>výsledná</small></div>
                <button class="btn outlined" data-corr="${t.idx}" ${ready ? "" : "disabled"}>Uložit</button>
              </div>
            </div>`;
          })
          .join("");
        left += `
          <div class="card">
            <div class="card-header">${icon("mdi:thermometer-plus")}Korekce teplot</div>
            ${temps}
          </div>`;
      }

      // matice (protokol 1) nebo akce tlačítka (protokol 2)
      const btn = this._btnList().find((b) => b.m === this._sel);
      const head = GROUPS.map((g) => `<th colspan="${g.opts.length}" class="grp">${g.title}</th>`).join("");
      const rows =
        this._cfg && btn
          ? info.circuits
              .map((c) => {
                const code = this._code(c.m, btn.m);
                const cells = GROUPS.map((g) =>
                  g.opts
                    .map(([v, label]) => {
                      const dis = !ready || (g.key === "d" && !c.dimmable);
                      const on = ((code >> g.shift) & 3) === v;
                      return `<td><button class="chip ${on ? "on" : ""}" data-c="${c.m}" data-g="${g.key}" data-v="${v}" ${dis ? "disabled" : ""}>${label}</button></td>`;
                    })
                    .join("")
                ).join("");
                return `<tr><td class="left">${esc(c.name)}<span class="secondary">${esc(this._groupName(c.group))}</span></td>${cells}</tr>`;
              })
              .join("")
          : "";
      const body = rows ? `<div class="scroll"><table><tr><th class="left">Okruh</th>${head}</tr>${rows}</table></div>` : "";
      right = `
        <div class="card">
          <div class="card-header">${icon("mdi:lightbulb-group")}
            <div style="display:flex;flex-direction:column">Osvětlení
              <span class="sub">${btn ? `${esc(this._groupName(btn.group))} · ${esc(btn.name)}` : "Vyberte tlačítko"}</span>
            </div>
          </div>
          ${this._alerts()}
          ${body}
          <div class="note">Změna se zapíše do PLC okamžitě. Konfigurace je uložená v PLC a tlačítka podle ní fungují i bez Home Assistant.</div>
        </div>`;

      // verze
      const versions = this._versions.length
        ? this._versions
            .map(
              (v) => `
          <div class="ver ${this._base === v.id ? "cur" : ""}">
            ${icon(v.source === "import" ? "mdi:file-import" : "mdi:history")}
            <div class="text"><span>${esc(v.name)}</span>
              <span class="secondary">${new Date(v.ts).toLocaleString("cs-CZ")}${v.source === "import" ? " · import" : ""}</span></div>
            <button class="btn" data-restore="${v.id}" ${ready ? "" : "disabled"}>${icon("mdi:restore")}Obnovit</button>
            <button class="iconbtn" style="color:var(--secondary-text-color)" data-del="${v.id}" title="Smazat" ${this._busy ? "disabled" : ""}>${icon("mdi:delete")}</button>
          </div>`
            )
            .join("")
        : `<div class="empty">Zatím žádná uložená verze.</div>`;
      right += `
        <div class="card">
          <div class="card-header">${icon("mdi:history")}Verze konfigurace</div>
          ${versions}
          <div class="note">Verze se ukládají ručně z aktuálního obsahu PLC a jsou společné pro všechny uživatele (součást záloh Home Assistant). Obnovení zapíše verzi do PLC.</div>
          <div class="card-actions">
            <button class="btn" id="importbtn" ${this._busy ? "disabled" : ""}>${icon("mdi:upload")}Import</button>
            <button class="btn" id="export" ${ready ? "" : "disabled"}>${icon("mdi:download")}Export</button>
            <button class="btn filled" id="savever" ${ready ? "" : "disabled"}>${icon("mdi:content-save")}Uložit verzi</button>
            <input id="importfile" type="file" accept=".json,application/json" style="display:none">
          </div>
        </div>`;
    } else if (!info && this._error) {
      right = `<div class="card"><div class="card-header">${icon("mdi:alert-circle")}Tecomat PLC</div>${this._alerts()}</div>`;
    }

    const dlg = this._dialog
      ? `<div class="backdrop" id="dlg-bg"><div class="dialog" role="dialog">
          <h2>${esc(this._dialog.title)}</h2>
          ${this._dialog.text ? `<p>${this._dialog.text}</p>` : ""}
          ${this._dialog.input !== null ? `<input id="dlg-input" type="text" value="${esc(this._dialog.input)}">` : ""}
          <div class="actions">
            <button class="btn" id="dlg-cancel">Zrušit</button>
            <button class="btn ${this._dialog.danger ? "danger" : "filled"}" id="dlg-ok">${esc(this._dialog.ok)}</button>
          </div></div></div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">Tecomat PLC · ovladače${info ? ` <span style="opacity:.7;font-size:14px">${esc(info.model)} · program ${info.program}</span>` : ""}</div>
        ${entrySel}
        <button class="iconbtn" id="reload" title="Načíst z PLC" ${this._busy || !this._entry ? "disabled" : ""}>${icon("mdi:refresh")}</button>
      </div>
      <div class="content ${this._narrow ? "narrow" : ""}">
        <div class="col">${left}</div>
        <div class="col">${right}</div>
      </div>
      ${dlg}`;

    const root = this.shadowRoot;
    const mb = root.querySelector("ha-menu-button");
    if (mb) {
      mb.hass = this._hass;
      mb.narrow = this._narrow;
    }
    const on = (sel, fn) => root.querySelectorAll(sel).forEach((el) => el.addEventListener("click", () => fn(el)));
    on(".item[data-b]", (el) => {
      this._sel = Number(el.dataset.b);
      this._render();
    });
    on(".chip:not([disabled])", (el) =>
      this._toggleOpt(Number(el.dataset.c), this._sel, el.dataset.g, Number(el.dataset.v))
    );
    on("button[data-par]", (el) => {
      const p = this._info.params.find((x) => x.p === Number(el.dataset.par));
      if (p) this._saveParam(p, root.getElementById(`par-${p.p}`).value);
    });
    on("button[data-corr]", (el) => {
      const idx = Number(el.dataset.corr);
      this._saveCorr(idx, root.getElementById(`in-${idx}`).value);
    });
    on("button[data-restore]", (el) => this._restore(el.dataset.restore));
    on("button[data-del]", (el) => this._delete(el.dataset.del));
    on("#reload", () => this._readPlc());
    on("#savever", () => this._saveVersion());
    on("#export", () => this._export());
    const fileIn = root.getElementById("importfile");
    on("#importbtn", () => fileIn && fileIn.click());
    if (fileIn) fileIn.addEventListener("change", () => fileIn.files[0] && this._import(fileIn.files[0]));
    const es = root.getElementById("entry");
    if (es) es.addEventListener("change", () => this._selectEntry(es.value));
    if (this._dialog) {
      const input = root.getElementById("dlg-input");
      const okVal = () => (this._dialog.input !== null ? input.value : true);
      on("#dlg-ok", () => this._closeDialog(okVal()));
      on("#dlg-cancel", () => this._closeDialog(this._dialog.input !== null ? null : false));
      const bg = root.getElementById("dlg-bg");
      bg.addEventListener("click", (ev) => {
        if (ev.target === bg) this._closeDialog(this._dialog.input !== null ? null : false);
      });
      if (input)
        input.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") this._closeDialog(input.value);
          if (ev.key === "Escape") this._closeDialog(null);
        });
    }
  }
}

customElements.define("tecomat-plc-panel", TecomatPlcPanel);
