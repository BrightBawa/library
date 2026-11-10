"""Phase 5: the number cards and chart sources move with library activity (measured as deltas)."""

import frappe

from library.library.api import dashboard
from library.tests.test_issuance import IssuanceTestCase
from library.tests.utils import make_issuance

SOURCES = ("library_billed_vs_free", "library_top_books_issued", "library_stock_by_category",
	"library_loans_vs_returns", "library_issuances_by_class")


def source(name):
	return frappe.get_attr(f"library.library.dashboard_chart_source.{name}.{name}.get")()


class TestDashboard(IssuanceTestCase):
	def test_cards_follow_an_issuance(self):
		before = {name: getattr(dashboard, name)()["value"] for name in
			("books_in_stock", "issuances_this_month", "billed_this_term", "free_books_this_term")}
		make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 1)])
		after = {name: getattr(dashboard, name)()["value"] for name in before}
		self.assertEqual({k: after[k] - before[k] for k in before},
			{"books_in_stock": -3, "issuances_this_month": 1, "billed_this_term": 80, "free_books_this_term": 1})
		self.assertEqual(dashboard.unpaid_fines()["fieldtype"], "Currency")

	def test_chart_sources_include_the_issued_books(self):
		issuance = make_issuance(self.sm.member, [(self.billed.name, 2), (self.free.name, 1)])
		for name in SOURCES:
			data = source(name)
			self.assertTrue(data["labels"] is not None and data["datasets"], name)
		top = source("library_top_books_issued")
		self.assertIn(self.billed.book_title, top["labels"])
		self.assertIn(issuance.student_batch or "No class", source("library_issuances_by_class")["labels"])
