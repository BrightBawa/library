// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Clearance", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Check Again"), () => frm.save());
		}
		if (frm.doc.status) {
			frm.dashboard.set_headline_alert(frm.doc.status === "Cleared"
				? `<span class="indicator green">${__("Cleared: nothing outstanding with the library")}</span>`
				: `<span class="indicator red">${__("Not cleared: {0} outstanding", [frm.doc.items.length])}</span>`);
		}
	},
});
