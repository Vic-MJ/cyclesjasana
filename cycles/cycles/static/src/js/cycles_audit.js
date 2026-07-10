/** @odoo-module **/

import {Component, useState, useRef, onMounted, onWillUnmount} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class CyclesAudit extends Component {
  static template = "cycles.CyclesAudit";
  static props = ["*"];

  setup() {
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.scanInputRef = useRef("scanInput");

    this.state = useState({
      step: "config", // config | scanning | result

      // Config
      locations: [],
      selectedLocationId: "",
      locationQuery: "",
      locationListOpen: false,
      garmentTypes: [],
      selectedGarmentTypeIds: [],

      // Scanning
      expectedCount: 0,
      epcs: [],
      foundEpcs: [],
      ignoredEpcs: [],
      scanActive: false,
      isLoading: false,

      // Result
      result: null,
      isProcessing: false,
    });

    // Non-reactive internal sets for O(1) lookup
    this._scannedEpcSet = new Set();
    this._expectedEpcSet = new Set();
    this._foundEpcSet = new Set();

    this._keyBuffer = "";
    this._onDocKeydown = this._onDocKeydown.bind(this);

    onMounted(async () => {
      await this._loadConfigData();
      document.addEventListener("keydown", this._onDocKeydown, true);
    });

    onWillUnmount(() => {
      this._scannedEpcSet.clear();
      this._expectedEpcSet.clear();
      this._foundEpcSet.clear();
      document.removeEventListener("keydown", this._onDocKeydown, true);
    });
  }

  // -------------------------------------------------------------------------
  // Carga de datos
  // -------------------------------------------------------------------------

  async _loadConfigData() {
    const data = await this.orm.call("cycles.audit", "get_audit_config_data", []);
    this.state.locations = data.locations;
    this.state.garmentTypes = data.garment_types;
  }

  // -------------------------------------------------------------------------
  // Config – Ubicación (autocomplete)
  // -------------------------------------------------------------------------

  get filteredLocations() {
    const q = (this.state.locationQuery || "").trim().toLowerCase();
    if (!q) return this.state.locations.slice(0, 20);
    return this.state.locations
      .filter((loc) => (loc.name || "").toLowerCase().includes(q))
      .slice(0, 20);
  }

  get selectedLocation() {
    if (!this.state.selectedLocationId) return null;
    const id = parseInt(this.state.selectedLocationId);
    return this.state.locations.find((l) => l.id === id) || null;
  }

  onLocationQueryInput(ev) {
    this.state.locationQuery = ev.target.value;
    this.state.locationListOpen = true;
    if (this.state.selectedLocationId) {
      this.state.selectedLocationId = "";
    }
  }

  onLocationFocus() {
    this.state.locationListOpen = true;
  }

  onLocationBlur() {
    setTimeout(() => {
      this.state.locationListOpen = false;
    }, 150);
  }

  selectLocation(loc) {
    this.state.selectedLocationId = loc.id;
    this.state.locationQuery = loc.name;
    this.state.locationListOpen = false;
  }

  clearLocation() {
    this.state.selectedLocationId = "";
    this.state.locationQuery = "";
    this.state.locationListOpen = true;
  }

  // -------------------------------------------------------------------------
  // Config – Tipos de prenda (toggle)
  // -------------------------------------------------------------------------

  toggleGarmentType(id) {
    const ids = this.state.selectedGarmentTypeIds;
    const idx = ids.indexOf(id);
    if (idx === -1) {
      this.state.selectedGarmentTypeIds = [...ids, id];
    } else {
      this.state.selectedGarmentTypeIds = ids.filter((x) => x !== id);
    }
  }

  isGarmentTypeSelected(id) {
    return this.state.selectedGarmentTypeIds.includes(id);
  }

  get canStartAudit() {
    return !!this.state.selectedLocationId;
  }

  // -------------------------------------------------------------------------
  // Transición config → scanning
  // -------------------------------------------------------------------------

  async startAudit() {
    if (!this.canStartAudit) return;
    this.state.isLoading = true;
    try {
      const expected = await this.orm.call(
        "cycles.audit",
        "load_expected_inventory",
        [
          parseInt(this.state.selectedLocationId),
          this.state.selectedGarmentTypeIds.map(Number),
        ]
      );
      this._expectedEpcSet = new Set(expected.map((item) => item.lot_name));
      this.state.expectedCount = expected.length;

      // Reset scan state
      this._scannedEpcSet.clear();
      this._foundEpcSet.clear();
      this.state.epcs = [];
      this.state.foundEpcs = [];
      this.state.ignoredEpcs = [];
      this.state.step = "scanning";
      this._focusScanInput();
    } catch (err) {
      this.notification.add(
        err.data?.message || err.message || "Error al cargar el inventario",
        {type: "danger", sticky: true}
      );
    } finally {
      this.state.isLoading = false;
    }
  }

  _focusScanInput() {
    setTimeout(() => {
      const el = this.scanInputRef.el;
      if (el) {
        el.value = "";
        el.focus();
        this.state.scanActive = true;
      }
    }, 100);
  }

  // -------------------------------------------------------------------------
  // Escaneo
  // -------------------------------------------------------------------------

  onScannerInput(ev) {
    const el = ev.target;
    const raw = el.value;
    const lines = raw.split("\n");
    const completeLines = lines.slice(0, -1);
    for (const line of completeLines) {
      this._classifyEpc(line);
    }
    el.value = lines[lines.length - 1];
  }

  _classifyEpc(rawEpc) {
    const epc = (rawEpc || "").trim();
    if (!epc || this._scannedEpcSet.has(epc)) return;
    this._scannedEpcSet.add(epc);
    this.state.epcs = [...this.state.epcs, epc];

    if (this._expectedEpcSet.has(epc)) {
      this._foundEpcSet.add(epc);
      this.state.foundEpcs = [...this.state.foundEpcs, epc];
    } else {
      this.state.ignoredEpcs = [...this.state.ignoredEpcs, epc];
    }
  }

  _onDocKeydown(ev) {
    if (this.state.step !== "scanning") return;
    if (ev.key === "Enter") {
      if (this._keyBuffer) {
        this._classifyEpc(this._keyBuffer);
        this._keyBuffer = "";
      }
      return;
    }
    if (ev.key && ev.key.length === 1) {
      this._keyBuffer += ev.key;
    }
  }

  activateScanner() {
    this._focusScanInput();
  }

  clearAll() {
    this._scannedEpcSet.clear();
    this._foundEpcSet.clear();
    this.state.epcs = [];
    this.state.foundEpcs = [];
    this.state.ignoredEpcs = [];
    if (this.scanInputRef.el) {
      this.scanInputRef.el.value = "";
    }
    this._focusScanInput();
  }

  get missingCount() {
    return Math.max(0, this.state.expectedCount - this.state.foundEpcs.length);
  }

  // -------------------------------------------------------------------------
  // Confirmar auditoría
  // -------------------------------------------------------------------------

  async confirmAudit() {
    if (!this.state.epcs.length) {
      this.notification.add("No hay EPCs escaneados", {type: "warning"});
      return;
    }
    this.state.isProcessing = true;
    try {
      const result = await this.orm.call("cycles.audit", "process_audit", [
        this.state.epcs,
        parseInt(this.state.selectedLocationId),
        this.state.selectedGarmentTypeIds.map(Number),
      ]);
      this.state.result = result;
      this.state.step = "result";
    } catch (err) {
      this.notification.add(
        err.data?.message || err.message || "Error al procesar la auditoría",
        {type: "danger", sticky: true}
      );
    } finally {
      this.state.isProcessing = false;
    }
  }

  // -------------------------------------------------------------------------
  // Resultado – reiniciar
  // -------------------------------------------------------------------------

  reset() {
    this._scannedEpcSet.clear();
    this._expectedEpcSet.clear();
    this._foundEpcSet.clear();
    this._keyBuffer = "";
    Object.assign(this.state, {
      step: "config",
      selectedLocationId: "",
      locationQuery: "",
      locationListOpen: false,
      selectedGarmentTypeIds: [],
      expectedCount: 0,
      epcs: [],
      foundEpcs: [],
      ignoredEpcs: [],
      scanActive: false,
      isLoading: false,
      result: null,
      isProcessing: false,
    });
  }
}

registry.category("actions").add("cycles_audit_scanner", CyclesAudit);
