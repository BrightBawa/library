"""
Library Member Integration API
Handles auto-creation of library members from Students and Employees
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, get_datetime


def create_library_member_from_student(doc, method):
"""
Auto-create library member when a student is created
Called via hooks on Student after_insert
"""
try:
# Check if library member already exists
existing = frappe.db.exists("Library Member", {
"student": doc.name
})

if existing:
frappe.logger().info(f"Library member already exists for student {doc.name}")
return

# Get membership type for students
membership_type = frappe.db.get_value(
"Library Membership Type",
{"membership_type": "Student"},
"name"
)

if not membership_type:
frappe.log_error(
f"No membership type found for 'Student'. Cannot create library member for {doc.name}",
"Library Member Creation Failed"
)
return

membership_type_doc = frappe.get_doc("Library Membership Type", membership_type)

# Calculate membership end date
membership_end_date = add_days(today(), 365)  # 1 year membership

# Create library member
member = frappe.get_doc({
"doctype": "Library Member",
"member_type": "Student",
"student": doc.name,
"full_name": doc.student_name,
"email": doc.student_email_id,
"phone": doc.student_mobile_number,
"membership_type": membership_type,
"membership_status": "Active",
"membership_start_date": today(),
"membership_end_date": membership_end_date,
"max_books_allowed": membership_type_doc.max_books_allowed,
"books_issued": 0,
"total_books_borrowed": 0,
"overdue_books": 0,
"outstanding_balance": 0
})

member.insert(ignore_permissions=True)

frappe.logger().info(f"Library member {member.name} created for student {doc.name}")

except Exception as e:
frappe.log_error(
f"Error creating library member for student {doc.name}: {str(e)}",
"Library Member Creation Failed"
)


def create_library_member_from_employee(doc, method):
"""
Auto-create library member when an employee is created
Called via hooks on Employee after_insert
"""
try:
# Check if library member already exists
existing = frappe.db.exists("Library Member", {
"employee": doc.name
})

if existing:
frappe.logger().info(f"Library member already exists for employee {doc.name}")
return

# Determine membership type based on department/designation
# Faculty = Teaching staff, Staff = Non-teaching staff
employee_group = doc.employee_group or "Staff"

if "faculty" in employee_group.lower() or "teacher" in employee_group.lower():
membership_type_filter = "Faculty"
else:
membership_type_filter = "Non-Teaching Staff"

membership_type = frappe.db.get_value(
"Library Membership Type",
{"membership_type": membership_type_filter},
"name"
)

if not membership_type:
# Fallback to generic Staff
membership_type = frappe.db.get_value(
"Library Membership Type",
{"membership_type": "Staff"},
"name"
)

if not membership_type:
frappe.log_error(
f"No membership type found for employees. Cannot create library member for {doc.name}",
"Library Member Creation Failed"
)
return

membership_type_doc = frappe.get_doc("Library Membership Type", membership_type)

# Calculate membership end date (usually tied to employment)
membership_end_date = add_days(today(), 365)  # 1 year membership

# Create library member
member = frappe.get_doc({
"doctype": "Library Member",
"member_type": "Employee",
"employee": doc.name,
"full_name": doc.employee_name,
"email": doc.personal_email or doc.company_email,
"phone": doc.cell_number,
"membership_type": membership_type,
"membership_status": "Active",
"membership_start_date": today(),
"membership_end_date": membership_end_date,
"max_books_allowed": membership_type_doc.max_books_allowed,
"books_issued": 0,
"total_books_borrowed": 0,
"overdue_books": 0,
"outstanding_balance": 0
})

member.insert(ignore_permissions=True)

frappe.logger().info(f"Library member {member.name} created for employee {doc.name}")

except Exception as e:
frappe.log_error(
f"Error creating library member for employee {doc.name}: {str(e)}",
"Library Member Creation Failed"
)


def sync_library_member_status(doc, method):
"""
Sync library member status when student/employee is updated
Called via hooks on Student/Employee on_update
"""
try:
# Determine reference field
if doc.doctype == "Student":
filters = {"student": doc.name}
name_field = "student_name"
email_field = "student_email_id"
phone_field = "student_mobile_number"
status_field = "enabled"
elif doc.doctype == "Employee":
filters = {"employee": doc.name}
name_field = "employee_name"
email_field = "personal_email"
phone_field = "cell_number"
status_field = "status"
else:
return

# Find library member
member_name = frappe.db.get_value("Library Member", filters, "name")

if not member_name:
return

member = frappe.get_doc("Library Member", member_name)

# Update member details
if doc.doctype == "Student":
member.full_name = doc.get(name_field)
member.email = doc.get(email_field)
member.phone = doc.get(phone_field)

# Update status based on enabled field
if hasattr(doc, "enabled"):
if not doc.enabled:
member.membership_status = "Inactive"
elif member.membership_status == "Inactive":
member.membership_status = "Active"

elif doc.doctype == "Employee":
member.full_name = doc.get(name_field)
member.email = doc.get(email_field) or doc.company_email
member.phone = doc.get(phone_field)

# Update status based on employee status
if doc.status == "Active":
if member.membership_status == "Inactive":
member.membership_status = "Active"
elif doc.status in ["Left", "Suspended"]:
member.membership_status = "Inactive"

member.save(ignore_permissions=True)

frappe.logger().info(f"Library member {member.name} synced with {doc.doctype} {doc.name}")

except Exception as e:
frappe.log_error(
f"Error syncing library member for {doc.doctype} {doc.name}: {str(e)}",
"Library Member Sync Failed"
)


@frappe.whitelist()
def get_or_create_library_member(reference_doctype, reference_name):
"""
Get existing library member or create new one
Used for manual linking and API calls

Args:
reference_doctype: "Student" or "Employee"
reference_name: Name of the Student or Employee record

Returns:
Library Member name
"""
if reference_doctype not in ["Student", "Employee"]:
frappe.throw(_("Invalid reference doctype. Must be 'Student' or 'Employee'"))

try:
# Check if library member exists
field_name = reference_doctype.lower()
existing = frappe.db.get_value(
"Library Member",
{field_name: reference_name},
"name"
)

if existing:
return existing

# Get the reference document
ref_doc = frappe.get_doc(reference_doctype, reference_name)

# Create library member using the appropriate function
if reference_doctype == "Student":
create_library_member_from_student(ref_doc, None)
else:
create_library_member_from_employee(ref_doc, None)

# Fetch and return the newly created member
member_name = frappe.db.get_value(
"Library Member",
{field_name: reference_name},
"name"
)

return member_name

except Exception as e:
frappe.log_error(
f"Error in get_or_create_library_member for {reference_doctype} {reference_name}: {str(e)}",
"Library Member Get/Create Failed"
)
frappe.throw(_("Failed to get or create library member: {0}").format(str(e)))
