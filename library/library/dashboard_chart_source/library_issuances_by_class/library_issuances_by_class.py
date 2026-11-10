# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from library.library import school


@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
		timespan=None, time_interval=None, heatmap_year=None):
	"""Issuances this academic year by class; students with no class on record are grouped together."""
	frappe.has_permission("Library Book Issuance", "read", throw=True)
	rows = frappe.db.sql("""select ifnull(student_batch, ''), count(*) from `tabLibrary Book Issuance`
		where docstatus = 1 and academic_year = %s group by student_batch order by count(*) desc limit 15""",
		school.current_academic_year())
	return {"labels": [r[0] or _("No class") for r in rows], "datasets": [{"name": _("Issuances"), "values": [flt(r[1]) for r in rows]}]}
