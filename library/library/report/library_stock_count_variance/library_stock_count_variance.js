// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.query_reports["Library Stock Count Variance"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "stock_count", label: __("Stock Count"), fieldtype: "Link", options: "Library Stock Count" },
	],
};
