// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.query_reports["Library Stock Balance"] = {
	filters: [
		{ fieldname: "book_type", label: __("Book Type"), fieldtype: "Select", options: ["", "Lending", "Issue"] },
		{ fieldname: "category", label: __("Category"), fieldtype: "Link", options: "Library Category" },
	],
};
