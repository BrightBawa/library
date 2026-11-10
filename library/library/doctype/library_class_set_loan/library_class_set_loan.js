// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Class Set Loan", {
	setup(frm) {
		frm.set_query("teacher", () => ({ filters: { reference_doctype: "Employee", membership_status: "Active" } }));
		frm.set_query("book", "items", () => ({ filters: { book_type: "Lending" } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus !== 1 || ["Returned", "Closed"].includes(frm.doc.status)) return;
		const ask = (method, label) => {
			const lines = frm.doc.items.filter((r) => r.qty - (r.returned_qty || 0) - (r.lost_qty || 0) > 0);
			const dialog = new frappe.ui.Dialog({
				title: label,
				fields: [
					{ fieldname: "item_row", fieldtype: "Select", label: __("Book"), reqd: 1,
					  options: lines.map((r) => ({ value: r.name, label: `${r.book_title} (${r.qty - (r.returned_qty || 0) - (r.lost_qty || 0)} out)` })) },
					{ fieldname: "qty", fieldtype: "Int", label: __("Copies"), reqd: 1, default: 1 },
				],
				primary_action_label: label,
				primary_action(values) {
					dialog.hide();
					frm.call(method, values).then(() => frm.reload_doc());
				},
			});
			dialog.show();
		};
		frm.add_custom_button(__("Return Copies"), () => ask("return_copies", __("Return Copies")));
		frm.add_custom_button(__("Mark Lost"), () => ask("mark_lost", __("Mark Lost")));
	},
});
