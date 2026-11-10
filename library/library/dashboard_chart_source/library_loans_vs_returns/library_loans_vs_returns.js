frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Library Loans vs Returns"] = {
	method: "library.library.dashboard_chart_source.library_loans_vs_returns.library_loans_vs_returns.get",
	filters: [],
};
