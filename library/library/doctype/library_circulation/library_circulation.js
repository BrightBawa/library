// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.ui.form.on("Library Circulation", {
	transaction_type(frm) {
		frm.trigger("fill_from_open_issue");
	},
	book_copy(frm) {
		frm.trigger("fill_from_open_issue");
	},
	fill_from_open_issue(frm) {
		// A Return or Renew applies to the copy's open Issue: show whose loan it is.
		if (frm.doc.docstatus !== 0 || frm.doc.transaction_type === "Issue" || !frm.doc.book_copy) {
			return;
		}
		frappe.call({
			method: "library.library.doctype.library_circulation.library_circulation.get_open_issue",
			args: { book_copy: frm.doc.book_copy },
			callback(r) {
				if (!r.message) {
					frappe.msgprint(__("Copy {0} is not on loan.", [frm.doc.book_copy]));
					return;
				}
				frm.set_value("member", r.message.member);
				frm.set_value("against_issue", r.message.name);
				frm.set_value("issue_date", r.message.issue_date);
			},
		});
	},
});
