"""Phase 2: Issue-type books as stock items, rates, warehouse balance and stock requests."""

import frappe

from library.library import stock
from library.tests.utils import LibraryTestCase, make_book, receive_stock, set_settings, set_stock_settings


class TestLibraryStock(LibraryTestCase):
	def setUp(self):
		super().setUp()
		self.s = set_stock_settings()

	def test_issue_book_gets_a_stock_item_in_the_library_group(self):
		book = make_book("_Test Exercise Book", book_type="Issue")
		item = frappe.db.get_value("Item", book.item, ["item_group", "is_stock_item", "item_name"], as_dict=True)
		self.assertEqual((item.item_group, item.is_stock_item, item.item_name),
			(self.s.library_item_group, 1, "_Test Exercise Book"))
		self.assertEqual(book.book_status, "Out of Stock")

	def test_lending_books_are_never_billable_and_need_no_item(self):
		book = make_book("_Test Novel", is_billable=1, rate=30)
		self.assertEqual((book.book_type, book.is_billable, book.item), ("Lending", 0, None))

	def test_rate_comes_from_the_price_list_and_can_be_overridden(self):
		book = make_book("_Test Textbook", book_type="Issue")
		frappe.get_doc({"doctype": "Item Price", "item_code": book.item, "price_list": self.s.selling_price_list,
			"price_list_rate": 85}).insert()
		book.is_billable = 1
		book.save()
		self.assertEqual(book.rate, 85)
		book.rate = 70
		book.save()
		self.assertEqual(book.rate, 70)

	def test_warehouse_balance_and_status_follow_stock_entries(self):
		book = make_book("_Test Workbook", book_type="Issue")
		entry = receive_stock(book.item, 5, self.s.library_warehouse)
		values = frappe.db.get_value("Library Book", book.name, ["total_copies", "available_copies", "book_status"], as_dict=True)
		self.assertEqual((values.total_copies, values.available_copies, values.book_status), (5, 5, "Available"))
		self.assertEqual(frappe.get_doc("Library Book", book.name).warehouse_qty, 5)
		receive_stock(book.item, 3, self.s.stores_warehouse)  # elsewhere: no change
		self.assertEqual(frappe.db.get_value("Library Book", book.name, "total_copies"), 5)
		entry.cancel()
		self.assertEqual(frappe.db.get_value("Library Book", book.name, "book_status"), "Out of Stock")

	def test_stock_request_is_a_transfer_from_stores_to_the_library(self):
		book = make_book("_Test Atlas", book_type="Issue")
		request = stock.make_stock_request(book.name)
		self.assertEqual((request.material_request_type, request.set_from_warehouse, request.set_warehouse),
			("Material Transfer", self.s.stores_warehouse, self.s.library_warehouse))
		self.assertEqual([(r.item_code, r.qty, r.from_warehouse, r.warehouse) for r in request.items],
			[(book.item, 1, self.s.stores_warehouse, self.s.library_warehouse)])
		request.insert()  # the user's draft, as the form would save it
		self.assertEqual(request.workflow_state or "Draft", "Draft")

		lending = make_book("_Test Lending").name
		with self.assertRaisesRegex(frappe.ValidationError, "not an Issue-type"):
			stock.make_stock_request(books=frappe.as_json([book.name, lending]))

	def test_settings_refuse_groups_and_wrong_account_types(self):
		settings = frappe.get_single("Library Settings")
		root = frappe.db.get_value("Warehouse", {"company": self.s.company, "is_group": 1})
		settings.library_warehouse = root
		with self.assertRaisesRegex(frappe.ValidationError, "group"):
			settings.save()
		settings.reload()
		settings.default_income_account = self.s.issue_expense_account
		with self.assertRaisesRegex(frappe.ValidationError, "Income"):
			settings.save()
		settings.reload()
		settings.stores_warehouse = settings.library_warehouse
		with self.assertRaisesRegex(frappe.ValidationError, "different"):
			settings.save()

	def test_issue_book_needs_the_item_group_setting(self):
		set_settings(library_item_group=None)
		with self.assertRaisesRegex(frappe.ValidationError, "Library Item Group"):
			make_book("_Test Without Group", book_type="Issue")
