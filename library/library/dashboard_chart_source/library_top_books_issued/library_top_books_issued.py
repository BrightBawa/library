# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, today

from library.library import school

@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
		timespan=None, time_interval=None, heatmap_year=None):
	"""The ten books issued most this academic year (copies issued)."""
	frappe.has_permission("Library Book Issuance", "read", throw=True)
	rows = frappe.db.sql("""select r.book_title, sum(r.qty - ifnull(r.returned_qty, 0)) qty
		from `tabLibrary Book Issuance Item` r join `tabLibrary Book Issuance` i on i.name = r.parent
		where i.docstatus = 1 and i.academic_year = %s group by r.book, r.book_title
		order by qty desc limit 10""", school.current_academic_year())
	return {"labels": [r[0] for r in rows], "datasets": [{"name": _("Copies issued"), "values": [flt(r[1]) for r in rows]}]}
