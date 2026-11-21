{
    "name": "Medilab Sessions",
    "version": "20.0.1.0.0",
    "summary": "Keeps sign-in sessions in the database, so every Odoo process and every release serves them.",
    "category": "Hidden/Tools",
    "author": "Soltune Montepre",
    "license": "LGPL-3",
    "depends": ["base"],
    "post_load": "use_database_sessions",
}
