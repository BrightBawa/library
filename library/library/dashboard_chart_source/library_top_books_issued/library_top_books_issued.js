frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Library Top Books Issued"] = {
	method: "library.library.dashboard_chart_source.library_top_books_issued.library_top_books_issued.get",
	filters: [],
};
