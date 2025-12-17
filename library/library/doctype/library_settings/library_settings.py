# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class LibrarySettings(Document):
	pass


@frappe.whitelist()
def sync_students_and_employees():
	"""Sync all students and employees to library members"""
	settings = frappe.get_single("Library Settings")
	
	students_created = 0
	employees_created = 0
	students_skipped = 0
	employees_skipped = 0
	
	# Sync Students
	if frappe.db.exists("DocType", "Student"):
		students = frappe.get_all("Student", 
			fields=["name", "student_name", "student_email_id", "student_mobile_number"],
			filters={"enabled": 1}
		)
		
		for student in students:
			# Check if member already exists
			existing = frappe.db.exists("Library Member", {
				"reference_doctype": "Student",
				"student": student.name
			})
			
			if not existing:
				try:
					member = frappe.get_doc({
						"doctype": "Library Member",
						"full_name": student.student_name,
						"email": student.student_email_id,
						"phone": student.student_mobile_number,
						"membership_type": settings.student_membership_type or get_default_membership_type(),
						"reference_doctype": "Student",
						"student": student.name
					})
					member.insert(ignore_permissions=True)
					students_created += 1
				except Exception as e:
					frappe.log_error(f"Error creating member for student {student.name}: {str(e)}")
					students_skipped += 1
			else:
				students_skipped += 1
	
	# Sync Employees
	if frappe.db.exists("DocType", "Employee"):
		employees = frappe.get_all("Employee",
			fields=["name", "employee_name", "personal_email", "cell_number"],
			filters={"status": "Active"}
		)
		
		for employee in employees:
			# Check if member already exists
			existing = frappe.db.exists("Library Member", {
				"reference_doctype": "Employee",
				"employee": employee.name
			})
			
			if not existing:
				try:
					member = frappe.get_doc({
						"doctype": "Library Member",
						"full_name": employee.employee_name,
						"email": employee.personal_email,
						"phone": employee.cell_number,
						"membership_type": settings.employee_membership_type or get_default_membership_type(),
						"reference_doctype": "Employee",
						"employee": employee.name
					})
					member.insert(ignore_permissions=True)
					employees_created += 1
				except Exception as e:
					frappe.log_error(f"Error creating member for employee {employee.name}: {str(e)}")
					employees_skipped += 1
			else:
				employees_skipped += 1
	
	frappe.db.commit()
	
	message = f"""
		<b>Sync Complete!</b><br><br>
		<b>Students:</b> {students_created} created, {students_skipped} skipped (already exist)<br>
		<b>Employees:</b> {employees_created} created, {employees_skipped} skipped (already exist)
	"""
	
	frappe.msgprint(message, title="Library Member Sync", indicator="green")
	
	return {
		"students_created": students_created,
		"students_skipped": students_skipped,
		"employees_created": employees_created,
		"employees_skipped": employees_skipped
	}


def get_default_membership_type():
	"""Get the first available membership type"""
	membership_type = frappe.db.get_value("Library Membership Type", {}, "name")
	return membership_type or "Standard"
