/** @odoo-module */

import { describe, expect, test } from "@odoo/hoot";
import { animationFrame } from "@odoo/hoot-mock";
import { queryOne } from "@odoo/hoot-dom";
import { RfidScanner } from "@cycles/js/rfid_scanner";
import {
    contains,
    makeMockEnv,
    mountWithCleanup,
} from "@web/../tests/web_test_helpers";

describe.tags("cycles", "cycles_rfid_scanner");

async function scanViaDocumentKeydown(epc) {
    const scanInput = queryOne("textarea");
    scanInput.dispatchEvent(new Event("focus", { bubbles: true }));
    await animationFrame();

    scanInput.dispatchEvent(new Event("blur", { bubbles: true }));
    await animationFrame();

    for (const key of epc) {
        document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    document.dispatchEvent(
        new KeyboardEvent("keydown", { key: "Enter", bubbles: true })
    );
    await animationFrame();
}

describe("Cycles RFID Scanner", () => {
    test(
        "pending receptions keep the handheld flow usable after scan input blur",
        async () => {
            let processScanArgs;
            const env = await makeMockEnv();
            env.services.action = { doAction: () => {} };
            env.services.notification = { add: () => {} };
            env.services.orm = {
                call: async (model, method, args) => {
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_scan_operations"
                    ) {
                        return [
                            {
                                code: "entrada",
                                name: "Ingreso de Inventario",
                                icon: "fa-download",
                                picking_type_id: 11,
                                location_src_id: 21,
                                location_dest_id: 22,
                                needs_garment_type: true,
                                needs_employee: false,
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_pending_receptions"
                    ) {
                        return [
                            {
                                picking_id: 31,
                                picking_name: "WH/IN/00031",
                                origin: "PO00031",
                                partner_name: "Proveedor Test",
                                lines: [
                                    {
                                        product_id: 42,
                                        product_name: "Filipina RFID",
                                        garment_type_id: 7,
                                        garment_type_name: "Filipina",
                                        demand: 2,
                                    },
                                ],
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_delivery_employees"
                    ) {
                        return [];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "process_scan"
                    ) {
                        processScanArgs = args;
                        return {
                            picking_id: 99,
                            picking_name: "WH/IN/00099",
                            processed_count: 1,
                            error_count: 0,
                            errors: [],
                        };
                    }
                    throw new Error(`Unexpected call: ${model}.${method}`);
                },
                searchRead: async (model) => {
                    if (model === "cycles.garment.type") {
                        return [{ id: 7, name: "Filipina" }];
                    }
                    throw new Error(`Unexpected searchRead: ${model}`);
                },
            };

            await mountWithCleanup(RfidScanner, { env });
            await animationFrame();
            await animationFrame();

            await contains(".btn.w-100").click();

            expect(".o_cycles_pending_reception_select").toHaveCount(1);
            expect(".o_cycles_start_scan_btn").toBeDisabled();

            const receptionSelect = queryOne(".o_cycles_pending_reception_select");
            receptionSelect.value = "31";
            receptionSelect.dispatchEvent(new Event("change", { bubbles: true }));
            await animationFrame();

            expect(".o_cycles_reception_product_select").toHaveCount(1);
            expect(".o_cycles_reception_product_select").toHaveValue("42");
            expect(".o_cycles_reception_product_select option:eq(1)").toHaveText(
                "Filipina RFID (2)"
            );
            expect(".o_cycles_start_scan_btn").not.toBeDisabled();

            await contains(".o_cycles_start_scan_btn").click();
            await animationFrame();

            expect(".btn.btn-lg").toHaveText("Activar escáner");

            await scanViaDocumentKeydown("EPC-001");

            expect(".btn.btn-lg").toHaveText("Activar escáner");
            expect(".list-group-item code").toHaveText("EPC-001");

            await contains(".btn.btn-success.flex-grow-1").click();
            await animationFrame();

            expect(processScanArgs).toEqual([
                ["EPC-001"],
                "entrada",
                11,
                21,
                22,
                false,
                7,
                31,
                42,
            ]);
        }
    );

    test(
        "product reception failures surface the backend contract message in the UI",
        async () => {
            const notifications = [];
            const env = await makeMockEnv();
            env.services.action = { doAction: () => {} };
            env.services.notification = {
                add: (message, options) => notifications.push({ message, options }),
            };
            env.services.orm = {
                call: async (model, method) => {
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_scan_operations"
                    ) {
                        return [
                            {
                                code: "entrada",
                                name: "Ingreso de Inventario",
                                icon: "fa-download",
                                picking_type_id: 14,
                                location_src_id: 24,
                                location_dest_id: 25,
                                needs_garment_type: true,
                                needs_employee: false,
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_pending_receptions"
                    ) {
                        return [
                            {
                                picking_id: 33,
                                picking_name: "WH/IN/00033",
                                origin: "PO00033",
                                partner_name: "Proveedor Error",
                                lines: [
                                    {
                                        product_id: 61,
                                        product_name: "Chaqueta RFID",
                                        garment_type_id: 10,
                                        garment_type_name: "Chaqueta",
                                        demand: 1,
                                    },
                                ],
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_delivery_employees"
                    ) {
                        return [];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "process_scan"
                    ) {
                        throw Object.assign(new Error(), {
                            data: {
                                message:
                                    "La recepción WH/IN/00033 no espera el tipo de prenda seleccionado.",
                            },
                        });
                    }
                    throw new Error(`Unexpected call: ${model}.${method}`);
                },
                searchRead: async (model) => {
                    if (model === "cycles.garment.type") {
                        return [{ id: 10, name: "Chaqueta" }];
                    }
                    throw new Error(`Unexpected searchRead: ${model}`);
                },
            };

            await mountWithCleanup(RfidScanner, { env });
            await animationFrame();
            await animationFrame();

            await contains(".btn.w-100").click();

            const receptionSelect = queryOne(".o_cycles_pending_reception_select");
            receptionSelect.value = "33";
            receptionSelect.dispatchEvent(new Event("change", { bubbles: true }));
            await animationFrame();

            await contains(".o_cycles_start_scan_btn").click();
            await animationFrame();
            await scanViaDocumentKeydown("EPC-ERR-1");

            await contains(".btn.btn-success.flex-grow-1").click();
            await animationFrame();

            expect(notifications).toEqual([
                {
                    message:
                        "La recepción WH/IN/00033 no espera el tipo de prenda seleccionado.",
                    options: { type: "danger", sticky: true },
                },
            ]);
            expect(".list-group-item code").toHaveText("EPC-ERR-1");
        }
    );

    test(
        "multi-line pending receptions require choosing the product and keep the garment type in sync",
        async () => {
            let processScanArgs;
            const env = await makeMockEnv();
            env.services.action = { doAction: () => {} };
            env.services.notification = { add: () => {} };
            env.services.orm = {
                call: async (model, method, args) => {
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_scan_operations"
                    ) {
                        return [
                            {
                                code: "entrada",
                                name: "Ingreso de Inventario",
                                icon: "fa-download",
                                picking_type_id: 13,
                                location_src_id: 23,
                                location_dest_id: 24,
                                needs_garment_type: true,
                                needs_employee: false,
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_pending_receptions"
                    ) {
                        return [
                            {
                                picking_id: 32,
                                picking_name: "WH/IN/00032",
                                origin: "PO00032",
                                partner_name: "Proveedor Multi",
                                lines: [
                                    {
                                        product_id: 52,
                                        product_name: "Pantalón RFID",
                                        garment_type_id: 8,
                                        garment_type_name: "Pantalón",
                                        demand: 1,
                                    },
                                    {
                                        product_id: 53,
                                        product_name: "Bata RFID",
                                        garment_type_id: 9,
                                        garment_type_name: "Bata",
                                        demand: 3,
                                    },
                                ],
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_delivery_employees"
                    ) {
                        return [];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "process_scan"
                    ) {
                        processScanArgs = args;
                        return {
                            picking_id: 100,
                            picking_name: "WH/IN/00100",
                            processed_count: 1,
                            error_count: 0,
                            errors: [],
                        };
                    }
                    throw new Error(`Unexpected call: ${model}.${method}`);
                },
                searchRead: async (model) => {
                    if (model === "cycles.garment.type") {
                        return [
                            { id: 8, name: "Pantalón" },
                            { id: 9, name: "Bata" },
                        ];
                    }
                    throw new Error(`Unexpected searchRead: ${model}`);
                },
            };

            const component = await mountWithCleanup(RfidScanner, { env });
            await animationFrame();
            await animationFrame();

            await contains(".btn.w-100").click();

            const receptionSelect = queryOne(".o_cycles_pending_reception_select");
            receptionSelect.value = "32";
            receptionSelect.dispatchEvent(new Event("change", { bubbles: true }));
            await animationFrame();

            expect(".o_cycles_start_scan_btn").toBeDisabled();
            expect(".o_cycles_reception_product_select option").toHaveCount(3);
            expect(".o_cycles_reception_product_select option:eq(1)").toHaveText(
                "Pantalón RFID (1)"
            );
            expect(".o_cycles_reception_product_select option:eq(2)").toHaveText(
                "Bata RFID (3)"
            );

            const productSelect = queryOne(".o_cycles_reception_product_select");
            productSelect.value = "53";
            productSelect.dispatchEvent(new Event("change", { bubbles: true }));
            await animationFrame();

            expect(".o_cycles_start_scan_btn").not.toBeDisabled();
            expect(component.state.selectedGarmentTypeId).toBe(9);

            component.state.epcs = ["EPC-ML-1"];
            await component.confirmScan();

            expect(processScanArgs).toEqual([
                ["EPC-ML-1"],
                "entrada",
                13,
                23,
                24,
                false,
                9,
                32,
                53,
            ]);
        }
    );

    test(
        "delivery loads a handheld-friendly employee selection list",
        async () => {
            const env = await makeMockEnv();
            let deliveryEmployeeCalls = 0;
            env.services.action = { doAction: () => {} };
            env.services.notification = { add: () => {} };
            env.services.orm = {
                call: async (model, method, args) => {
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_scan_operations"
                    ) {
                        return [
                            {
                                code: "entrega",
                                name: "Ropería → En Uso",
                                icon: "fa-user",
                                picking_type_id: 15,
                                location_src_id: 25,
                                location_dest_id: 26,
                                needs_garment_type: false,
                                needs_employee: true,
                            },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_delivery_employees"
                    ) {
                        deliveryEmployeeCalls += 1;
                        expect(args).toEqual([]);
                        return [
                            { id: 8, name: "Ana Scanner" },
                            { id: 12, name: "Bruno RFID" },
                        ];
                    }
                    if (
                        model === "cycles.rfid.processor" &&
                        method === "get_pending_receptions"
                    ) {
                        return [];
                    }
                    throw new Error(`Unexpected call: ${model}.${method}`);
                },
                searchRead: async (model) => {
                    if (model === "cycles.garment.type") {
                        return [];
                    }
                    throw new Error(`Unexpected searchRead: ${model}`);
                },
            };

            const component = await mountWithCleanup(RfidScanner, { env });
            await animationFrame();
            await animationFrame();

            await contains(".btn.w-100").click();
            await animationFrame();

            expect(deliveryEmployeeCalls).toBe(1);
            expect(component.state.employees).toEqual([
                { id: 8, name: "Ana Scanner" },
                { id: 12, name: "Bruno RFID" },
            ]);
            expect(".o_cycles_employee_select option").toHaveCount(3);
            expect(".o_cycles_employee_select option:eq(1)").toHaveText(
                "Ana Scanner"
            );

            const employeeSelect = queryOne(".o_cycles_employee_select");
            employeeSelect.value = "12";
            employeeSelect.dispatchEvent(new Event("change", { bubbles: true }));
            await animationFrame();

            expect(component.state.selectedEmployeeId).toBe("12");
            expect(".o_cycles_start_scan_btn").not.toBeDisabled();
        }
    );
});
