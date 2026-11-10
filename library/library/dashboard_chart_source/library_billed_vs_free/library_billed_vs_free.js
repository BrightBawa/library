frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Library Billed vs Free"] = {
	method: "library.library.dashboard_chart_source.library_billed_vs_free.library_billed_vs_free.get",
	filters: [],
};
