"""Shared set-up for the library tests.

The tests run against the live site inside one transaction that the runner rolls back
(scripts/run_library_mock_tests.py in the bench repo). Each test also runs inside its
own savepoint, so records and Settings changes never leak from one test to the next.
frappe.log_error is patched: Error Log is MyISAM and would survive the rollback.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

SETTINGS = {
	"enable_fines": 1,
	"default_fine_per_day": 5,
	"default_loan_period": 14,
	"max_renewals": 2,
	"damage_fine_amount": 50,
	"lost_book_fine_multiplier": 2,
	"reservation_expiry_days": 3,
	"send_overdue_reminders": 1,
	"overdue_reminder_days": 1,
}


class LibraryTestCase(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("library_test")
		self.log_error = patch("frappe.log_error").start()
		self.addCleanup(patch.stopall)
		set_settings(**SETTINGS)
		self.mtype = make_membership_type()

	def tearDown(self):
		frappe.db.rollback(save_point="library_test")
		frappe.set_user("Administrator")


def set_settings(**values):
	frappe.db.set_single_value("Library Settings", values)
	# set_single_value leaves the request's value cache alone; drop it so reads see the change.
	frappe.db.value_cache.pop("Library Settings", None)


def make_membership_type(name="_Test Library Type", max_books=2, loan_days=7, fine=3):
	if frappe.db.exists("Library Membership Type", name):
		frappe.delete_doc("Library Membership Type", name, force=True)
	return frappe.get_doc({
		"doctype": "Library Membership Type", "membership_type": name, "max_books_allowed": max_books,
		"loan_period_days": loan_days, "fine_per_day": fine, "is_active": 1,
	}).insert().name


def make_member(full_name="_Test Reader", membership_type="_Test Library Type", **values):
	return frappe.get_doc({
		"doctype": "Library Member", "full_name": full_name, "membership_type": membership_type,
		"reference_doctype": "Other", **values,
	}).insert()


def make_book(title="_Test Library Book", **values):
	return frappe.get_doc({"doctype": "Library Book", "book_title": title, **values}).insert()


def make_copy(book, cost=100, **values):
	return frappe.get_doc({"doctype": "Library Book Copy", "book": book, "cost": cost, **values}).insert()


def circulate(transaction_type, member, copy, submit=True, **values):
	doc = frappe.get_doc({
		"doctype": "Library Circulation", "transaction_type": transaction_type,
		"member": member, "book_copy": copy, **values,
	}).insert()
	if submit:
		doc.submit()
	return doc


def days_ago(days):
	return add_days(today(), -days)


def company():
	return frappe.db.get_single_value("Global Defaults", "default_company")


def make_warehouse(name="_Test Library"):
	abbr = frappe.db.get_value("Company", company(), "abbr")
	full = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full):
		root = frappe.db.get_value("Warehouse", {"company": company(), "is_group": 1, "parent_warehouse": ["is", "not set"]})
		frappe.get_doc({"doctype": "Warehouse", "warehouse_name": name, "company": company(),
			"parent_warehouse": root}).insert()
	return full


def make_item_group(name="_Test Library Books"):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": name, "parent_item_group": "All Item Groups"}).insert()
	return name


def account(root_type, account_type=None):
	filters = {"company": company(), "root_type": root_type, "is_group": 0, "disabled": 0}
	if account_type:
		filters["account_type"] = account_type
	return frappe.db.get_value("Account", filters, "name", order_by="name")


def set_stock_settings(**overrides):
	"""Library Settings pointing at test-only warehouses and group, with real company accounts."""
	values = {
		"company": company(),
		"library_warehouse": make_warehouse("_Test Library"),
		"stores_warehouse": make_warehouse("_Test Stores"),
		"library_item_group": make_item_group(),
		"selling_price_list": frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}),
		"default_income_account": account("Income", "Income Account"),
		"issue_expense_account": account("Expense", "Expense Account"),
		"default_cost_center": frappe.db.get_value("Cost Center", {"company": company(), "is_group": 0}),
	}
	values.update(overrides)
	set_settings(**values)
	return frappe._dict(values)


def receive_stock(item, qty, warehouse, rate=50):
	"""Material Receipt into a warehouse (rolled back with the test)."""
	entry = frappe.get_doc({
		"doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
		"company": company(),
		"items": [{"item_code": item, "qty": qty, "t_warehouse": warehouse, "basic_rate": rate,
			"conversion_factor": 1}],
	}).insert()
	entry.submit()
	return entry


def student_member():
	"""A real enabled student with a Customer, and its Library Member (made in the test if missing)."""
	from library.library import utils as member_utils

	row = frappe.db.sql("""
		select s.name, s.customer from tabStudent s join tabCustomer c on c.name = s.customer
		where s.enabled = 1 and c.disabled = 0 order by s.name limit 1""", as_dict=True)[0]
	member = member_utils.existing_member("Student", row.name) or member_utils.create_member(
		"Student", frappe.get_doc("Student", row.name))
	frappe.db.set_value("Library Member", member, "membership_status", "Active")
	return frappe._dict(member=member, student=row.name, customer=row.customer)


def make_service_item(name):
	item = frappe.new_doc("Item")
	if frappe.db.get_single_value("Stock Settings", "item_naming_by") == "Item Code":
		item.item_code = name
	item.update({"item_name": name, "item_group": make_item_group(), "stock_uom": "Nos",
		"is_stock_item": 0, "is_sales_item": 1, "include_item_in_manufacturing": 0})
	item.insert()
	return item.name


def make_issue_book(title, billable=False, rate=0, stock=0):
	book = make_book(title, book_type="Issue", is_billable=1 if billable else 0, rate=rate)
	if stock:
		receive_stock(book.item, stock, frappe.db.get_single_value("Library Settings", "library_warehouse"))
	return book


def make_issuance(member, rows, submit=True, **values):
	doc = frappe.get_doc({"doctype": "Library Book Issuance", "member": member,
		"items": [{"book": book, "qty": qty} for book, qty in rows], **values}).insert()
	if submit:
		doc.submit()
	return doc
