"""Sales Invoices and Stock Entries that library documents create, submit and cancel.

Library staff hold no accounting roles: these documents are made only here, with
ignore_permissions and the ``from_library`` flag, and carry a link back to the library
document (``library_issuance`` or ``library_document_type`` / ``library_document``).
``guard_library_document`` refuses the same links on documents made any other way, and
refuses cancelling them outside the library, so stock and bills stay in step with the
library records.

Invoices never set Sales Invoice.student: a student field makes other apps treat the
invoice as a school fee bill.

ERPNext checks the session user's access to accounts while building an invoice even when
it is saved with ignore_permissions (get_party_account), so these documents are made in
``as_system()``: as Administrator, owned by the user who issued them.
"""

from collections import defaultdict
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import flt

from library.library.stock import get_settings, require

LINK_FIELDS = ("library_issuance", "library_document")


def student_customer(student):
	"""The student's Customer: Student.customer, else a Customer whose custom_student_id is the student."""
	if not student:
		return None
	customer = frappe.db.get_value("Student", student, "customer")
	if not customer and frappe.get_meta("Customer").has_field("custom_student_id"):
		customer = frappe.db.get_value("Customer", {"custom_student_id": student})
	return customer


@contextmanager
def as_system():
	"""Run as Administrator and give back the request's session afterwards; yields the real user.

	frappe.set_user also replaces the session id, session data and form_dict of the request,
	so those are restored, not just the user. Only library code that has already validated
	its own document runs inside this.
	"""
	local = frappe.local
	user = local.session.user
	if user == "Administrator":
		yield user
		return
	saved = (local.session.sid, local.session.data, local.form_dict)
	frappe.set_user("Administrator")
	try:
		yield user
	finally:
		frappe.set_user(user)
		local.session.sid, local.session.data, local.form_dict = saved


def keep_owner(doc, user):
	"""Frappe makes the session user (here Administrator) the owner on insert: give it back."""
	if user and user != doc.owner:
		doc.db_set("owner", user, update_modified=False)


def _library_flags(doc):
	doc.flags.ignore_permissions = True
	doc.flags.from_library = True
	return doc


def _links(issuance=None, document=None):
	values = {"library_issuance": issuance}
	if document:
		values.update({"library_document_type": document.doctype, "library_document": document.name})
	return values


def make_sales_invoice(*, customer, company, posting_date, rows, income_account, update_stock,
		issuance=None, document=None, remarks=None, is_return=False, return_against=None):
	"""Insert and submit a Sales Invoice (or credit note) for library rows.

	rows: dicts with item_code, qty, rate and description.
	"""
	settings = get_settings()
	require(settings, "default_cost_center", *(("library_warehouse", "issue_expense_account") if update_stock else ()))
	if not income_account:
		frappe.throw(_("Set the income account in Library Settings first."))
	invoice = frappe.new_doc("Sales Invoice")
	invoice.update({
		"customer": customer,
		"company": company,
		"posting_date": posting_date,
		"set_posting_time": 1,
		"selling_price_list": settings.selling_price_list,
		"ignore_pricing_rule": 1,
		"cost_center": settings.default_cost_center,
		"update_stock": 1 if update_stock else 0,
		"set_warehouse": settings.library_warehouse if update_stock else None,
		"is_return": 1 if is_return else 0,
		"return_against": return_against,
		"remarks": remarks,
		**_links(issuance, document),
	})
	for row in rows:
		line = {
			"item_code": row["item_code"], "qty": row["qty"], "rate": row["rate"], "price_list_rate": row["rate"],
			"description": row.get("description"), "income_account": income_account,
			"cost_center": settings.default_cost_center,
		}
		if update_stock:
			line.update(warehouse=settings.library_warehouse, expense_account=settings.issue_expense_account)
		invoice.append("items", line)
	_library_flags(invoice)
	with as_system() as user:
		invoice.run_method("set_missing_values")
		invoice.insert()
		invoice.submit()
	keep_owner(invoice, user)
	return invoice


def make_stock_entry(*, purpose, company, posting_date, rows, issuance=None, document=None, remarks=None):
	"""Insert and submit a Material Issue (out of) or Material Receipt (into) the library warehouse."""
	settings = get_settings()
	require(settings, "library_warehouse", "issue_expense_account", "default_cost_center")
	warehouse_field = "s_warehouse" if purpose == "Material Issue" else "t_warehouse"
	entry = frappe.new_doc("Stock Entry")
	entry.update({
		"stock_entry_type": purpose,
		"purpose": purpose,
		"company": company,
		"posting_date": posting_date,
		"set_posting_time": 1,
		"remarks": remarks,
		"from_warehouse" if purpose == "Material Issue" else "to_warehouse": settings.library_warehouse,
		**_links(issuance, document),
	})
	for row in rows:
		line = {
			"item_code": row["item_code"], "qty": row["qty"], "conversion_factor": 1,
			warehouse_field: settings.library_warehouse,
			"expense_account": settings.issue_expense_account,
			"cost_center": settings.default_cost_center,
		}
		if purpose == "Material Receipt":
			line["basic_rate"] = flt(row.get("basic_rate"))
			line["allow_zero_valuation_rate"] = 0 if flt(row.get("basic_rate")) else 1
		entry.append("items", line)
	_library_flags(entry)
	with as_system() as user:
		entry.run_method("set_missing_values")
		entry.insert()
		entry.submit()
	keep_owner(entry, user)
	return entry


def assert_unpaid(invoice):
	"""Refuse to cancel an invoice that has payments or credit notes against it.

	With "unlink payment on cancellation of invoice" on, ERPNext would otherwise cancel a
	paid invoice and leave its payment unallocated.
	"""
	if not invoice:
		return
	values = frappe.db.get_value("Sales Invoice", invoice,
		["docstatus", "outstanding_amount", "grand_total", "rounded_total"], as_dict=True)
	if not values or values.docstatus != 1:
		return
	total = abs(flt(values.rounded_total) or flt(values.grand_total))
	if abs(abs(flt(values.outstanding_amount)) - total) > 0.005:
		frappe.throw(_("Sales Invoice {0} has payments or credit notes against it ({1} of {2} outstanding). "
			"Use a Library Issuance Return instead of cancelling.").format(
			invoice, flt(values.outstanding_amount), total))


def cancel_document(doctype, name):
	if not name:
		return
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		_library_flags(doc)
		with as_system():
			doc.cancel()


def guard_library_document(doc, method=None):
	"""before_insert / before_cancel of Sales Invoice, Stock Entry, Stock Reconciliation."""
	if doc.flags.from_library or not any(doc.get(f) for f in LINK_FIELDS):
		return
	source = (f"{doc.library_document_type} {doc.library_document}" if doc.get("library_document")
		else f"Library Book Issuance {doc.library_issuance}")
	if method == "before_cancel":
		frappe.throw(_("{0} {1} belongs to {2}; cancel or return it there.").format(doc.doctype, doc.name, source),
			frappe.PermissionError)
	frappe.throw(_("Only the library creates documents linked to {0}.").format(source), frappe.PermissionError)


def member_customer(member):
	"""The Customer of a Student member; None for staff and other members."""
	return student_customer(frappe.db.get_value("Library Member", member, "student"))


def bill_rental(circulation):
	"""Invoice the rental fee of a submitted Issue to the student's Customer."""
	settings = get_settings()
	require(settings, "company", "rental_item", "rental_income_account", "default_cost_center")
	customer = member_customer(circulation.member)
	if not customer:
		frappe.throw(_("Rental fees are billed to a student's Customer; {0} has none.").format(
			circulation.member_name or circulation.member))
	invoice = make_sales_invoice(customer=customer, company=settings.company, posting_date=circulation.transaction_date,
		rows=[{"item_code": settings.rental_item, "qty": 1, "rate": flt(circulation.rental_fee),
			"description": _("Rental of {0} ({1})").format(circulation.book_title, circulation.book_copy)}],
		income_account=settings.rental_income_account, update_stock=False, document=circulation,
		remarks=_("Library Circulation {0}: rental of {1}").format(circulation.name, circulation.book_title))
	return invoice.name


def bill_fine(fine):
	"""Invoice a final, unpaid fine to the student's Customer; returns the invoice or None.

	Only when "Bill Fines to the Student's Account" is on and the member is a student with
	a Customer. The fine is then Invoiced: its payment is tracked on the invoice.
	"""
	if not frappe.db.get_single_value("Library Settings", "bill_fines_to_customer"):
		return None
	if fine.sales_invoice or fine.payment_status != "Unpaid" or flt(fine.paid_amount) or not flt(fine.fine_amount):
		return None
	customer = member_customer(fine.member)
	if not customer:
		return None
	settings = get_settings()
	require(settings, "company", "fine_item", "fine_income_account", "default_cost_center")
	invoice = make_sales_invoice(customer=customer, company=settings.company, posting_date=fine.fine_date,
		rows=[{"item_code": settings.fine_item, "qty": 1, "rate": flt(fine.fine_amount),
			"description": _("Library {0} fine {1}").format(fine.fine_type.lower(), fine.name)}],
		income_account=settings.fine_income_account, update_stock=False, document=fine,
		remarks=_("Library Fine {0} ({1})").format(fine.name, fine.fine_type))
	fine.db_set({"sales_invoice": invoice.name, "payment_status": "Invoiced", "outstanding_amount": 0})
	return invoice.name


@frappe.whitelist()
def bill_fine_now(fine):
	"""Form button: invoice an unpaid fine now (when fine billing is on)."""
	doc = frappe.get_doc("Library Fine", fine)
	doc.check_permission("write")
	if not frappe.db.get_single_value("Library Settings", "bill_fines_to_customer"):
		frappe.throw(_("Fine billing is off in Library Settings."))
	if not member_customer(doc.member):
		frappe.throw(_("{0} is not a student with a Customer.").format(doc.member_name or doc.member))
	invoice = bill_fine(doc)
	if not invoice:
		frappe.throw(_("Only an unpaid fine with an amount can be billed."))
	from library.library.stats import update_member_stats

	update_member_stats(doc.member)
	return invoice


def make_credit_note(*, original_invoice, quantities, posting_date, issuance=None, document=None, remarks=None):
	"""Insert and submit a credit note against a library invoice for some of its items.

	quantities: {item_code: qty returned}. Built with ERPNext's make_return_doc, so each line
	refers to the original invoice line and stock goes back into the original warehouse.
	"""
	from erpnext.controllers.sales_and_purchase_return import make_return_doc

	wanted = defaultdict(float, {k: flt(v) for k, v in quantities.items()})
	with as_system() as user:
		credit = make_return_doc("Sales Invoice", original_invoice)
		kept = []
		for line in credit.items:
			take = min(wanted[line.item_code], abs(flt(line.qty)))
			if take > 0:
				line.qty = -take
				line.stock_qty = -take * flt(line.conversion_factor or 1)
				wanted[line.item_code] -= take
				kept.append(line)
		if any(qty > 0.0001 for qty in wanted.values()):
			frappe.throw(_("Invoice {0} does not have enough of these items to credit.").format(original_invoice))
		for idx, line in enumerate(kept, start=1):
			line.idx = idx
		credit.set("items", kept)
		credit.update({"posting_date": posting_date, "set_posting_time": 1, "remarks": remarks, **_links(issuance, document)})
		_library_flags(credit)
		credit.run_method("calculate_taxes_and_totals")
		credit.insert()
		credit.submit()
	keep_owner(credit, user)
	return credit


def make_stock_reconciliation(*, rows, company, posting_date, document, remarks=None):
	"""Insert and submit a Stock Reconciliation setting library-warehouse quantities to the counted ones.

	rows: dicts with item_code, qty (counted) and valuation_rate.
	"""
	settings = get_settings()
	require(settings, "library_warehouse", "default_cost_center")
	reconciliation = frappe.new_doc("Stock Reconciliation")
	reconciliation.update({
		"company": company, "purpose": "Stock Reconciliation", "posting_date": posting_date, "set_posting_time": 1,
		"expense_account": frappe.get_cached_value("Company", company, "stock_adjustment_account"),
		"cost_center": settings.default_cost_center, **_links(None, document),
	})
	for row in rows:
		reconciliation.append("items", {
			"item_code": row["item_code"], "warehouse": settings.library_warehouse, "qty": flt(row["qty"]),
			"valuation_rate": flt(row.get("valuation_rate")),
			"allow_zero_valuation_rate": 0 if flt(row.get("valuation_rate")) else 1,
		})
	_library_flags(reconciliation)
	with as_system() as user:
		reconciliation.insert()
		reconciliation.submit()
	keep_owner(reconciliation, user)
	return reconciliation
