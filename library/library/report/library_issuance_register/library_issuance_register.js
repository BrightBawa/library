// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.query_reports["Library Issuance Register"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "academic_year", label: __("Academic Year"), fieldtype: "Link", options: "Academic Year" },
		{ fieldname: "student_batch", label: __("Class"), fieldtype: "Link", options: "Student Batch Name" },
		{ fieldname: "student", label: __("Student"), fieldtype: "Link", options: "Student" },
		{ fieldname: "billing", label: __("Billing"), fieldtype: "Select", options: ["", "Billed", "Free"] },
	],
};
