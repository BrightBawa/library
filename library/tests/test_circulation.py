"""Library Circulation: issue, return, renew, fines, cancel, counters and the API."""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, getdate, today

from library.api import circulation as api
from library.tests.utils import (
	LibraryTestCase,
	circulate,
	days_ago,
	make_book,
	make_copy,
	make_member,
	set_settings,
)


class TestCirculation(LibraryTestCase):
	def setUp(self):
		super().setUp()
		self.member = make_member().name
		self.book = make_book().name
		self.copy = make_copy(self.book).name

	def value(self, doctype, name, field):
		return frappe.db.get_value(doctype, name, field)

	def test_issue_marks_copy_issued_and_updates_counters(self):
		issue = circulate("Issue", self.member, self.copy)
		self.assertEqual(getdate(issue.due_date), getdate(add_days(today(), 7)))  # loan_period_days
		self.assertEqual(issue.max_renewals_allowed, 2)
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Issued")
		book = frappe.db.get_value("Library Book", self.book,
			["total_copies", "available_copies", "book_status"], as_dict=True)
		self.assertEqual((book.total_copies, book.available_copies, book.book_status), (1, 0, "All Issued"))
		member = frappe.db.get_value("Library Member", self.member,
			["books_issued", "total_books_borrowed", "overdue_books"], as_dict=True)
		self.assertEqual((member.books_issued, member.total_books_borrowed, member.overdue_books), (1, 1, 0))

	def test_issue_is_refused_for_inactive_member_unavailable_copy_and_limit(self):
		frappe.db.set_value("Library Member", self.member, "membership_status", "Suspended")
		with self.assertRaisesRegex(frappe.ValidationError, "Suspended"):
			circulate("Issue", self.member, self.copy)
		frappe.db.set_value("Library Member", self.member, "membership_status", "Active")

		frappe.db.set_value("Library Book Copy", self.copy, "status", "Maintenance")
		with self.assertRaisesRegex(frappe.ValidationError, "not available"):
			circulate("Issue", self.member, self.copy)
		frappe.db.set_value("Library Book Copy", self.copy, "status", "Available")

		circulate("Issue", self.member, self.copy)
		circulate("Issue", self.member, make_copy(self.book).name)
		with self.assertRaisesRegex(frappe.ValidationError, "limit"):  # max_books_allowed = 2
			circulate("Issue", self.member, make_copy(self.book).name)

	def test_late_return_creates_one_overdue_fine_on_the_issue(self):
		issue = circulate("Issue", self.member, self.copy, transaction_date=days_ago(20))
		ret = circulate("Return", self.member, self.copy)
		self.assertEqual(ret.against_issue, issue.name)
		self.assertEqual(ret.days_overdue, 13)
		self.assertEqual(ret.fine_amount, 39)  # 13 days x fine_per_day 3

		issue.reload()
		self.assertEqual(getdate(issue.return_date), getdate(today()))
		fines = frappe.get_all("Library Fine", filters={"member": self.member},
			fields=["fine_type", "fine_amount", "outstanding_amount", "payment_status", "circulation"])
		self.assertEqual(len(fines), 1)
		self.assertEqual((fines[0].fine_type, fines[0].fine_amount, fines[0].circulation), ("Overdue", 39, issue.name))
		self.assertEqual((fines[0].outstanding_amount, fines[0].payment_status), (39, "Unpaid"))
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Available")
		self.assertEqual(self.value("Library Member", self.member, "outstanding_balance"), 39)
		self.assertEqual(self.value("Library Member", self.member, "books_issued"), 0)

	def test_daily_job_accrues_the_fine_and_the_return_finalises_it(self):
		issue = circulate("Issue", self.member, self.copy, transaction_date=days_ago(10))  # due 3 days ago
		api.auto_calculate_fines()
		fine = frappe.get_all("Library Fine", filters={"circulation": issue.name}, fields=["name", "fine_amount"])
		self.assertEqual(len(fine), 1)
		self.assertEqual(fine[0].fine_amount, 9)
		self.assertEqual(self.value("Library Member", self.member, "overdue_books"), 1)

		circulate("Return", self.member, self.copy, return_date=days_ago(1))  # 2 days late
		after = frappe.get_all("Library Fine", filters={"circulation": issue.name}, fields=["name", "fine_amount"])
		self.assertEqual([(f.name, f.fine_amount) for f in after], [(fine[0].name, 6)])
		self.assertEqual(self.value("Library Member", self.member, "overdue_books"), 0)

	def test_paid_fine_is_never_changed_by_the_daily_job(self):
		issue = circulate("Issue", self.member, self.copy, transaction_date=days_ago(10))
		api.auto_calculate_fines()
		fine = frappe.get_doc("Library Fine", {"circulation": issue.name})
		fine.paid_amount = fine.fine_amount
		fine.save()
		self.assertEqual(fine.payment_status, "Paid")
		frappe.db.set_value("Library Circulation", issue.name, "due_date", days_ago(5))
		api.auto_calculate_fines()
		self.assertEqual(self.value("Library Fine", fine.name, "fine_amount"), 9)

	def test_renew_extends_the_issue_and_cancel_restores_it(self):
		issue = circulate("Issue", self.member, self.copy)
		renew = circulate("Renew", self.member, self.copy)
		self.assertEqual(renew.against_issue, issue.name)
		self.assertEqual(getdate(renew.original_due_date), getdate(issue.due_date))
		issue.reload()
		self.assertEqual(getdate(issue.due_date), getdate(add_days(today(), 14)))
		self.assertEqual(issue.renewal_count, 1)

		renew.cancel()
		issue.reload()
		self.assertEqual(getdate(issue.due_date), getdate(add_days(today(), 7)))
		self.assertEqual(issue.renewal_count, 0)

	def test_renewal_limit_and_reservations_block_renewal(self):
		set_settings(max_renewals=1)
		circulate("Issue", self.member, self.copy)
		circulate("Renew", self.member, self.copy)
		with self.assertRaisesRegex(frappe.ValidationError, "maximum"):
			circulate("Renew", self.member, self.copy)

		other_copy = make_copy(self.book).name
		circulate("Issue", self.member, other_copy)
		frappe.get_doc({"doctype": "Library Reservation", "member": make_member("_Test Waiting").name,
			"book": self.book}).insert()
		with self.assertRaisesRegex(frappe.ValidationError, "reserved"):
			circulate("Renew", self.member, other_copy)

	def test_return_by_another_member_is_refused(self):
		circulate("Issue", self.member, self.copy)
		with self.assertRaisesRegex(frappe.ValidationError, "on loan to"):
			circulate("Return", make_member("_Test Other").name, self.copy)
		with self.assertRaisesRegex(frappe.ValidationError, "not on loan"):
			circulate("Return", self.member, make_copy(self.book).name)

	def test_damaged_return_and_its_cancel(self):
		issue = circulate("Issue", self.member, self.copy)
		ret = circulate("Return", self.member, self.copy, condition_on_return="Damaged")
		copy = frappe.db.get_value("Library Book Copy", self.copy, ["status", "condition"], as_dict=True)
		self.assertEqual((copy.status, copy.condition), ("Damaged", "Damaged"))
		damage = frappe.get_all("Library Fine", filters={"circulation": ret.name}, fields=["fine_type", "fine_amount"])
		self.assertEqual([(f.fine_type, f.fine_amount) for f in damage], [("Damage", 50)])

		ret.cancel()
		self.assertFalse(frappe.db.exists("Library Fine", {"circulation": ret.name}))
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Issued")
		self.assertIsNone(self.value("Library Circulation", issue.name, "return_date"))
		self.assertEqual(self.value("Library Member", self.member, "books_issued"), 1)

	def test_lost_return_fines_twice_the_cost_and_removes_the_copy_from_stock(self):
		circulate("Issue", self.member, self.copy)
		ret = circulate("Return", self.member, self.copy, condition_on_return="Lost")
		lost = frappe.get_all("Library Fine", filters={"circulation": ret.name}, fields=["fine_type", "fine_amount"])
		self.assertEqual([(f.fine_type, f.fine_amount) for f in lost], [("Lost", 200)])
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Lost")
		self.assertEqual(self.value("Library Book", self.book, "book_status"), "Out of Stock")

	def test_an_issue_with_a_return_cannot_be_cancelled(self):
		issue = circulate("Issue", self.member, self.copy)
		circulate("Return", self.member, self.copy)
		with self.assertRaisesRegex(frappe.ValidationError, "Cancel Return"):
			issue.cancel()

	def test_cancelled_issue_frees_the_copy_and_reopens_the_reservation(self):
		reservation = frappe.get_doc({"doctype": "Library Reservation", "member": self.member,
			"book": self.book}).insert()
		issue = circulate("Issue", self.member, self.copy)
		self.assertEqual(self.value("Library Reservation", reservation.name, "status"), "Fulfilled")
		self.assertEqual(self.value("Library Reservation", reservation.name, "circulation"), issue.name)
		issue.cancel()
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Available")
		self.assertEqual(self.value("Library Reservation", reservation.name, "status"), "Active")
		self.assertEqual(self.value("Library Member", self.member, "books_issued"), 0)

	def test_api_wrappers_go_through_the_controller(self):
		issue = api.issue_book(self.member, self.copy)
		renew = api.renew_book(issue)
		self.assertEqual(self.value("Library Circulation", renew, "against_issue"), issue)
		ret = api.return_book(issue, condition="Good")
		self.assertEqual(self.value("Library Circulation", ret, "transaction_type"), "Return")
		self.assertEqual(self.value("Library Book Copy", self.copy, "status"), "Available")
		with self.assertRaisesRegex(frappe.ValidationError, "already been returned"):
			api.return_book(issue)

	def test_reminder_and_reservation_expiry_jobs(self):
		# The jobs act on every loan and reservation on the site, so check only ours.
		frappe.db.set_value("Library Member", self.member, "email", "reader@example.com")
		circulate("Issue", self.member, self.copy, transaction_date=days_ago(9))
		with patch("frappe.sendmail") as sendmail:
			api.send_overdue_reminders()
		self.assertIn(["reader@example.com"], [c.kwargs["recipients"] for c in sendmail.call_args_list])

		set_settings(overdue_reminder_days=5)  # 2 days overdue: not yet
		with patch("frappe.sendmail") as sendmail:
			api.send_overdue_reminders()
		self.assertNotIn(["reader@example.com"], [c.kwargs["recipients"] for c in sendmail.call_args_list])

		waiting = make_member("_Test Waiting", email="waiting@example.com").name
		expired = frappe.get_doc({"doctype": "Library Reservation", "member": waiting, "book": self.book,
			"expiry_date": days_ago(1)}).insert()
		queued = make_member("_Test Queued", email="queued@example.com").name
		frappe.get_doc({"doctype": "Library Reservation", "member": queued, "book": self.book}).insert()
		with patch("frappe.sendmail") as sendmail:
			api.expire_unclaimed_reservations()
		self.assertEqual(self.value("Library Reservation", expired.name, "status"), "Expired")
		self.assertIn(["queued@example.com"], [c.kwargs["recipients"] for c in sendmail.call_args_list])


class TestFine(LibraryTestCase):
	def test_payments_and_waiver(self):
		member = make_member().name
		fine = frappe.get_doc({"doctype": "Library Fine", "member": member, "fine_type": "Other",
			"fine_amount": 40}).insert()
		self.assertEqual((fine.outstanding_amount, fine.payment_status), (40, "Unpaid"))
		fine.paid_amount = 15
		fine.save()
		self.assertEqual((fine.outstanding_amount, fine.payment_status), (25, "Partially Paid"))
		self.assertEqual(frappe.db.get_value("Library Member", member, "outstanding_balance"), 25)

		fine.payment_status = "Waived"
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			fine.save()
		fine.waiver_reason = "Hardship"
		fine.save()
		self.assertEqual((fine.outstanding_amount, fine.waived_by), (0, "Administrator"))
		self.assertEqual(frappe.db.get_value("Library Member", member, "outstanding_balance"), 0)

		fine.payment_status = "Unpaid"
		fine.paid_amount = 50
		with self.assertRaisesRegex(frappe.ValidationError, "more than the fine"):
			fine.save()
