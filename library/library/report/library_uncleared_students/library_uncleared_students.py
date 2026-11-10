# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from library.library import school
from library.library.api.dashboard import latest_clearances


def execute(filters=None):
	filters = frappe._dict(filters or {})
	students = None
	if filters.student_group:
		students = set(school.students_in_group(filters.student_group))
	elif filters.student_batch:
		students = set(school.students_in_batch(filters.student_batch, filters.academic_year))
	data = []
	for latest in latest_clearances():
		if latest.status != "Not Cleared" or (students is not None and latest.student not in students):
			continue
		doc = frappe.get_doc("Library Clearance", latest.name)
		if filters.academic_year and doc.academic_year != filters.academic_year:
			continue
		kinds = {}
		for row in doc.items:
			kinds[row.check_type] = kinds.get(row.check_type, 0) + 1
		data.append({"student": doc.student, "student_name": doc.student_name, "student_batch": doc.student_batch,
			"clearance": doc.name, "clearance_date": doc.clearance_date, "loans": kinds.get("Unreturned Loan", 0),
			"fines": kinds.get("Unpaid Fine", 0), "reservations": kinds.get("Active Reservation", 0),
			"total_owed": doc.total_owed})
	data.sort(key=lambda r: (r["student_batch"] or "", r["student_name"] or ""))
	return columns(), data


def columns():
	return [
		{"fieldname": "student", "label": _("Student"), "fieldtype": "Link", "options": "Student", "width": 100},
		{"fieldname": "student_name", "label": _("Student Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "student_batch", "label": _("Class"), "fieldtype": "Data", "width": 70},
		{"fieldname": "clearance", "label": _("Clearance"), "fieldtype": "Link", "options": "Library Clearance", "width": 140},
		{"fieldname": "clearance_date", "label": _("Checked"), "fieldtype": "Date", "width": 95},
		{"fieldname": "loans", "label": _("Unreturned Loans"), "fieldtype": "Int", "width": 120},
		{"fieldname": "fines", "label": _("Unpaid Fines"), "fieldtype": "Int", "width": 100},
		{"fieldname": "reservations", "label": _("Reservations"), "fieldtype": "Int", "width": 100},
		{"fieldname": "total_owed", "label": _("Total Owed"), "fieldtype": "Currency", "width": 110},
	]
