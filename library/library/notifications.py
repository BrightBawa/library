"""Library email reminders, worded by Email Templates that the library can edit.

The templates are created once if missing and never overwritten. If one is deleted or
cannot be rendered, the built-in wording below is used, so a reminder is never lost.
Template context: member_name, book_title, book_copy, due_date, days_overdue, qty,
document (the loan's name).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, formatdate, today

from library.library.stats import OPEN_LOAN

TEMPLATES = {
	"Library Due Date Reminder": {
		"subject": "Library book due on {{ due_date }}: {{ book_title }}",
		"response_html": (
			"<p>Dear {{ member_name }},</p>"
			"<p><strong>{{ book_title }}</strong>{% if book_copy %} (copy {{ book_copy }}){% endif %}"
			"{% if qty and qty > 1 %} &times; {{ qty }}{% endif %} is due back at the library on "
			"<strong>{{ due_date }}</strong>. Please return or renew it by then.</p><p>Library</p>"
		),
	},
	"Library Overdue Reminder": {
		"subject": "Overdue library book: {{ book_title }}",
		"response_html": (
			"<p>Dear {{ member_name }},</p>"
			"<p><strong>{{ book_title }}</strong>{% if book_copy %} (copy {{ book_copy }}){% endif %}"
			"{% if qty and qty > 1 %} &times; {{ qty }}{% endif %} was due on {{ due_date }} and is now "
			"<strong>{{ days_overdue }} days overdue</strong>. Please return it to the library as soon as possible.</p>"
			"<p>Library</p>"
		),
	},
}


def ensure_email_templates():
	"""after_install / after_migrate: create the library's Email Templates if they are missing."""
	for name, values in TEMPLATES.items():
		if not frappe.db.exists("Email Template", name):
			frappe.get_doc({"doctype": "Email Template", "name": name, "subject": values["subject"],
				"use_html": 1, "response_html": values["response_html"]}).insert(ignore_permissions=True)


def render(template_name, context):
	"""(subject, message) from the Email Template, or from the built-in wording."""
	builtin = TEMPLATES[template_name]
	template = frappe.db.get_value("Email Template", template_name,
		["subject", "use_html", "response_html", "response"], as_dict=True)
	if template:
		try:
			body = template.response_html if template.use_html else template.response
			return frappe.render_template(template.subject, context), frappe.render_template(body, context)
		except Exception:
			frappe.log_error(title=f"Library email template {template_name} could not be rendered; built-in wording used")
	return frappe.render_template(builtin["subject"], context), frappe.render_template(builtin["response_html"], context)


def member_email(member):
	"""The member's email, else the Student's or Employee's."""
	values = frappe.db.get_value("Library Member", member, ["email", "student", "employee"], as_dict=True)
	if not values:
		return None
	if values.email:
		return values.email
	if values.student:
		return frappe.db.get_value("Student", values.student, "student_email_id")
	if values.employee:
		employee = frappe.db.get_value("Employee", values.employee, ["company_email", "personal_email"], as_dict=True)
		return employee and (employee.company_email or employee.personal_email)
	return None


def send(template_name, recipient, context, reference_doctype, reference_name):
	subject, message = render(template_name, context)
	frappe.sendmail(recipients=[recipient], subject=subject, message=message,
		reference_doctype=reference_doctype, reference_name=reference_name)


def _loan_context(member_name, book_title, due_date, book_copy=None, qty=1, document=None):
	return {"member_name": member_name, "book_title": book_title, "book_copy": book_copy, "qty": qty,
		"due_date": formatdate(due_date), "days_overdue": max(date_diff(today(), due_date), 0), "document": document}


def _class_set_lines(filters_sql, values):
	if not frappe.db.exists("DocType", "Library Class Set Loan"):
		return []
	return frappe.db.sql(f"""
		select l.name, l.teacher, l.teacher_name, l.due_date, i.book_title,
			i.qty - ifnull(i.returned_qty, 0) - ifnull(i.lost_qty, 0) qty
		from `tabLibrary Class Set Loan` l join `tabLibrary Class Set Loan Item` i on i.parent = l.name
		where l.docstatus = 1 and i.qty - ifnull(i.returned_qty, 0) - ifnull(i.lost_qty, 0) > 0 {filters_sql}""",
		values, as_dict=True)


def send_due_date_reminders():
	"""Daily: remind members whose loan is due in `due_date_reminder_days` days (loans and class sets)."""
	if not cint(frappe.db.get_single_value("Library Settings", "send_due_date_reminders")):
		return 0
	due = add_days(today(), cint(frappe.db.get_single_value("Library Settings", "due_date_reminder_days")) or 2)
	sent = 0
	for loan in frappe.get_all("Library Circulation", filters=dict(OPEN_LOAN, due_date=due),
			fields=["name", "member", "member_name", "book_title", "book_copy", "due_date"]):
		email = member_email(loan.member)
		if email:
			send("Library Due Date Reminder", email, _loan_context(loan.member_name, loan.book_title, loan.due_date,
				loan.book_copy, document=loan.name), "Library Circulation", loan.name)
			sent += 1
	for line in _class_set_lines("and l.due_date = %(due)s", {"due": due}):
		email = member_email(line.teacher)
		if email:
			send("Library Due Date Reminder", email, _loan_context(line.teacher_name, line.book_title, line.due_date,
				qty=line.qty, document=line.name), "Library Class Set Loan", line.name)
			sent += 1
	return sent


def send_overdue_reminders():
	"""Daily: remind members whose loan is at least `overdue_reminder_days` overdue (loans and class sets)."""
	if not cint(frappe.db.get_single_value("Library Settings", "send_overdue_reminders")):
		return 0
	after = cint(frappe.db.get_single_value("Library Settings", "overdue_reminder_days")) or 1
	cutoff = add_days(today(), -after)
	sent = 0
	for loan in frappe.get_all("Library Circulation", filters=dict(OPEN_LOAN, due_date=["<=", cutoff]),
			fields=["name", "member", "member_name", "book_title", "book_copy", "due_date"]):
		email = member_email(loan.member)
		if email:
			send("Library Overdue Reminder", email, _loan_context(loan.member_name, loan.book_title, loan.due_date,
				loan.book_copy, document=loan.name), "Library Circulation", loan.name)
			sent += 1
	for line in _class_set_lines("and l.due_date <= %(cutoff)s", {"cutoff": cutoff}):
		email = member_email(line.teacher)
		if email:
			send("Library Overdue Reminder", email, _loan_context(line.teacher_name, line.book_title, line.due_date,
				qty=line.qty, document=line.name), "Library Class Set Loan", line.name)
			sent += 1
	return sent
