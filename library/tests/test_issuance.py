"""Phase 3: book issuance and billing, bulk issue, rentals, fine billing and scanning."""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from library.api import bulk, scan
from library.library import billing
from library.library.stock import warehouse_qty
from library.tests.utils import (
	LibraryTestCase,
	account,
	circulate,
	days_ago,
	make_book,
	make_copy,
	make_issuance,
	make_issue_book,
	make_service_item,
	set_settings,
	set_stock_settings,
	student_member,
)


class IssuanceTestCase(LibraryTestCase):
	def setUp(self):
		super().setUp()
		self.s = set_stock_settings()
		self.sm = student_member()
		self.billed = make_issue_book("_Test Maths Textbook", billable=True, rate=40, stock=5)
		self.free = make_issue_book("_Test Exercise Book", stock=4)


class TestIssuance(IssuanceTestCase):
	def test_billed_lines_are_invoiced_and_free_lines_issued(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 1)])
		self.assertEqual((issuance.total_billable, issuance.total_billable_qty, issuance.total_free), (80, 2, 1))
		self.assertEqual((issuance.student, issuance.customer, issuance.issued_by),
			(self.sm.student, self.sm.customer, "Administrator"))

		invoice = frappe.get_doc("Sales Invoice", issuance.sales_invoice)
		self.assertEqual((invoice.docstatus, invoice.customer, invoice.update_stock, invoice.library_issuance),
			(1, self.sm.customer, 1, issuance.name))
		self.assertEqual(flt(invoice.grand_total), 80)
		self.assertFalse(invoice.get("student"), "library invoices must not be school bills")
		self.assertEqual([(i.item_code, i.qty, i.rate, i.income_account, i.warehouse) for i in invoice.items],
			[(self.billed.item, 2, 40, self.s.default_income_account, self.s.library_warehouse)])

		entry = frappe.get_doc("Stock Entry", issuance.stock_entry)
		self.assertEqual((entry.docstatus, entry.purpose, entry.library_issuance), (1, "Material Issue", issuance.name))
		self.assertEqual([(i.item_code, i.qty, i.s_warehouse, i.expense_account) for i in entry.items],
			[(self.free.item, 1, self.s.library_warehouse, self.s.issue_expense_account)])

		self.assertEqual(warehouse_qty(self.billed.item), 3)
		self.assertEqual(warehouse_qty(self.free.item), 3)
		self.assertEqual(frappe.db.get_value("Library Book", self.billed.name, "total_copies"), 3)

	def test_cancel_reverses_the_invoice_and_the_stock(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 1)])
		issuance.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", issuance.sales_invoice, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Stock Entry", issuance.stock_entry, "docstatus"), 2)
		self.assertEqual((warehouse_qty(self.billed.item), warehouse_qty(self.free.item)), (5, 4))

	def test_a_paid_invoice_blocks_cancelling(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 1)])
		frappe.db.set_value("Sales Invoice", issuance.sales_invoice, "outstanding_amount", 0)
		with self.assertRaisesRegex(frappe.ValidationError, "payments"):
			issuance.cancel()

	def test_stock_and_customer_are_checked_before_submit(self):
		draft = make_issuance(self.sm.member, [(self.billed.name, 6)], submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, "Not enough stock"):
			draft.submit()
		draft.reload()
		draft.items[0].qty = 1
		with patch.object(billing, "student_customer", return_value=None):
			draft.save()
			with self.assertRaisesRegex(frappe.ValidationError, "no Customer"):
				draft.submit()

	def test_only_issue_type_books_with_rates_and_only_students(self):
		lending = make_book("_Test Novel").name
		with self.assertRaisesRegex(frappe.ValidationError, "lending book"):
			make_issuance(self.sm.member, [(lending, 1)], submit=False)
		no_rate = make_issue_book("_Test Unpriced", billable=True)
		with self.assertRaisesRegex(frappe.ValidationError, "no rate"):
			make_issuance(self.sm.member, [(no_rate.name, 1)], submit=False)
		staff = frappe.db.get_value("Library Member", {"reference_doctype": "Employee"})
		with self.assertRaisesRegex(frappe.ValidationError, "not a student"):
			make_issuance(staff, [(self.free.name, 1)], submit=False)

	def test_warning_when_a_billable_book_was_already_issued_this_year(self):
		make_issuance(self.sm.member, [(self.billed.name, 1)])
		frappe.local.message_log = []
		make_issuance(self.sm.member, [(self.billed.name, 1)], submit=False)
		messages = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn("already issued", messages)

	def test_library_documents_cannot_be_made_or_cancelled_outside_the_library(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 1)])
		invoice = frappe.get_doc("Sales Invoice", issuance.sales_invoice)
		with self.assertRaisesRegex(frappe.PermissionError, "belongs to Library Book Issuance"):
			invoice.cancel()
		copy = frappe.copy_doc(invoice)
		copy.library_issuance = issuance.name
		with self.assertRaisesRegex(frappe.PermissionError, "Only the library"):
			copy.insert()

	def test_scan_finds_books_by_isbn_copy_barcode_and_item_barcode(self):
		frappe.db.set_value("Library Book", self.billed.name, "isbn", "9780000000017")
		self.assertEqual(scan.resolve("9780000000017").name, self.billed.name)
		lending = make_book("_Test Scanned Novel").name
		copy = make_copy(lending, barcode="LIBTEST0001").name
		found = scan.resolve("LIBTEST0001")
		self.assertEqual((found.name, found.book_copy), (lending, copy))
		item = frappe.get_doc("Item", self.free.item)
		item.append("barcodes", {"barcode": "LIBTEST-ITEM-1"})
		item.save()
		self.assertEqual(scan.resolve("LIBTEST-ITEM-1").name, self.free.name)
		self.assertIsNone(scan.resolve("nothing-like-this"))


class TestBulkIssue(IssuanceTestCase):
	def test_one_issuance_per_student_and_already_issued_students_are_skipped(self):
		students = frappe.db.sql_list("""
			select s.name from tabStudent s join tabCustomer c on c.name = s.customer
			where s.enabled = 1 and c.disabled = 0 order by s.name limit 3""")
		make_issuance(student_member().member, [(self.billed.name, 1)])  # the first student already has it
		doc = frappe.get_doc({"doctype": "Library Bulk Issue", "student_batch": frappe.db.get_value("Student Batch Name", {}),
			"items": [{"book": self.billed.name, "qty": 1}, {"book": self.free.name, "qty": 1}]}).insert()
		with patch("library.library.doctype.library_bulk_issue.library_bulk_issue.LibraryBulkIssue.get_students",
				return_value=students):
			counts = bulk.run_bulk_issue(doc.name, user="Administrator", commit_every=0)
		self.assertEqual(counts, {"Created": 2, "Skipped": 1, "Failed": 0})
		doc.reload()
		self.assertEqual((doc.status, doc.created_count, doc.skipped_count), ("Completed", 2, 1))
		self.assertEqual([(r.student, r.status) for r in doc.results],
			[(students[0], "Skipped"), (students[1], "Created"), (students[2], "Created")])
		for row in doc.results[1:]:
			self.assertEqual(frappe.db.get_value("Library Book Issuance", row.issuance, "docstatus"), 1)

	def test_a_failing_student_does_not_undo_the_others(self):
		students = frappe.db.sql_list("""
			select s.name from tabStudent s join tabCustomer c on c.name = s.customer
			where s.enabled = 1 and c.disabled = 0 order by s.name limit 2""")
		doc = frappe.get_doc({"doctype": "Library Bulk Issue", "student_batch": frappe.db.get_value("Student Batch Name", {}),
			"skip_already_issued": 0, "items": [{"book": self.billed.name, "qty": 3}]}).insert()  # stock 5: one fits
		with patch("library.library.doctype.library_bulk_issue.library_bulk_issue.LibraryBulkIssue.get_students",
				return_value=students):
			counts = bulk.run_bulk_issue(doc.name, user="Administrator", commit_every=0)
		self.assertEqual(counts, {"Created": 1, "Skipped": 0, "Failed": 1})
		doc.reload()
		self.assertEqual(doc.status, "Completed with Errors")
		self.assertIn("Not enough stock", doc.results[1].message)
		self.assertEqual(warehouse_qty(self.billed.item), 2)


class TestRentalsAndFines(IssuanceTestCase):
	def setUp(self):
		super().setUp()
		set_settings(rental_item=make_service_item("_Test Library Rental"), rental_income_account=account("Income", "Income Account"),
			fine_item=make_service_item("_Test Library Fine"), fine_income_account=account("Income", "Income Account"))
		self.lending = make_book("_Test Rented Novel").name
		self.copy = make_copy(self.lending).name

	def test_rental_fee_is_invoiced_and_cancelled_with_the_issue(self):
		issue = circulate("Issue", self.sm.member, self.copy, rental_fee=15)
		invoice = frappe.get_doc("Sales Invoice", issue.sales_invoice)
		self.assertEqual((invoice.docstatus, invoice.customer, invoice.update_stock, flt(invoice.grand_total)),
			(1, self.sm.customer, 0, 15))
		self.assertEqual((invoice.library_document_type, invoice.library_document), ("Library Circulation", issue.name))
		issue.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", issue.sales_invoice, "docstatus"), 2)

	def test_final_fines_are_invoiced_when_switched_on_and_waiving_cancels_the_invoice(self):
		set_settings(bill_fines_to_customer=1)
		frappe.db.set_value("Library Member", self.sm.member, "membership_type", self.mtype)
		circulate("Issue", self.sm.member, self.copy, transaction_date=days_ago(10))  # 3 days late at 3/day
		circulate("Return", self.sm.member, self.copy)
		fine = frappe.get_doc("Library Fine", {"member": self.sm.member, "fine_type": "Overdue"})
		self.assertEqual((fine.payment_status, fine.outstanding_amount), ("Invoiced", 0))
		self.assertEqual(flt(frappe.db.get_value("Sales Invoice", fine.sales_invoice, "grand_total")), 9)
		self.assertEqual(frappe.db.get_value("Library Member", self.sm.member, "outstanding_balance"), 0)

		fine.payment_status = "Unpaid"
		with self.assertRaisesRegex(frappe.ValidationError, "only be waived"):
			fine.save()
		fine.reload()
		fine.payment_status = "Waived"
		fine.waiver_reason = "Returned with a note from the class teacher"
		fine.save()
		self.assertEqual(frappe.db.get_value("Sales Invoice", fine.sales_invoice, "docstatus"), 2)

	def test_fines_stay_with_the_library_when_billing_is_off(self):
		frappe.db.set_value("Library Member", self.sm.member, "membership_type", self.mtype)
		circulate("Issue", self.sm.member, self.copy, transaction_date=days_ago(10))
		circulate("Return", self.sm.member, self.copy)
		fine = frappe.get_doc("Library Fine", {"member": self.sm.member, "fine_type": "Overdue"})
		self.assertEqual((fine.payment_status, fine.sales_invoice, fine.outstanding_amount), ("Unpaid", None, 9))
