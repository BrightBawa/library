"""Phase 7: issuance returns, stock counts, class set loans and clearance."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, flt, today

from library.api import bulk
from library.library import clearance
from library.library.api import dashboard
from library.library.doctype.library_class_set_loan.library_class_set_loan import refresh_statuses
from library.library.doctype.library_stock_count.library_stock_count import scan_copy
from library.library.notifications import send_overdue_reminders
from library.library.stock import warehouse_qty
from library.tests.test_issuance import IssuanceTestCase
from library.tests.test_member_sync import _changed
from library.tests.utils import (
	LibraryTestCase,
	circulate,
	days_ago,
	make_book,
	make_copy,
	make_issuance,
	make_member,
	make_user,
	set_settings,
)


def make_return(issuance, quantities, submit=True, reason="Unused"):
	rows = [{"issuance_item": r.name, "qty": quantities[r.book]} for r in issuance.items if r.book in quantities]
	doc = frappe.get_doc({"doctype": "Library Issuance Return", "against_issuance": issuance.name, "reason": reason,
		"items": rows}).insert()
	if submit:
		doc.submit()
	return doc


class TestIssuanceReturn(IssuanceTestCase):
	def test_billed_books_are_credited_and_free_books_received_back(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 2)])
		ret = make_return(issuance, {self.billed.name: 1, self.free.name: 1})
		credit = frappe.get_doc("Sales Invoice", ret.sales_invoice_return)
		self.assertEqual((credit.docstatus, credit.is_return, credit.return_against, flt(credit.grand_total)),
			(1, 1, issuance.sales_invoice, -40))
		self.assertEqual((credit.library_issuance, credit.library_document), (issuance.name, ret.name))
		self.assertFalse(credit.get("student"))
		receipt = frappe.get_doc("Stock Entry", ret.stock_entry)
		self.assertEqual((receipt.purpose, [(i.item_code, i.qty, i.t_warehouse) for i in receipt.items]),
			("Material Receipt", [(self.free.item, 1, self.s.library_warehouse)]))
		self.assertEqual((warehouse_qty(self.billed.item), warehouse_qty(self.free.item)), (4, 3))
		returned = {r.book: r.returned_qty for r in frappe.get_doc("Library Book Issuance", issuance.name).items}
		self.assertEqual(returned, {self.billed.name: 1, self.free.name: 1})

		with self.assertRaisesRegex(frappe.ValidationError, "at most 1"):
			make_return(issuance, {self.billed.name: 2}, submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, "Cancel Library Issuance Return"):
			frappe.get_doc("Library Book Issuance", issuance.name).cancel()

		ret.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", ret.sales_invoice_return, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Stock Entry", ret.stock_entry, "docstatus"), 2)
		self.assertEqual((warehouse_qty(self.billed.item), warehouse_qty(self.free.item)), (3, 2))
		returned = {r.book: r.returned_qty for r in frappe.get_doc("Library Book Issuance", issuance.name).items}
		self.assertEqual(returned, {self.billed.name: 0, self.free.name: 0})

	def test_only_a_library_manager_approves_a_return(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 1)])
		frappe.set_user(make_user("library-test-librarian@example.com", "Librarian"))
		draft = make_return(issuance, {self.billed.name: 1}, submit=False)
		with self.assertRaisesRegex(frappe.PermissionError, "Library Manager"):
			draft.submit()


class TestStockCount(IssuanceTestCase):
	def test_count_reconciles_the_warehouse_and_marks_missing_copies_lost(self):
		lending = make_book("_Test Counted Novel").name
		found, missing = make_copy(lending, barcode="LIBCOUNT1").name, make_copy(lending).name
		count = frappe.get_doc({"doctype": "Library Stock Count"}).insert()
		count.load_books()
		count.reload()
		row = next(r for r in count.items if r.book == self.billed.name)
		self.assertEqual(row.system_qty, 5)
		row.counted_qty = 3
		count.save()
		self.assertEqual(scan_copy(count.name, "LIBCOUNT1"), found)
		count.reload()
		count.submit()
		self.assertEqual(warehouse_qty(self.billed.item), 3)
		reconciliation = frappe.get_doc("Stock Reconciliation", count.stock_reconciliation)
		self.assertEqual((reconciliation.docstatus, reconciliation.library_document), (1, count.name))
		self.assertEqual(frappe.db.get_value("Library Book Copy", missing, "status"), "Lost")
		self.assertEqual(frappe.db.get_value("Library Book Copy", found, "status"), "Available")

		count.cancel()
		self.assertEqual(warehouse_qty(self.billed.item), 5)
		self.assertEqual(frappe.db.get_value("Library Book Copy", missing, "status"), "Available")


class TestClassSetLoan(LibraryTestCase):
	def setUp(self):
		super().setUp()
		employee = frappe.db.get_value("Employee", {"status": "Active"})
		frappe.db.delete("Library Member", {"employee": employee})
		self.teacher = make_member("_Test Teacher", reference_doctype="Employee", employee=employee,
			email="teacher@example.com").name
		self.book = make_book("_Test Class Reader").name
		self.copies = [make_copy(self.book).name for _ in range(4)]

	def loan(self, qty, **values):
		return frappe.get_doc({"doctype": "Library Class Set Loan", "teacher": self.teacher,
			"due_date": add_days(today(), 14), "items": [{"book": self.book, "qty": qty}], **values}).insert()

	def test_copies_are_allocated_returned_in_parts_and_lost(self):
		before = dashboard.copies_on_loan()["value"]
		loan = self.loan(3)
		loan.submit()
		loan.reload()
		self.assertEqual((loan.status, len(loan.copies)), ("Open", 3))
		self.assertEqual(dashboard.copies_on_loan()["value"] - before, 3)
		row = loan.items[0].name
		loan.return_copies(row, qty=2)
		loan.reload()
		self.assertEqual((loan.status, loan.items[0].returned_qty), ("Partly Returned", 2))
		with self.assertRaisesRegex(frappe.ValidationError, "cancelling"):
			loan.cancel()
		loan.mark_lost(row, qty=1)
		loan.reload()
		self.assertEqual((loan.status, loan.items[0].lost_qty), ("Closed", 1))
		self.assertEqual(sorted(frappe.db.get_value("Library Book Copy", c.copy, "status") for c in loan.copies),
			["Available", "Available", "Lost"])

	def test_shelf_availability_teachers_only_and_cancel(self):
		with self.assertRaisesRegex(frappe.ValidationError, "on the shelf"):
			self.loan(5).submit()
		with self.assertRaisesRegex(frappe.ValidationError, "teachers"):
			frappe.get_doc({"doctype": "Library Class Set Loan", "teacher": make_member("_Test Pupil").name,
				"due_date": add_days(today(), 7), "items": [{"book": self.book, "qty": 1}]}).insert()
		loan = self.loan(2)
		loan.submit()
		loan.cancel()
		self.assertEqual({frappe.db.get_value("Library Book Copy", c, "status") for c in self.copies}, {"Available"})

	def test_overdue_class_sets_and_the_teacher_reminder(self):
		set_settings(send_overdue_reminders=1, overdue_reminder_days=1)
		loan = self.loan(2, issue_date=days_ago(20), due_date=days_ago(3))
		loan.submit()
		refresh_statuses()
		self.assertEqual(frappe.db.get_value("Library Class Set Loan", loan.name, "status"), "Overdue")
		with patch("frappe.sendmail") as sendmail:
			send_overdue_reminders()
		self.assertIn(["teacher@example.com"], [c.kwargs["recipients"] for c in sendmail.call_args_list])


class TestClearance(LibraryTestCase):
	def setUp(self):
		super().setUp()
		self.student = frappe.db.get_value("Student", {"enabled": 1})
		frappe.db.delete("Library Member", {"student": self.student})
		self.member = make_member("_Test Leaver", reference_doctype="Student", student=self.student).name

	def test_cleared_until_something_is_outstanding(self):
		doc = frappe.get_doc({"doctype": "Library Clearance", "student": self.student}).insert()
		self.assertEqual((doc.status, doc.items), ("Cleared", []))
		book = make_book("_Test Unreturned").name
		circulate("Issue", self.member, make_copy(book).name)
		frappe.get_doc({"doctype": "Library Fine", "member": self.member, "fine_type": "Other", "fine_amount": 15}).insert()
		doc.save()
		self.assertEqual(doc.status, "Not Cleared")
		self.assertEqual(sorted(r.check_type for r in doc.items), ["Unpaid Fine", "Unreturned Loan"])
		self.assertEqual(doc.total_owed, 15)
		doc.submit()
		self.assertEqual(dashboard.uncleared_students()["value"] >= 1, True)
		_, rows = frappe.get_attr("library.library.report.library_uncleared_students.library_uncleared_students.execute")({})
		self.assertIn(doc.name, [r["clearance"] for r in rows])

	def test_disabling_students_only_queues_their_clearance(self):
		others = frappe.get_all("Student", filters={"enabled": 1, "name": ["!=", self.student]}, pluck="name", limit=2)
		for other in others:
			frappe.db.delete("Library Member", {"student": other})
			make_member(f"_Test Leaver {other}", reference_doctype="Student", student=other)
		with patch("frappe.enqueue") as enqueue:
			for name in [self.student, *others]:
				clearance.on_student_update(_changed(frappe.get_doc("Student", name), enabled=0))
		jobs = [(c.args[0], c.kwargs["student"], c.kwargs["job_id"]) for c in enqueue.call_args_list]
		self.assertEqual(jobs, [("library.library.clearance.run_student_clearance", s, f"library-clearance-{s}")
			for s in [self.student, *others]])
		self.assertFalse(frappe.db.exists("Library Clearance", {"student": self.student}))  # nothing done in the save

	def test_the_job_records_the_clearance_and_one_digest_reaches_the_managers(self):
		manager = make_user("library-test-manager@example.com", "Library Manager")
		circulate("Issue", self.member, make_copy(make_book("_Test Kept Book").name).name)
		frappe.db.set_value("Student", self.student, "enabled", 0)
		with patch("frappe.enqueue") as enqueue:
			name = clearance.run_student_clearance(self.student)
		doc = frappe.get_doc("Library Clearance", name)
		self.assertEqual((doc.docstatus, doc.status, doc.automatic), (1, "Not Cleared", 1))
		self.assertEqual([c.args[0] for c in enqueue.call_args_list], ["library.library.clearance.send_clearance_digest"])

		with patch("frappe.sendmail") as sendmail:
			self.assertGreaterEqual(clearance.send_clearance_digest(), 1)
		self.assertEqual(len(sendmail.call_args_list), 1)
		self.assertIn(manager, sendmail.call_args.kwargs["recipients"])
		self.assertIn(name, sendmail.call_args.kwargs["message"])
		self.assertEqual(frappe.db.get_value("Library Clearance", name, "managers_notified"), 1)
		with patch("frappe.sendmail") as sendmail:
			clearance.send_clearance_digest()
		self.assertNotIn(name, " ".join(c.kwargs["message"] for c in sendmail.call_args_list))

	def test_a_student_enabled_again_before_the_job_runs_is_skipped(self):
		self.assertIsNone(clearance.run_student_clearance(self.student))  # still enabled

	def test_bulk_clearance(self):
		doc = frappe.get_doc({"doctype": "Library Bulk Clearance",
			"student_batch": frappe.db.get_value("Student Batch Name", {})}).insert()
		with patch("library.library.doctype.library_bulk_clearance.library_bulk_clearance.LibraryBulkClearance.get_students",
				return_value=[self.student]):
			counts = bulk.run_bulk_clearance(doc.name, user="Administrator", commit_every=0)
		self.assertEqual(counts, {"Cleared": 1, "Not Cleared": 0, "Failed": 0})
		doc.reload()
		self.assertEqual((doc.status, doc.results[0].status), ("Completed", "Cleared"))
