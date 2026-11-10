// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Book", {
	refresh(frm) {
		if (!frm.is_new() && frm.doc.book_type === "Issue" && frm.doc.item) {
			frm.add_custom_button(__("Request Stock from Stores"), () => {
				frappe.model.open_mapped_doc({
					method: "library.library.stock.make_stock_request",
					frm,
				});
			});
		}
	},
	book_type(frm) {
		if (frm.doc.book_type !== "Issue") {
			frm.set_value("is_billable", 0);
		}
	},
});
