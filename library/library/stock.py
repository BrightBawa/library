"""Library stock: the library warehouse, items for Issue-type books, rates and stock requests.

Lending books are counted by their Library Book Copy records. Issue-type books (the
student keeps them) are ERPNext stock items whose quantity is the Bin balance in the
library warehouse.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, today

WAREHOUSE_FIELDS = ("warehouse", "s_warehouse", "t_warehouse", "set_warehouse", "from_warehouse")


def get_settings():
	return frappe.get_single("Library Settings")


def require(settings, *fields):
	missing = [settings.meta.get_label(f) for f in fields if not settings.get(f)]
	if missing:
		frappe.throw(_("Set {0} in Library Settings first.").format(", ".join(missing)))


def warehouse_qty(item, warehouse=None):
	warehouse = warehouse or frappe.db.get_single_value("Library Settings", "library_warehouse")
	if not item or not warehouse:
		return 0
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


def make_book_item(book):
	"""Create the stock Item for an Issue-type Library Book and return its name."""
	settings = get_settings()
	require(settings, "library_item_group")
	item = frappe.new_doc("Item")
	if frappe.db.get_single_value("Stock Settings", "item_naming_by") == "Item Code":
		item.item_code = book.name
	item.update({
		"item_name": (book.book_title or "")[:140],
		"item_group": settings.library_item_group,
		"stock_uom": frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos",
		"is_stock_item": 1,
		"is_sales_item": 1,
		"is_purchase_item": 1,
		"include_item_in_manufacturing": 0,
		"description": ", ".join(filter(None, [book.book_title, book.author, book.isbn])),
	})
	from library.library.billing import as_system, keep_owner

	with as_system() as user:  # Item validation reads masters with the session user's rights
		item.insert(ignore_permissions=True)
	keep_owner(item, user)
	return item.name


def item_rate(item, price_list=None):
	price_list = price_list or frappe.db.get_single_value("Library Settings", "selling_price_list")
	if not item or not price_list:
		return 0
	return flt(frappe.db.get_value(
		"Item Price",
		{"item_code": item, "price_list": price_list, "selling": 1},
		"price_list_rate",
		order_by="valid_from desc, creation desc",
	))


@frappe.whitelist()
def make_stock_request(source_name=None, target_doc=None, books=None):
	"""An unsaved Material Request (Material Transfer, stores -> library) for Issue-type books.

	The user saves and submits it through the normal Material Request workflow, with
	their own Material Request rights.
	"""
	if frappe.session.user != "Administrator" and not {"Library Manager", "System Manager"} & set(frappe.get_roles()):
		frappe.throw(_("Only a Library Manager can request stock from stores."), frappe.PermissionError)
	frappe.has_permission("Material Request", "create", throw=True)
	names = frappe.parse_json(books) if books else [source_name]
	settings = get_settings()
	require(settings, "company", "library_warehouse", "stores_warehouse")
	schedule_date = add_days(today(), 7)
	request = frappe.new_doc("Material Request")
	request.update({
		"material_request_type": "Material Transfer",
		"company": settings.company,
		"transaction_date": today(),
		"schedule_date": schedule_date,
		"set_from_warehouse": settings.stores_warehouse,
		"set_warehouse": settings.library_warehouse,
	})
	for name in names:
		book = frappe.get_doc("Library Book", name)
		book.check_permission("read")
		if book.book_type != "Issue" or not book.item:
			frappe.throw(_("{0} is not an Issue-type book with an item, so it is not stocked.").format(book.book_title))
		uom = frappe.db.get_value("Item", book.item, "stock_uom")
		request.append("items", {
			"item_code": book.item, "item_name": book.book_title[:140], "description": book.book_title,
			"qty": 1, "uom": uom, "stock_uom": uom, "conversion_factor": 1, "schedule_date": schedule_date,
			"from_warehouse": settings.stores_warehouse, "warehouse": settings.library_warehouse,
		})
	return request


def refresh_books_for_items(items):
	if not items:
		return
	from library.library.stats import update_book_stats

	for book in frappe.get_all("Library Book", filters={"item": ["in", list(items)], "book_type": "Issue"}, pluck="name"):
		update_book_stats(book)


def refresh_books_after_stock_change(doc, method=None):
	"""on_submit / on_cancel of stock documents: refresh Issue-type books moved in or out of the library."""
	warehouse = frappe.db.get_single_value("Library Settings", "library_warehouse")
	if not warehouse:
		return
	items = set()
	for row in doc.get("items") or []:
		if any(row.get(f) == warehouse for f in WAREHOUSE_FIELDS) or doc.get("set_warehouse") == warehouse:
			items.add(row.item_code)
	refresh_books_for_items(items)


def refresh_all_issue_books():
	"""Daily: catch stock moved by documents the hooks do not watch."""
	refresh_books_for_items(set(frappe.get_all("Library Book", filters={"book_type": "Issue", "item": ["is", "set"]}, pluck="item")))
