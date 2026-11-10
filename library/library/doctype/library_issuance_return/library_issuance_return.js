// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Issuance Return", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = ["Sales Invoice", "Stock Entry"];
		frm.set_query("against_issuance", () => ({ filters: { docstatus: 1 } }));
	},
	against_issuance(frm) {
		if (!frm.doc.against_issuance || frm.doc.docstatus !== 0) return;
		frappe.call({
			method: "library.library.doctype.library_issuance_return.library_issuance_return.get_returnable_items",
			args: { issuance: frm.doc.against_issuance },
			callback(r) {
				frm.clear_table("items");
				(r.message || []).forEach((row) => frm.add_child("items", row));
				frm.refresh_field("items");
				if (!(r.message || []).length) {
					frappe.msgprint(__("Every book of this issuance has already been returned."));
				}
			},
		});
	},
});
