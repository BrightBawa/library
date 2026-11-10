# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, today

from library.library import school

@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
		timespan=None, time_interval=None, heatmap_year=None):
	"""Books issued this academic year: billed against free, net of returns."""
	frappe.has_permission("Library Book Issuance", "read", throw=True)
	year = school.current_academic_year()
	issued = frappe.db.sql("""select coalesce(sum(total_billable_qty), 0), coalesce(sum(total_free), 0)
		from `tabLibrary Book Issuance` where docstatus = 1 and academic_year = %s""", year)[0]
	billed, free = flt(issued[0]), flt(issued[1])
	if frappe.db.exists("DocType", "Library Issuance Return"):
		returned = frappe.db.sql("""select coalesce(sum(r.total_billable_qty), 0), coalesce(sum(r.total_free), 0)
			from `tabLibrary Issuance Return` r join `tabLibrary Book Issuance` i on i.name = r.against_issuance
			where r.docstatus = 1 and i.academic_year = %s""", year)[0]
		billed, free = billed - flt(returned[0]), free - flt(returned[1])
	return {"labels": [_("Billed"), _("Free")], "datasets": [{"name": _("Books"), "values": [billed, free]}]}
