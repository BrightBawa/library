# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def auto_create_library_member_from_student(doc, method):
	"""Auto create library member when a new student is created"""
	settings = frappe.get_single("Library Settings")
	
	if not settings.auto_create_members_from_students:
		return
	
	# Check if member already exists
	existing = frappe.db.exists("Library Member", {
		"reference_doctype": "Student",
		"student": doc.name
	})
	
	if existing:
		return
	
	try:
		member = frappe.get_doc({
			"doctype": "Library Member",
			"full_name": doc.student_name,
			"email": doc.student_email_id,
			"phone": doc.student_mobile_number,
			"membership_type": settings.student_membership_type or get_default_membership_type(),
			"reference_doctype": "Student",
			"student": doc.name
		})
		member.insert(ignore_permissions=True)
		frappe.msgprint(_("Library Member {0} created automatically").format(member.name), 
			alert=True, indicator="green")
	except Exception as e:
		frappe.log_error(f"Error auto-creating member for student {doc.name}: {str(e)}")


def auto_create_library_member_from_employee(doc, method):
	"""Auto create library member when a new employee is created"""
	settings = frappe.get_single("Library Settings")
	
	if not settings.auto_create_members_from_employees:
		return
	
	# Check if member already exists
	existing = frappe.db.exists("Library Member", {
		"reference_doctype": "Employee",
		"employee": doc.name
	})
	
	if existing:
		return
	
	try:
		member = frappe.get_doc({
			"doctype": "Library Member",
			"full_name": doc.employee_name,
			"email": doc.personal_email,
			"phone": doc.cell_number,
			"membership_type": settings.employee_membership_type or get_default_membership_type(),
			"reference_doctype": "Employee",
			"employee": doc.name
		})
		member.insert(ignore_permissions=True)
		frappe.msgprint(_("Library Member {0} created automatically").format(member.name),
			alert=True, indicator="green")
	except Exception as e:
		frappe.log_error(f"Error auto-creating member for employee {doc.name}: {str(e)}")


def get_default_membership_type():
	"""Get the first available membership type"""
	membership_type = frappe.db.get_value("Library Membership Type", {}, "name")
	return membership_type or "Standard"
