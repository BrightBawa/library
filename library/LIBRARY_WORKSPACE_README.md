# Library Workspace Documentation

## Overview

The Library Workspace provides a comprehensive dashboard and interface for managing the GCIHS Library system. It includes real-time statistics, quick access shortcuts, interactive charts, and streamlined navigation to all library-related functions.

## Features

### 📊 Number Cards (KPIs)

The workspace displays 8 key performance indicators:

1. **Total Books** (Blue)
   - Counts all books in the library catalog
   - Shows monthly trend
   - Color: #3498db

2. **Available Books** (Green)
   - Sum of all available book copies across all titles
   - Shows monthly trend
   - Color: #2ecc71

3. **Issued Books** (Orange)
   - Current count of books checked out to members
   - Shows daily trend
   - Color: #f39c12

4. **Overdue Books** (Red)
   - Books not returned by due date
   - Dynamic filter: updates daily based on current date
   - Color: #e74c3c

5. **Active Members** (Purple)
   - Members with active membership status
   - Shows monthly trend
   - Color: #9b59b6

6. **Total Members** (Dark Grey)
   - All registered library members
   - Shows monthly trend
   - Color: #34495e

7. **Outstanding Fines** (Dark Orange)
   - Total amount of unpaid/partially paid fines
   - Shows weekly trend
   - Color: #e67e22

8. **Active Reservations** (Teal)
   - Books currently reserved or awaiting pickup
   - Shows daily trend
   - Color: #1abc9c

### 🎯 Quick Shortcuts

10 quick action shortcuts for common tasks:

1. **Library Statistics** - Opens the library dashboard
2. **Issue Book** - Quick access to issue book form
3. **Return Book** - Quick access to return book form
4. **Renew Book** - Quick access to renewal form
5. **Books** - Navigate to book catalog
6. **Members** - Navigate to member list
7. **Overdue Books** - View overdue items report
8. **Fines** - Manage library fines
9. **Reservations** - Manage book reservations
10. **Settings** - Library configuration

### 📈 Dashboard Charts

4 interactive charts for data visualization:

1. **Circulation Trend** (Line Chart)
   - Shows daily circulation patterns (issues, returns, renewals)
   - Time period: Last month
   - Grouped by transaction type
   - Color: #7cd6fd

2. **Category Distribution** (Donut Chart)
   - Displays book distribution across categories
   - Helps identify collection strengths and gaps
   - Color: #5e64ff

3. **Member Activity** (Bar Chart)
   - Monthly member registration trends
   - Grouped by membership type
   - Time period: Last 6 months
   - Color: #fc4f51

4. **Fine Collection** (Line Chart)
   - Weekly fine collection trends
   - Shows payment status breakdown
   - Time period: Last 3 months
   - Color: #29cd42

### 🔗 Quick Lists

3 organized quick access lists:

1. **Books & Inventory**
   - Library Books
   - Book Copies
   - Categories

2. **Members & Circulation**
   - Library Members
   - Circulation records
   - Reservations

3. **Reports & Analytics**
   - Various library reports
   - Member activity
   - Fine reports

### 📚 Direct Links

Quick access to all library doctypes:

- Library Book
- Library Book Copy
- Library Category
- Library Member
- Library Circulation
- Library Reservation
- Library Fine
- Library Membership Type
- Library Settings

## Installation

The workspace is automatically installed when you:

1. **Install the GCIHS App** - Runs on `after_install` hook
2. **Run Bench Migrate** - Runs on `after_migrate` hook

### Manual Installation/Update

If you need to manually reload the workspace:

```bash
# From bench directory
cd gcihs-bench

# Option 1: Reinstall fixtures
bench --site [your-site] migrate

# Option 2: Export and reimport
bench --site [your-site] export-fixtures
bench --site [your-site] import-fixtures
```

### Using Python Console

```python
# Login to site
bench --site [your-site] console

# Execute setup
import frappe
from gcihs_app.install import setup_library_workspace

setup_library_workspace()
frappe.db.commit()
```

## Configuration

### Customizing Number Cards

Number cards can be customized by editing the JSON files in:
```
gcihs_app/library/number_card/[card_name]/[card_name].json
```

Available customizations:
- `color`: Hex color code
- `filters_json`: Static filters
- `dynamic_filters_json`: Dynamic filters (e.g., "Today", "This Month")
- `stats_time_interval`: Daily, Weekly, Monthly, Yearly
- `show_percentage_stats`: 0 or 1

### Customizing Charts

Charts can be customized by editing the JSON files in:
```
gcihs_app/library/dashboard_chart/[chart_name]/[chart_name].json
```

Available chart types:
- Line
- Bar
- Donut
- Pie
- Percentage
- Heatmap

### Customizing Shortcuts

Shortcuts are defined in the workspace JSON:
```
gcihs_app/library/workspace/library/library.json
```

Shortcut properties:
- `label`: Display name
- `type`: DocType, Report, Page, Dashboard
- `link_to`: Target document
- `icon`: Feather icon name
- `color`: Visual identifier

### Adding Custom Links

To add new links to the workspace, edit the `links` array in the workspace JSON file.

## File Structure

```
gcihs_app/library/
├── workspace/
│   └── library/
│       ├── __init__.py
│       └── library.json
├── dashboard/
│   └── library_dashboard/
│       ├── __init__.py
│       └── library_dashboard.json
├── dashboard_chart/
│   ├── circulation_trend/
│   │   ├── __init__.py
│   │   └── circulation_trend.json
│   ├── category_distribution/
│   │   ├── __init__.py
│   │   └── category_distribution.json
│   ├── member_activity/
│   │   ├── __init__.py
│   │   └── member_activity.json
│   └── fine_collection/
│       ├── __init__.py
│       └── fine_collection.json
└── number_card/
    ├── total_books/
    │   ├── __init__.py
    │   └── total_books.json
    ├── available_books/
    │   ├── __init__.py
    │   └── available_books.json
    ├── issued_books/
    │   ├── __init__.py
    │   └── issued_books.json
    ├── overdue_books/
    │   ├── __init__.py
    │   └── overdue_books.json
    ├── active_members/
    │   ├── __init__.py
    │   └── active_members.json
    ├── total_members/
    │   ├── __init__.py
    │   └── total_members.json
    ├── outstanding_fines/
    │   ├── __init__.py
    │   └── outstanding_fines.json
    └── active_reservations/
        ├── __init__.py
        └── active_reservations.json
```

## Hooks Configuration

The workspace components are configured in `hooks.py`:

```python
fixtures = [
    {
        "dt": "Workspace",
        "filters": [["name", "in", ["Library"]]]
    },
    {
        "dt": "Dashboard",
        "filters": [["name", "in", ["Library Dashboard"]]]
    },
    {
        "dt": "Dashboard Chart",
        "filters": [
            ["name", "in", ["Circulation Trend", "Category Distribution", 
                           "Member Activity", "Fine Collection"]]
        ]
    },
    {
        "dt": "Number Card",
        "filters": [
            ["name", "in", ["Total Books", "Available Books", "Issued Books", 
                           "Overdue Books", "Active Members", "Total Members", 
                           "Outstanding Fines", "Active Reservations"]]
        ]
    }
]
```

## Troubleshooting

### Workspace Not Appearing

1. **Clear cache:**
   ```bash
   bench --site [your-site] clear-cache
   ```

2. **Reload workspace:**
   ```bash
   bench --site [your-site] console
   ```
   ```python
   import frappe
   frappe.reload_doc("library", "workspace", "library")
   frappe.db.commit()
   ```

3. **Check permissions:**
   - Ensure user has access to Library module
   - Check role permissions for library doctypes

### Number Cards Not Showing Data

1. **Verify data exists:**
   - Check if library records exist in the database
   - Verify filter conditions are correct

2. **Check number card permissions:**
   - Number cards must have `is_public` set to 1
   - User must have read permissions on the document type

### Charts Not Displaying

1. **Verify chart configuration:**
   - Check if `based_on` field exists in the DocType
   - Verify `group_by_based_on` field is valid

2. **Check data filters:**
   - Ensure dynamic filters are properly formatted
   - Verify static filters match actual data

## Best Practices

1. **Regular Updates:**
   - Run `bench migrate` after app updates
   - Clear cache after configuration changes

2. **Performance:**
   - Number cards with complex filters may impact load time
   - Consider adjusting `stats_time_interval` for optimal performance

3. **Customization:**
   - Always backup workspace JSON before major changes
   - Test customizations in development before production

4. **Data Integrity:**
   - Ensure library data is complete and accurate
   - Regularly verify calculated fields (total_copies, available_copies)

## Permissions

The workspace respects Frappe's role-based permission system:

- **Librarian Role:** Full access to all features
- **Library Member Role:** Limited access (view only)
- **System Manager:** Full administrative access

Configure permissions in:
- User Role Settings
- DocType Permission Rules
- Custom permission scripts

## Support

For issues or questions:

1. Check this documentation
2. Review Frappe workspace documentation
3. Contact the development team
4. Create an issue in the repository

## Version History

- **v1.0** (2025-12-16)
  - Initial workspace creation
  - 8 number cards
  - 4 dashboard charts
  - 10 quick shortcuts
  - 9 direct links

## Future Enhancements

Planned features:
- [ ] Custom reports integration
- [ ] Advanced filtering options
- [ ] Export functionality for charts
- [ ] Mobile-optimized layout
- [ ] Customizable dashboard layouts
- [ ] Integration with notifications

---

**Last Updated:** December 16, 2025  
**Module:** Library  
**App:** GCIHS App
