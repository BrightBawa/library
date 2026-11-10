// Copyright (c) 2025, GCIHS and contributors
// For license information, please see license.txt

frappe.query_reports["Library Uncleared Students"] = {
	filters: [
		{ fieldname: "academic_year", label: __("Academic Year"), fieldtype: "Link", options: "Academic Year" },
		{ fieldname: "student_batch", label: __("Class"), fieldtype: "Link", options: "Student Batch Name" },
		{ fieldname: "student_group", label: __("Student Group"), fieldtype: "Link", options: "Student Group" },
	],
};
