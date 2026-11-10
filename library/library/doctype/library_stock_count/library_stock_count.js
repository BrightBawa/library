// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Stock Count", {
	setup(frm) {
		frm.ignore_doctypes_on_cancel_all = ["Stock Reconciliation"];
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Load Books"), () => {
				frappe.confirm(__("Replace the rows with today's system quantities and shelf copies?"), () =>
					frm.call("load_books").then((r) => {
						frm.reload_doc();
						frappe.show_alert({ message: __("{0} books, {1} copies", [r.message.books, r.message.copies]) });
					})
				);
			});
		}
	},
	scan_barcode(frm) {
		const code = (frm.doc.scan_barcode || "").trim();
		if (!code || frm.is_new()) return;
		frm.set_value("scan_barcode", "");
		frm.save().then(() =>
			frappe.call({
				method: "library.library.doctype.library_stock_count.library_stock_count.scan_copy",
				args: { name: frm.doc.name, code },
				callback(r) {
					frappe.show_alert(r.message
						? { message: __("Found {0}", [r.message]), indicator: "green" }
						: { message: __("{0} is not on this count", [code]), indicator: "red" });
					frm.reload_doc();
				},
			})
		);
	},
});
