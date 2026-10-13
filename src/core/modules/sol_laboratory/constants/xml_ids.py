"""External ids that Python code of the Laboratory module refers to."""

MODULE = "sol_laboratory"
ADMINISTRATOR_GROUP = "sol_laboratory.group_role_administrator"
ADMINISTRATOR_ROLE = "sol_laboratory.role_administrator"
ADMINISTRATOR_PERSON = "sol_laboratory.person_administrator"
# Only people who can read test requests see the customer and the customer's name for a sample.
TEST_REQUEST_READER_GROUP = "sol_laboratory.group_permission_test_request_read_all"
# Only people who maintain customers read a customer's citizen ID.
CUSTOMER_EDITOR_GROUP = "sol_laboratory.group_permission_customer_edit_all"
SAMPLE_LABEL_REPORT = "sol_laboratory.action_report_sample_label"
HANDOVER_RECORD_REPORT = "sol_laboratory.action_report_handover_record"
DEPARTMENTS_MENU = "hr.menu_hr_department_kanban"
