"""Phase 4: what Librarians, Library Managers and Library Members may do."""

import frappe

from library.library import stock
from library.tests.test_issuance import IssuanceTestCase
from library.tests.utils import circulate, make_book, make_copy, make_issuance, make_member, make_user


class TestRoles(IssuanceTestCase):
	def setUp(self):
		super().setUp()
		self.librarian = make_user("library-test-librarian@example.com", "Librarian", "Employee")
		self.manager = make_user("library-test-manager@example.com", "Library Manager", "Employee")

	def test_librarians_issue_and_bill_without_accounting_roles_but_cannot_cancel(self):
		frappe.set_user(self.librarian)
		self.assertFalse(frappe.has_permission("Sales Invoice", "create"))
		self.assertFalse(frappe.has_permission("Stock Entry", "create"))
		issuance = make_issuance(self.sm.member, [(self.billed.name, 1), (self.free.name, 1)])
		self.assertEqual(issuance.issued_by, self.librarian)
		invoice = frappe.db.get_value("Sales Invoice", issuance.sales_invoice, ["docstatus", "owner"], as_dict=True)
		self.assertEqual((invoice.docstatus, invoice.owner), (1, self.librarian))
		with self.assertRaises(frappe.PermissionError):
			issuance.cancel()

		frappe.set_user(self.manager)
		issuance = frappe.get_doc("Library Book Issuance", issuance.name)
		issuance.cancel()
		self.assertEqual(frappe.db.get_value("Sales Invoice", issuance.sales_invoice, "docstatus"), 2)

	def test_settings_and_bulk_issue_are_for_library_managers(self):
		frappe.set_user(self.librarian)
		self.assertFalse(frappe.has_permission("Library Settings", "read"))
		self.assertFalse(frappe.has_permission("Library Bulk Issue", "create"))
		frappe.set_user(self.manager)
		self.assertTrue(frappe.has_permission("Library Settings", "write"))
		self.assertTrue(frappe.has_permission("Library Bulk Issue", "create"))

	def test_only_library_managers_waive_fines(self):
		fine = frappe.get_doc({"doctype": "Library Fine", "member": make_member().name, "fine_type": "Other",
			"fine_amount": 20}).insert()
		frappe.set_user(self.librarian)
		fine = frappe.get_doc("Library Fine", fine.name)
		fine.payment_status = "Waived"
		fine.waiver_reason = "Kind"
		with self.assertRaisesRegex(frappe.PermissionError, "Library Manager"):
			fine.save()
		frappe.set_user(self.manager)
		fine = frappe.get_doc("Library Fine", fine.name)
		fine.payment_status = "Waived"
		fine.waiver_reason = "First offence"
		fine.save()
		self.assertEqual((fine.outstanding_amount, fine.waived_by), (0, self.manager))

	def test_stock_requests_are_for_library_managers(self):
		frappe.set_user(self.librarian)
		with self.assertRaisesRegex(frappe.PermissionError, "Library Manager"):
			stock.make_stock_request(self.billed.name)
		frappe.set_user(self.manager)
		self.assertEqual(stock.make_stock_request(self.billed.name).material_request_type, "Material Transfer")

	def test_library_members_see_only_their_own_records(self):
		reader = make_user("library-test-reader@example.com", "Library Member")
		mine, theirs = make_member("_Test Mine"), make_member("_Test Theirs")
		frappe.db.set_value("Library Member", mine.name, "user", reader)
		book = make_book("_Test Shared Book").name
		my_loan = circulate("Issue", mine.name, make_copy(book).name)
		their_loan = circulate("Issue", theirs.name, make_copy(book).name)

		frappe.set_user(reader)
		self.assertEqual(frappe.get_list("Library Circulation", pluck="name"), [my_loan.name])
		self.assertEqual(frappe.get_list("Library Member", pluck="name"), [mine.name])
		self.assertTrue(frappe.has_permission("Library Circulation", "read", doc=my_loan))
		self.assertFalse(frappe.has_permission("Library Circulation", "read", doc=their_loan))
		self.assertFalse(frappe.has_permission("Library Circulation", "write", doc=my_loan))
		self.assertFalse(frappe.has_permission("Library Circulation", "create"))
		self.assertTrue(frappe.has_permission("Library Book", "read"))
