// Tecomat PLC: konfigurace ovladačů (stránka dodávaná integrací tecomat_plc)
//
// Vzhled podle Home Assistant: barvy a rozměry z proměnných aktivního motivu
// (světlý / tmavý / vlastní), horní lišta, karty, tlačítka, ikony mdi a dialogy.
//
// Data přes websocket API integrace:
//   tecomat_plc/entries, /info, /config/get, /config/set,
//   /versions/list, /versions/save, /versions/restore, /versions/delete, /versions/import
//
// PLC je zdroj pravdy: konfigurace se čte z PLC, verze se ukládají ručně.

const GROUPS = [
  { key: "s", shift: 0, title: "Krátký stisk", opts: [[1, "Přepni"], [2, "Vypni"], [3, "Zapni"]] },
  { key: "l", shift: 2, title: "Dlouhý stisk", opts: [[1, "Přepni"], [2, "Vypni"], [3, "Zapni"]] },
  { key: "d", shift: 4, title: "Stmívání", opts: [[1, "Přidej"], [2, "Uber"]] },
];
const CORR_BASE = 10000;

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
    position: sticky; top: 0; z-index: 2;
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
    this._info = null;
    this._cfg = null;
    this._error = "";
    this._render();
    try {
      this._info = await this._ws("info");
      if (this._sel === null || !this._info.buttons.find((b) => b.m === this._sel))
        this._sel = this._info.buttons.length ? this._info.buttons[0].m : null;
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

  _code(c, b) {
    return (this._cfg && this._cfg.map[`${c},${b}`]) || 0;
  }
  _version(id) {
    return this._versions.find((v) => v.id === id) || null;
  }
  _diff(ver) {
    if (!ver || !this._cfg) return null;
    let n = 0;
    const keys = new Set([...Object.keys(ver.map), ...Object.keys(this._cfg.map)]);
    for (const k of keys) if ((ver.map[k] || 0) !== (this._cfg.map[k] || 0)) n++;
    const vc = ver.corr || {};
    const cc = this._cfg.corr || {};
    for (const k of new Set([...Object.keys(vc), ...Object.keys(cc)])) if ((vc[k] || 0) !== (cc[k] || 0)) n++;
    return n;
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
  _alerts() {
    const a = (type, ic, text) => `<div class="alert ${type}">${icon(ic)}<span>${text}</span></div>`;
    const out = [];
    if (this._busy) out.push(a("info", "mdi:progress-clock", esc(this._busy)));
    if (this._error) out.push(a("error", "mdi:alert-circle", esc(this._error)));
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
    const info = this._info;
    const ready = !!(info && this._cfg && !this._busy);
    const fmtT = (v) => (v === null || v === undefined ? "–" : `${(v / 10).toFixed(1)} °C`);

    const entrySel =
      this._entries.length > 1
        ? `<select id="entry">${this._entries
            .map((e) => `<option value="${e.entry_id}" ${e.entry_id === this._entry ? "selected" : ""}>${esc(e.title)}</option>`)
            .join("")}</select>`
        : "";

    let left = "";
    let right = `<div class="card"><div class="card-header">${icon("mdi:light-switch")}Načítám…</div>${this._alerts()}</div>`;

    if (info) {
      // tlačítka
      const byGroup = {};
      for (const b of info.buttons) (byGroup[b.group] ||= []).push(b);
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

      // matice
      const btn = info.buttons.find((b) => b.m === this._sel);
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
      right = `
        <div class="card">
          <div class="card-header">${icon("mdi:lightbulb-group")}
            <div style="display:flex;flex-direction:column">Osvětlení
              <span class="sub">${btn ? `${esc(this._groupName(btn.group))} · ${esc(btn.name)}` : "Vyberte tlačítko"}</span>
            </div>
          </div>
          ${this._alerts()}
          ${rows ? `<div class="scroll"><table><tr><th class="left">Okruh</th>${head}</tr>${rows}</table></div>` : ""}
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
    } else if (this._error) {
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
    on(".item", (el) => {
      this._sel = Number(el.dataset.b);
      this._render();
    });
    on(".chip:not([disabled])", (el) =>
      this._toggleOpt(Number(el.dataset.c), this._sel, el.dataset.g, Number(el.dataset.v))
    );
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
