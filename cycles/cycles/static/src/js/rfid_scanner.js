/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RfidScanner extends Component {
  static template = "cycles.RfidScanner";
  static props = ["*"];

  setup() {
    this.orm = useService("orm");
    this.notification = useService("notification");
    this.actionService = useService("action");
    this.scanInputRef = useRef("scanInput");

    this.state = useState({
      step: "config", // config | scanning | result
      operations: [],
      selectedOp: null,
      garmentTypes: [],
      selectedGarmentTypeId: "",
      pendingReceptions: [],
      selectedPickingId: "",
      employees: [],
      selectedEmployeeId: "",
      employeeQuery: "",
      employeeListOpen: false,
      epcs: [],
      isProcessing: false,
      result: null,
      scanActive: false,
      epcDetails: {}, // [MODIFICACION] Guarda la relacion EPC -> Nombre del Producto
      showBackorderModal: false,
      pendingWizardId: false,
      pendingResult: null,
      enlargedImage: null,
    });

    // [MODIFICACION] Temporizador para agrupar consultas y no saturar el servidor al escanear rápido
    this._pendingEpcsToResolve = new Set();
    this._resolveTimeout = null;

    // Internal set for fast deduplication (not reactive, synced to state.epcs)
    this._epcSet = new Set();

    // Buffer for the document-level keydown listener (RFID scanner sends
    // characters one by one, terminated by Enter). This captures input even
    // when the hidden textarea loses focus on handheld devices.
    this._keyBuffer = "";
    this._onDocKeydown = this._onDocKeydown.bind(this);

    onMounted(async () => {
      await this._loadData();
      document.addEventListener("keydown", this._onDocKeydown, true);
    });

    onWillUnmount(() => {
      this._epcSet.clear();
      document.removeEventListener("keydown", this._onDocKeydown, true);
    });
  }

  // -------------------------------------------------------------------------
  // Carga de datos
  // -------------------------------------------------------------------------

  async _loadData() {
    const [operations, garmentTypes, employees, pendingReceptions] = await Promise.all([
      this.orm.call("cycles.rfid.processor", "get_scan_operations", []),
      this.orm.searchRead("cycles.garment.type", [["active", "=", true]], ["id", "name"]),
      this.orm.searchRead("hr.employee", [["active", "=", true]], ["id", "name"], { order: "name asc" }),
      this.orm.call("cycles.rfid.processor", "get_pending_receptions", []),
    ]);
    this.state.operations = operations;
    this.state.garmentTypes = garmentTypes;
    this.state.employees = employees;
    this.state.pendingReceptions = pendingReceptions;
  }

  get selectedReception() {
    if (!this.state.selectedPickingId || this.state.selectedPickingId === "manual") return null;
    const id = parseInt(this.state.selectedPickingId);
    return this.state.pendingReceptions.find((p) => p.picking_id === id) || null;
  }

  onReceptionChange() {
    if (this.state.selectedPickingId) {
      setTimeout(() => this.startScanning(), 50);
    }
  }

  // -------------------------------------------------------------------------
  // Paso 1 – Configuración
  // -------------------------------------------------------------------------

  selectOperation(op) {
    this.state.selectedOp = op;
    this.state.selectedGarmentTypeId = "";
    this.state.selectedPickingId = "";
    this.state.selectedEmployeeId = "";
    this.state.employeeQuery = "";
    this.state.employeeListOpen = false;

    // Auto-iniciar si la operación no requiere datos adicionales
    if (!op.needs_garment_type && !op.needs_employee) {
        // Necesitamos un pequeño delay para que OWL actualice el estado antes de enfocar el input
        setTimeout(() => this.startScanning(), 50);
    }
  }

  get filteredEmployees() {
    const q = (this.state.employeeQuery || "").trim().toLowerCase();
    if (!q) return this.state.employees.slice(0, 20);
    return this.state.employees
      .filter((emp) => {
        const name = (emp.name || "").toLowerCase();
        return name.includes(q);
      })
      .slice(0, 20);
  }

  get selectedEmployee() {
    if (!this.state.selectedEmployeeId) return null;
    const id = parseInt(this.state.selectedEmployeeId);
    return this.state.employees.find((e) => e.id === id) || null;
  }

  selectEmployee(emp) {
    this.state.selectedEmployeeId = emp.id;
    this.state.employeeQuery = emp.name;
    this.state.employeeListOpen = false;
    setTimeout(() => this.startScanning(), 50);
  }

  clearEmployee() {
    this.state.selectedEmployeeId = "";
    this.state.employeeQuery = "";
    this.state.employeeListOpen = true;
  }

  onEmployeeQueryInput(ev) {
    this.state.employeeQuery = ev.target.value;
    this.state.employeeListOpen = true;
    if (this.state.selectedEmployeeId) {
      this.state.selectedEmployeeId = "";
    }
  }

  onEmployeeFocus() {
    this.state.employeeListOpen = true;
  }

  onEmployeeBlur() {
    setTimeout(() => {
      this.state.employeeListOpen = false;
    }, 150);
  }

  get canStartScanning() {
    const op = this.state.selectedOp;
    if (!op) return false;
    if (op.needs_garment_type && !this.state.selectedPickingId) return false;
    if (op.needs_employee && !this.state.selectedEmployeeId) return false;
    return true;
  }

  get isLastItemInOrder() {
    if (this.state.selectedOp && this.state.selectedOp.code === 'entrada' && this.selectedReception) {
      const selectedLine = this.selectedReception.lines.find(l => l.product_id == this.state.selectedGarmentTypeId);
      if (!selectedLine) return false;
      
      // If we haven't met the demand for the current product, it's not the last item.
      if (this.state.epcs.length < selectedLine.demand) return false;
      
      // If we met the demand for the current product, check if there are other products left.
      const otherLines = this.selectedReception.lines.filter(l => l.product_id != this.state.selectedGarmentTypeId);
      
      // If there are no other lines, then this is indeed the very last item of the order.
      return otherLines.length === 0;
    }
    return false;
  }

  get currentDemand() {
    if (this.state.selectedOp && this.state.selectedOp.code === 'entrada' && this.selectedReception && this.state.selectedGarmentTypeId) {
      const selectedLine = this.selectedReception.lines.find(l => l.product_id == this.state.selectedGarmentTypeId);
      return selectedLine ? selectedLine.demand : 0;
    }
    return 0;
  }

  startScanning() {
    if (!this.canStartScanning) return;
    this.state.step = "scanning";
    this.state.epcs = [];
    this._epcSet.clear();
    this.state.scanActive = false;
    if (this.scanInputRef.el) {
      this.scanInputRef.el.blur();
    }
  }

  _focusScanInput() {
    const el = this.scanInputRef.el;
    if (el) {
      el.value = "";
      el.focus();
      this.state.scanActive = true;
    }
  }

  // -------------------------------------------------------------------------
  // Paso 2 – Escaneo
  // -------------------------------------------------------------------------

  /**
   * Se llama en cada tecla del textarea oculto.
   * El lector RFID envía: <EPC><Enter> por cada etiqueta.
   */
  onScannerInput(ev) {
    const el = ev.target;
    const raw = el.value;
    const lines = raw.split("\n");

    const completeLines = lines.slice(0, -1);

    for (const line of completeLines) {
      this._pushEpc(line);
    }

    el.value = lines[lines.length - 1];
  }

  _pushEpc(rawEpc) {
    if (this.state.selectedOp && this.state.selectedOp.code === 'entrada' && !this.state.selectedGarmentTypeId) {
        this.notification.add("¡Selecciona la siguiente prenda de la lista arriba antes de escanear!", { type: "warning" });
        return false;
    }
    const epc = (rawEpc || "").trim();
    if (!epc || this._epcSet.has(epc)) return false;

    // Verificar que no se exceda la demanda de la orden
    if (this.state.selectedOp && this.state.selectedOp.code === 'entrada' && this.state.selectedGarmentTypeId) {
        const selectedLine = this.selectedReception?.lines.find(l => l.product_id == this.state.selectedGarmentTypeId);
        if (selectedLine && this.state.epcs.length >= selectedLine.demand) {
            this.notification.add(`¡Límite alcanzado! La orden solo pide ${selectedLine.demand} prendas de este tipo. ¡Aleja el lector de las demás prendas!`, { type: "danger" });
            return false;
        }
    }
    this._epcSet.add(epc);
    this.state.epcs = [...this.state.epcs, epc];

    if (this.state.selectedOp && this.state.selectedOp.code === 'entrada' && this.state.selectedGarmentTypeId) {
        const selectedLine = this.selectedReception?.lines.find(l => l.product_id == this.state.selectedGarmentTypeId);
        if (selectedLine) {
            this.state.epcDetails[epc] = {
                product_name: selectedLine.garment_type_name,
                product_id: selectedLine.product_id,
                employee_name: false
            };
        }
    } else {
        this._pendingEpcsToResolve.add(epc);
        if (this._resolveTimeout) clearTimeout(this._resolveTimeout);
        this._resolveTimeout = setTimeout(() => this._resolvePendingEpcs(), 300);
    }

    return true;
  }

  async _resolvePendingEpcs() {
    // [MODIFICACION] Consulta a Odoo el nombre del producto de los EPCs escaneados recientemente
    if (this._pendingEpcsToResolve.size === 0) return;
    const epcsToResolve = Array.from(this._pendingEpcsToResolve);
    this._pendingEpcsToResolve.clear();
    try {
      const details = await this.orm.call("cycles.rfid.processor", "resolve_epcs", [epcsToResolve]);
      Object.assign(this.state.epcDetails, details);
    } catch (e) {
    }
  }

  /**
   * Document-level keydown fallback. Captures characters even when the
   * textarea loses focus (common on handhelds when the virtual keyboard
   * hides or the user taps elsewhere). Active only during the scanning step.
   */
  _onDocKeydown(ev) {
    if (this.state.step !== "scanning") return;
    // If the textarea handled it via t-on-input, the keystroke also fires
    // here — but it's idempotent because _pushEpc dedupes.
    if (ev.key === "Enter") {
      if (this._keyBuffer) {
        this._pushEpc(this._keyBuffer);
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

  removeEpc(epc) {
    this._epcSet.delete(epc);
    this.state.epcs = this.state.epcs.filter((e) => e !== epc);
  }

  clearAll() {
    this._epcSet.clear();
    this.state.epcs = [];
    this.state.epcDetails = {};
    if (this.scanInputRef.el) {
      this.scanInputRef.el.value = "";
    }
    this._focusScanInput();
  }

  // -------------------------------------------------------------------------
  // Paso 3 – Confirmar / Procesar
  // -------------------------------------------------------------------------

  async confirmScan() {
    if (!this.state.epcs.length) {
      this.notification.add("No hay EPCs escaneados", { type: "warning" });
      return;
    }

    this.state.isProcessing = true;
    try {
      const op = this.state.selectedOp;
      const result = await this.orm.call("cycles.rfid.processor", "process_scan", [
        this.state.epcs,
        op.code,
        op.picking_type_id,
        op.location_src_id,
        op.location_dest_id,
        this.state.selectedEmployeeId ? parseInt(this.state.selectedEmployeeId) : false,
        this.state.selectedGarmentTypeId ? parseInt(this.state.selectedGarmentTypeId) : false,
        this.state.selectedPickingId && this.state.selectedPickingId !== "manual" ? parseInt(this.state.selectedPickingId) : false,
        true,
      ]);
      
      if (result.requires_backorder) {
        this.state.pendingWizardId = result.wizard_id;
        this.state.pendingResult = result;
        this.state.showBackorderModal = true;
      } else {
        this.state.result = result;
        this.state.step = "result";
      }
    } catch (error) {
      this.notification.add(error.data?.message || error.message || "Error al procesar el escaneo", {
        type: "danger",
        sticky: true,
      });
    } finally {
      this.state.isProcessing = false;
    }
  }

  async saveAndNext() {
    if (!this.state.epcs.length) {
      this.notification.add("No hay EPCs escaneados", { type: "warning" });
      return;
    }

    this.state.isProcessing = true;
    try {
      const op = this.state.selectedOp;
      await this.orm.call("cycles.rfid.processor", "process_scan", [
        this.state.epcs,
        op.code,
        op.picking_type_id,
        op.location_src_id,
        op.location_dest_id,
        this.state.selectedEmployeeId ? parseInt(this.state.selectedEmployeeId) : false,
        this.state.selectedGarmentTypeId ? parseInt(this.state.selectedGarmentTypeId) : false,
        this.state.selectedPickingId && this.state.selectedPickingId !== "manual" ? parseInt(this.state.selectedPickingId) : false,
        false,
      ]);
      
      this.notification.add("Prendas guardadas en la orden. Puedes continuar.", { type: "success" });
      
      // Reset scanning state but KEEP selected picking AND stay in scanning screen
      this._epcSet.clear();
      this.state.epcs = [];
      this.state.selectedGarmentTypeId = "";
      this.state.scanActive = false;
      if (this.scanInputRef.el) {
        this.scanInputRef.el.value = "";
        this.scanInputRef.el.blur();
      }
      this._loadData();
    } catch (error) {
      this.notification.add(error.data?.message || error.message || "Error al procesar el escaneo", {
        type: "danger",
        sticky: true,
      });
    } finally {
      this.state.isProcessing = false;
    }
  }

  async validatePartialPicking() {
    if (!this.state.selectedPickingId) return;
    
    this.state.isProcessing = true;
    try {
      const result = await this.orm.call("cycles.rfid.processor", "validate_picking", [
        parseInt(this.state.selectedPickingId)
      ]);
      if (result) {
        if (result.requires_backorder) {
          this.state.pendingWizardId = result.wizard_id;
          this.state.pendingResult = result;
          this.state.showBackorderModal = true;
        } else {
          this.notification.add(`Recepción ${result.picking_name} validada con éxito.`, { type: "success" });
          this.reset();
        }
      }
    } catch (error) {
      this.notification.add(error.data?.message || error.message || "Error al validar la orden", {
        type: "danger",
        sticky: true,
      });
    } finally {
      this.state.isProcessing = false;
    }
  }

  async submitBackorderDecision(createBackorder) {
    this.state.isProcessing = true;
    try {
      await this.orm.call("cycles.rfid.processor", "process_backorder_decision", [
        this.state.pendingWizardId,
        createBackorder
      ]);
      
      this.state.showBackorderModal = false;
      
      if (this.state.step === "scanning") {
        // Came from confirmScan
        this.state.result = this.state.pendingResult;
        this.state.step = "result";
      } else {
        // Came from validatePartialPicking (Step 2)
        this.notification.add(`Recepción ${this.state.pendingResult.picking_name} validada con éxito.`, { type: "success" });
        this.reset();
      }
      
    } catch (error) {
      this.notification.add(error.data?.message || error.message || "Error al procesar la decisión", {
        type: "danger",
        sticky: true,
      });
    } finally {
      this.state.isProcessing = false;
    }
  }

  // -------------------------------------------------------------------------
  // Paso 4 – Resultado
  // -------------------------------------------------------------------------

  openPicking() {
    if (this.state.result?.picking_id) {
      this.actionService.doAction({
        type: "ir.actions.act_window",
        res_model: "stock.picking",
        res_id: this.state.result.picking_id,
        views: [[false, "form"]],
        target: "current",
      });
    }
  }

  reset() {
    this._epcSet.clear();
    Object.assign(this.state, {
      step: "config",
      selectedOp: null,
      selectedGarmentTypeId: "",
      selectedPickingId: "",
      selectedEmployeeId: "",
      employeeQuery: "",
      employeeListOpen: false,
      epcs: [],
      isProcessing: false,
      result: null,
      scanActive: false,
      enlargedImage: null,
    });
    // Refresh pending receptions: the last one may now be done/backordered.
    this._loadData();
  }

  openImage(productId) {
    this.state.enlargedImage = `/web/image?model=product.product&id=${productId}&field=image_1920`;
  }

  closeImage() {
    this.state.enlargedImage = null;
  }
}

registry.category("actions").add("cycles_rfid_scanner", RfidScanner);
