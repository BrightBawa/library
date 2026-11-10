frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Library Issuances by Class"] = {
	method: "library.library.dashboard_chart_source.library_issuances_by_class.library_issuances_by_class.get",
	filters: [],
};
