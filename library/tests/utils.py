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
