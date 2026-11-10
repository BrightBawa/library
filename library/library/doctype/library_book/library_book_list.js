// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.listview_settings["Library Book"] = {
	add_fields: ["book_type", "is_billable", "book_status"],
	get_indicator(doc) {
		if (doc.book_type === "Issue") {
			return doc.is_billable
				? [__("Billed"), "blue", "book_type,=,Issue|is_billable,=,1"]
				: [__("Free"), "green", "book_type,=,Issue|is_billable,=,0"];
		}
		const colour = { Available: "green", "All Issued": "orange", "Out of Stock": "red" }[doc.book_status];
		return [__(doc.book_status || "Lending"), colour || "gray", `book_status,=,${doc.book_status}`];
	},
	onload(listview) {
		listview.page.add_actions_menu_item(__("Request Stock from Stores"), () => {
			const books = listview.get_checked_items(true);
			if (!books.length) {
				frappe.msgprint(__("Select the Issue-type books to request."));
				return;
			}
			frappe.call({
				method: "library.library.stock.make_stock_request",
				args: { books },
				callback(r) {
					if (r.message) {
						const doc = frappe.model.sync(r.message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					}
				},
			});
		});
	},
};
