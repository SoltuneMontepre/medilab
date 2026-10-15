{
    "name": "Medilab - Inventory",
    "version": "20.0.1.0.0",
    "summary": "Manage stock, expiry, material movement and suppliers for testing centers",
    "category": "Services/Laboratory",
    "icon": "/sol_inventory/static/description/icon.svg",
    "author": "Soltune Montepre",
    "license": "LGPL-3",
    "depends": ["sol_laboratory", "stock_account", "product_expiry", "purchase_stock"],
    "data": [
        "data/permission_data.xml",
        "data/account_analytic_plan_data.xml",
        "views/stores/stock_location_views.xml",
        "views/costs/account_analytic_account_views.xml",
        "views/system/menus.xml",
    ],
    "application": True,
}
