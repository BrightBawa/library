# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, today

from library.library import school

@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
		timespan=None, time_interval=None, heatmap_year=None):
	"""Books on hand by category: Issue-type stock in the library warehouse plus lending copies on the shelf."""
	frappe.has_permission("Library Book", "read", throw=True)
	warehouse = frappe.db.get_single_value("Library Settings", "library_warehouse")
	totals = {}
	if warehouse:
		for category, qty in frappe.db.sql("""select ifnull(lb.category, ''), sum(b.actual_qty) from tabBin b
				join `tabLibrary Book` lb on lb.item = b.item_code and lb.book_type = 'Issue'
				where b.warehouse = %s group by lb.category""", warehouse):
			totals[category] = totals.get(category, 0) + flt(qty)
	for category, qty in frappe.db.sql("""select ifnull(lb.category, ''), count(*) from `tabLibrary Book Copy` c
			join `tabLibrary Book` lb on lb.name = c.book where c.status = 'Available' group by lb.category"""):
		totals[category] = totals.get(category, 0) + flt(qty)
	labels = sorted(totals, key=lambda c: -totals[c])
	return {"labels": [c or _("No category") for c in labels],
		"datasets": [{"name": _("Books on hand"), "values": [totals[c] for c in labels]}]}
