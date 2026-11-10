"""Phase 6: the script reports and the templated reminders."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from library.library import notifications
from library.tests.test_issuance import IssuanceTestCase
from library.tests.utils import LibraryTestCase, circulate, days_ago, make_book, make_copy, make_issuance, make_member, set_settings


def run(report, **filters):
	module = frappe.scrub(report)
	columns, data = frappe.get_attr(f"library.library.report.{module}.{module}.execute")(frappe._dict(filters))
	return [c["fieldname"] for c in columns], data


class TestReports(IssuanceTestCase):
	def setUp(self):
		super().setUp()
		self.issuance = make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 1)])

	def test_student_statement_shows_billed_and_free_books(self):
		_, rows = run("Student Library Statement", student=self.sm.student)
		mine = [(r["entry"], r["detail"], r["qty"], r["amount"]) for r in rows if r["document"] == self.issuance.name]
		self.assertEqual(sorted(mine), sorted([("Issued, billed", "_Test Maths Textbook", 2, 80), ("Issued, free", "_Test Exercise Book", 1, 0)]))
		self.assertEqual(run("Student Library Statement")[1], [])  # no student: nothing

	def test_issuance_register_filters_billed_and_free(self):
		_, billed = run("Library Issuance Register", student=self.sm.student, billing="Billed")
		_, free = run("Library Issuance Register", student=self.sm.student, billing="Free")
		self.assertEqual([(r["book_title"], r["amount"], r["sales_invoice"]) for r in billed if r["issuance"] == self.issuance.name],
			[("_Test Maths Textbook", 80, self.issuance.sales_invoice)])
		self.assertEqual([r["book_title"] for r in free if r["issuance"] == self.issuance.name], ["_Test Exercise Book"])

	def test_billed_items_by_class_totals(self):
		_, rows = run("Library Billed Items by Class", academic_year=self.issuance.academic_year)
		klass = self.issuance.student_batch or "No class"
		row = next(r for r in rows if r["student_batch"] == klass and r["book_title"] == "_Test Maths Textbook")
		self.assertEqual((row["qty"], row["amount"]), (2, 80))

	def test_stock_balance_shows_the_library_warehouse(self):
		_, rows = run("Library Stock Balance", book_type="Issue")
		by_book = {r["book"]: r["warehouse_qty"] for r in rows}
		self.assertEqual((by_book[self.billed.name], by_book[self.free.name]), (3, 3))


class TestOverdueReportAndReminders(LibraryTestCase):
	def setUp(self):
		super().setUp()
		self.member = make_member(email="reader@example.com").name
		self.book = make_book("_Test Reminder Book").name

	def test_overdue_loans_report(self):
		issue = circulate("Issue", self.member, make_copy(self.book).name, transaction_date=days_ago(10))
		_, rows = run("Library Overdue Loans")
		row = next(r for r in rows if r["name"] == issue.name)
		self.assertEqual((row["days_overdue"], row["email"]), (3, "reader@example.com"))

	def test_due_date_reminder_uses_the_template_and_falls_back_without_it(self):
		set_settings(send_due_date_reminders=1, due_date_reminder_days=2)
		notifications.ensure_email_templates()
		circulate("Issue", self.member, make_copy(self.book).name, due_date=add_days(today(), 2))
		frappe.db.set_value("Email Template", "Library Due Date Reminder", "subject", "EDITED {{ book_title }}")
		with patch("frappe.sendmail") as sendmail:
			notifications.send_due_date_reminders()
		mine = [c.kwargs for c in sendmail.call_args_list if c.kwargs["recipients"] == ["reader@example.com"]]
		self.assertEqual([m["subject"] for m in mine], ["EDITED _Test Reminder Book"])

		frappe.delete_doc("Email Template", "Library Due Date Reminder", force=True)
		with patch("frappe.sendmail") as sendmail:
			notifications.send_due_date_reminders()
		mine = [c.kwargs for c in sendmail.call_args_list if c.kwargs["recipients"] == ["reader@example.com"]]
		self.assertTrue(mine and mine[0]["subject"].startswith("Library book due on"), mine)

	def test_templates_are_created_once_and_never_overwritten(self):
		notifications.ensure_email_templates()
		frappe.db.set_value("Email Template", "Library Overdue Reminder", "subject", "Ours")
		notifications.ensure_email_templates()
		self.assertEqual(frappe.db.get_value("Email Template", "Library Overdue Reminder", "subject"), "Ours")
