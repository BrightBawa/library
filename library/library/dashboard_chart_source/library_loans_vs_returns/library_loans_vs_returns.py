# Copyright (c) 2025, GCIHS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, getdate, today

from library.library import school

@frappe.whitelist()
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
		timespan=None, time_interval=None, heatmap_year=None):
	"""Loans issued and returned per month, last twelve months."""
	frappe.has_permission("Library Circulation", "read", throw=True)
	first = get_first_day(add_months(today(), -11))
	months = [add_months(first, i) for i in range(12)]
	counts = {(t, getdate(m).strftime("%Y-%m")): n for t, m, n in frappe.db.sql("""
		select transaction_type, date_format(transaction_date, '%%Y-%%m-01'), count(*) from `tabLibrary Circulation`
		where docstatus = 1 and transaction_type in ('Issue', 'Return') and transaction_date >= %s
		group by transaction_type, date_format(transaction_date, '%%Y-%%m-01')""", first)}
	keys = [getdate(m).strftime("%Y-%m") for m in months]
	return {
		"labels": [getdate(m).strftime("%b %Y") for m in months],
		"datasets": [
			{"name": _("Loans"), "values": [counts.get(("Issue", k), 0) for k in keys]},
			{"name": _("Returns"), "values": [counts.get(("Return", k), 0) for k in keys]},
		],
	}
