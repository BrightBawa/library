# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt
"""Books a student keeps (exercise books, textbooks): billed lines go on a Sales Invoice to the
student's Customer, free lines leave the library warehouse on a Material Issue."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from library.library import billing, school
from library.library.stock import get_settings, refresh_books_for_items, require, warehouse_qty

CANCEL_ROLES = {"Library Manager"}


class LibraryBookIssuance(Document):
	# The invoice and stock entry are cancelled by on_cancel; do not ask the user to cancel them first.
	ignore_linked_doctypes = ("Sales Invoice", "Stock Entry")

	def validate(self):
		settings = get_settings()
		self.company = self.company or settings.company
		if not self.company:
			require(settings, "company")
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		self.academic_year = self.academic_year or school.current_academic_year()
		self.set_student()
		self.set_rows()
		self.set_totals()
		self.warn_already_issued()

	def set_student(self):
		member = frappe.db.get_value("Library Member", self.member,
			["reference_doctype", "student", "membership_status", "full_name"], as_dict=True)
		if not member:
			frappe.throw(_("Select the library member."))
		if member.reference_doctype != "Student" or not member.student:
			frappe.throw(_("{0} is not a student; books are issued to students.").format(member.full_name))
		if member.membership_status != "Active":
			frappe.throw(_("{0}'s library membership is {1}.").format(member.full_name, member.membership_status))
		self.student = member.student
		self.student_name = member.full_name
		self.student_batch = school.student_batch(self.student, self.academic_year)
		self.customer = billing.student_customer(self.student)

	def set_rows(self):
		if not self.items:
			frappe.throw(_("Add the books to issue."))
		for row in self.items:
			book = frappe.db.get_value("Library Book", row.book,
				["book_title", "book_type", "item", "is_billable", "rate"], as_dict=True)
			if book.book_type != "Issue":
				frappe.throw(_("Row {0}: {1} is a lending book; lend it through Library Circulation.").format(
					row.idx, book.book_title))
			if not book.item:
				frappe.throw(_("Row {0}: {1} has no item.").format(row.idx, book.book_title))
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: the quantity must be more than zero.").format(row.idx))
			row.book_title, row.item, row.book_type = book.book_title, book.item, book.book_type
			row.is_billable = book.is_billable
			row.rate = flt(book.rate) if book.is_billable else 0
			if book.is_billable and not row.rate:
				frappe.throw(_("Row {0}: {1} is billable but has no rate.").format(row.idx, book.book_title))
			row.amount = flt(row.qty) * flt(row.rate)
			row.currency = self.currency

	def set_totals(self):
		self.total_qty = sum(flt(r.qty) for r in self.items)
		self.total_billable_qty = sum(flt(r.qty) for r in self.items if r.is_billable)
		self.total_billable = sum(flt(r.amount) for r in self.items if r.is_billable)
		self.total_free = sum(flt(r.qty) for r in self.items if not r.is_billable)

	def warn_already_issued(self):
		books = [r.book for r in self.items if r.is_billable]
		if not books:
			return
		earlier = frappe.db.sql("""
			select i.name, r.book_title from `tabLibrary Book Issuance` i
			join `tabLibrary Book Issuance Item` r on r.parent = i.name
			where i.docstatus = 1 and i.student = %s and i.academic_year = %s and r.book in %s and i.name != %s
		""", (self.student, self.academic_year, books, self.name or ""), as_dict=True)
		if earlier:
			frappe.msgprint(
				_("{0} was already issued these billable books in {1}: {2}").format(
					self.student_name, self.academic_year,
					", ".join(f"{e.book_title} ({e.name})" for e in earlier)),
				title=_("Already issued this year"), indicator="orange")

	def before_submit(self):
		settings = get_settings()
		require(settings, "library_warehouse", "issue_expense_account", "default_cost_center")
		if self.total_billable_qty:
			require(settings, "default_income_account")
			if not self.customer:
				frappe.throw(_("{0} has no Customer, so the billed books cannot be invoiced.").format(self.student_name))
		needed = defaultdict(float)
		titles = {}
		for row in self.items:
			needed[row.item] += flt(row.qty)
			titles[row.item] = row.book_title
		short = []
		for item, qty in needed.items():
			in_stock = warehouse_qty(item, settings.library_warehouse)
			if in_stock < qty:
				short.append(_("{0}: {1} needed, {2} in stock").format(titles[item], f"{qty:g}", f"{in_stock:g}"))
		if short:
			frappe.throw(_("Not enough stock in {0}:<br>{1}").format(settings.library_warehouse, "<br>".join(short)),
				title=_("Not enough stock"))
		self.issued_by = frappe.session.user

	def on_submit(self):
		settings = get_settings()
		remarks = _("Library Book Issuance {0} for {1}, issued by {2}").format(
			self.name, self.student_name, self.issued_by)
		billed = [self.as_line(r) for r in self.items if r.is_billable]
		free = [self.as_line(r) for r in self.items if not r.is_billable]
		if billed:
			invoice = billing.make_sales_invoice(customer=self.customer, company=self.company,
				posting_date=self.posting_date, rows=billed, income_account=settings.default_income_account,
				update_stock=True, issuance=self.name, remarks=remarks)
			self.db_set("sales_invoice", invoice.name)
		if free:
			entry = billing.make_stock_entry(purpose="Material Issue", company=self.company,
				posting_date=self.posting_date, rows=free, issuance=self.name, remarks=remarks)
			self.db_set("stock_entry", entry.name)
		refresh_books_for_items({r.item for r in self.items})

	def as_line(self, row):
		return {"item_code": row.item, "qty": row.qty, "rate": row.rate, "description": row.book_title}

	def before_cancel(self):
		if frappe.session.user != "Administrator" and not CANCEL_ROLES & set(frappe.get_roles()):
			frappe.throw(_("Only a Library Manager can cancel an issuance."), frappe.PermissionError)
		if frappe.db.exists("DocType", "Library Issuance Return"):
			returned = frappe.db.get_value("Library Issuance Return", {"against_issuance": self.name, "docstatus": 1})
			if returned:
				frappe.throw(_("Cancel Library Issuance Return {0} first.").format(returned))
		billing.assert_unpaid(self.sales_invoice)

	def on_cancel(self):
		billing.cancel_document("Sales Invoice", self.sales_invoice)
		billing.cancel_document("Stock Entry", self.stock_entry)
		refresh_books_for_items({r.item for r in self.items})
