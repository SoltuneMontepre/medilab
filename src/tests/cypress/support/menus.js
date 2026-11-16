// The back-office menus the main paths open as a user does, by external ID: an app, its sections and their entries.
export const MENU = {
  sales: "sale.sale_menu_root",
  unclaimedOrders: "sol_commerce.menu_sale_order_queue",
  orders: "sol_commerce.menu_sale_order",
  laboratory: "sol_laboratory.menu_laboratory_root",
  requests: "sol_laboratory.menu_laboratory_requests",
  testRequests: "sol_laboratory.menu_test_request",
  samples: "sol_laboratory.menu_laboratory_samples",
  sampleList: "sol_laboratory.menu_sample",
  sampleTests: "sol_laboratory.menu_sample_test",
  handoverRecords: "sol_laboratory.menu_handover_record",
  scanLabel: "sol_laboratory.menu_sample_scan",
  results: "sol_laboratory.menu_laboratory_results",
  testResults: "sol_laboratory.menu_test_result",
  schedule: "sol_laboratory.menu_laboratory_schedule",
  machineSchedule: "sol_laboratory.menu_machine_booking",
  outsourcingSuggestions: "sol_laboratory.menu_outsourcing_suggestion",
  outsourcingSchedule: "sol_laboratory.menu_outsourcing_schedule",
  dispatchesToCarry: "sol_laboratory.menu_dispatch_to_carry",
  tasks: "sol_laboratory.menu_tasks_root",
  departmentQueue: "sol_laboratory.menu_task_queue",
  myTasks: "sol_laboratory.menu_task_mine",
  calendar: "calendar.mail_menu_calendar",
};

// The links of the portal's header menu.
export const PORTAL_MENU = "ul.o_medilab_portal_navigation";
