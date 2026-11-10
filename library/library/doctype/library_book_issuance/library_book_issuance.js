// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Book Issuance", {
	setup(frm) {
		// The issuance cancels its own Sales Invoice and Stock Entry.
		frm.ignore_doctypes_on_cancel_all = ["Sales Invoice", "Stock Entry"];
		frm.set_query("member", () => ({
			filters: { reference_doctype: "Student", membership_status: "Active" },
		}));
		frm.set_query("book", "items", () => ({ filters: { book_type: "Issue" } }));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.sales_invoice) {
			frm.add_custom_button(__("Sales Invoice"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("View"));
		}
		if (frm.doc.docstatus === 1 && frm.doc.stock_entry) {
			frm.add_custom_button(__("Stock Entry"), () => frappe.set_route("Form", "Stock Entry", frm.doc.stock_entry), __("View"));
		}
	},
	scan_barcode(frm) {
		const code = (frm.doc.scan_barcode || "").trim();
		if (!code) return;
		frappe.call({
			method: "library.api.scan.resolve",
			args: { code },
			callback(r) {
				frm.set_value("scan_barcode", "");
				const book = r.message;
				if (!book) {
					frappe.show_alert({ message: __("No book found for {0}", [code]), indicator: "red" });
					return;
				}
				if (book.book_type !== "Issue") {
					frappe.show_alert({ message: __("{0} is a lending book", [book.book_title]), indicator: "orange" });
					return;
				}
				const row = (frm.doc.items || []).find((d) => d.book === book.name);
				if (row) {
					frappe.model.set_value(row.doctype, row.name, "qty", (row.qty || 0) + 1);
				} else {
					const added = frm.add_child("items", { book: book.name, qty: 1 });
					frappe.model.set_value(added.doctype, added.name, "book", book.name);
				}
				frm.refresh_field("items");
				frappe.show_alert({ message: __("Added {0}", [book.book_title]), indicator: "green" });
			},
		});
	},
});
