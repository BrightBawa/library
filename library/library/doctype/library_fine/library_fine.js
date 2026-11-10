// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Fine", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.payment_status === "Unpaid" && !frm.doc.sales_invoice && frm.doc.fine_amount) {
			frm.add_custom_button(__("Bill to Student Account"), () => {
				frappe.call({
					method: "library.library.billing.bill_fine_now",
					args: { fine: frm.doc.name },
					freeze: true,
					callback(r) {
						if (r.message) {
							frappe.show_alert({ message: __("Billed on {0}", [r.message]), indicator: "green" });
							frm.reload_doc();
						}
					},
				});
			});
		}
	},
});
