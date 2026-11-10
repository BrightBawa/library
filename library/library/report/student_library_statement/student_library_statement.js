// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.query_reports["Student Library Statement"] = {
	filters: [
		{ fieldname: "student", label: __("Student"), fieldtype: "Link", options: "Student", reqd: 1 },
		{ fieldname: "academic_year", label: __("Academic Year"), fieldtype: "Link", options: "Academic Year" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
};
