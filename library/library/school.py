"""School data the library reads: academic year and term, a student's class, class lists.

Standard Education records come first (Education Settings, Student Group, Program
Enrollment). A site's own Student.custom_class is read only if that field exists, so the
library does not depend on any other app.
"""

import frappe
from frappe.utils import getdate, today


def current_academic_year():
	year = frappe.db.get_single_value("Education Settings", "current_academic_year")
	if year:
		return year
	return frappe.db.get_value("Academic Year",
		{"year_start_date": ["<=", today()], "year_end_date": [">=", today()]}, "name")


def current_academic_term():
	term = frappe.db.get_single_value("Education Settings", "current_academic_term")
	if term:
		return frappe.db.get_value("Academic Term", term, ["name", "term_start_date", "term_end_date"], as_dict=True)
	return frappe.db.get_value("Academic Term",
		{"term_start_date": ["<=", today()], "term_end_date": [">=", today()]},
		["name", "term_start_date", "term_end_date"], as_dict=True)


def _has_custom_class():
	return frappe.get_meta("Student").has_field("custom_class")


def student_batch(student, academic_year=None):
	"""The student's class: a Batch-based Student Group, then a Program Enrollment, then custom_class."""
	if not student:
		return None
	year_clause = "and sg.academic_year = %(year)s" if academic_year else ""
	batch = frappe.db.sql(f"""
		select sg.batch from `tabStudent Group` sg
		join `tabStudent Group Student` sgs on sgs.parent = sg.name
		where sgs.student = %(student)s and sgs.active = 1 and sg.disabled = 0
			and sg.group_based_on = 'Batch' and ifnull(sg.batch, '') != '' {year_clause}
		order by sg.modified desc limit 1
	""", {"student": student, "year": academic_year})
	if batch:
		return batch[0][0]
	filters = {"student": student, "docstatus": 1, "student_batch_name": ["is", "set"]}
	if academic_year:
		filters["academic_year"] = academic_year
	batch = frappe.db.get_value("Program Enrollment", filters, "student_batch_name", order_by="enrollment_date desc")
	if batch:
		return batch
	return frappe.db.get_value("Student", student, "custom_class") if _has_custom_class() else None


def students_in_group(student_group):
	return frappe.get_all("Student Group Student",
		filters={"parent": student_group, "parenttype": "Student Group", "active": 1},
		pluck="student", order_by="group_roll_number asc, idx asc")


def students_in_batch(batch, academic_year=None):
	"""Enabled students of a class from every source, in name order."""
	students = set()
	group_filters = {"batch": batch, "group_based_on": "Batch", "disabled": 0}
	if academic_year:
		group_filters["academic_year"] = academic_year
	for group in frappe.get_all("Student Group", filters=group_filters, pluck="name"):
		students.update(students_in_group(group))
	enrollment_filters = {"student_batch_name": batch, "docstatus": 1}
	if academic_year:
		enrollment_filters["academic_year"] = academic_year
	students.update(frappe.get_all("Program Enrollment", filters=enrollment_filters, pluck="student"))
	if _has_custom_class():
		students.update(frappe.get_all("Student", filters={"custom_class": batch, "enabled": 1}, pluck="name"))
	if not students:
		return []
	return frappe.get_all("Student", filters={"name": ["in", list(students)], "enabled": 1}, pluck="name", order_by="name")


def in_term(date, term):
	return term and getdate(term.term_start_date) <= getdate(date) <= getdate(term.term_end_date)
