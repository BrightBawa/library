// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Bulk Clearance", {
	refresh(frm) {
		if (!frm.is_new() && ["Draft", "Completed with Errors"].includes(frm.doc.status)) {
			frm.add_custom_button(frm.doc.status === "Draft" ? __("Check Students") : __("Retry Failed"), () => {
				frm.call("start").then((r) => {
					frappe.show_alert({ message: __("Queued for {0} students", [r.message]), indicator: "blue" });
					frm.reload_doc();
				});
			}).addClass("btn-primary");
		}
		frappe.realtime.off("library_bulk_progress");
		frappe.realtime.on("library_bulk_progress", (data) => {
			if (data.name !== frm.doc.name) return;
			frm.dashboard.show_progress(__("Checking"), (data.done / data.total) * 100, `${data.done} / ${data.total}`);
			if (data.finished) {
				frm.dashboard.hide_progress();
				frm.reload_doc();
			}
		});
	},
});
