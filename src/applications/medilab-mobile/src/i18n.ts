export type Locale = "vi" | "en";

export const LOCALES: readonly Locale[] = ["vi", "en"];

// Every string the app shows, in Vietnamese and English.
const messages = {
  "home.server": { vi: "Máy chủ: {url}", en: "Server: {url}" },
  "home.signedInAs": { vi: "Xin chào, {name}", en: "Hello, {name}" },
  "language.vi": { vi: "Tiếng Việt", en: "Tiếng Việt" },
  "language.en": { vi: "English", en: "English" },
  "signIn.title": { vi: "Đăng nhập MediLab", en: "Sign in to MediLab" },
  "signIn.server": { vi: "Địa chỉ MediLab", en: "MediLab address" },
  "signIn.login": { vi: "Tên đăng nhập", en: "Login" },
  "signIn.password": { vi: "Mật khẩu", en: "Password" },
  "signIn.submit": { vi: "Đăng nhập", en: "Sign in" },
  "signIn.missing": { vi: "Nhập tên đăng nhập và mật khẩu.", en: "Enter your login and password." },
  "server.invalid": {
    vi: "Địa chỉ MediLab phải bắt đầu bằng https://.",
    en: "The MediLab address must start with https://.",
  },
  "server.invalidDevelopment": {
    vi: "Địa chỉ MediLab phải bắt đầu bằng http:// hoặc https://.",
    en: "The MediLab address must start with http:// or https://.",
  },
  "signOut.submit": { vi: "Đăng xuất", en: "Sign out" },
  "unreachable.message": {
    vi: "Không kết nối được MediLab, nên chưa có gì thay đổi. Kiểm tra kết nối rồi thử lại.",
    en: "MediLab cannot be reached, so nothing was changed. Check the connection and try again.",
  },
  "unreachable.retry": { vi: "Thử lại", en: "Try again" },
  "home.notifications": { vi: "Thông báo", en: "Notifications" },
  "home.notificationSettings": { vi: "Cài đặt thông báo", en: "Notification settings" },
  "notifications.title": { vi: "Thông báo", en: "Notifications" },
  "notifications.empty": { vi: "Chưa có thông báo nào.", en: "There are no notifications." },
  "notifications.unread": { vi: "Chưa đọc", en: "Unread" },
  "more": { vi: "Xem thêm", en: "Show more" },
  "document.gone": {
    vi: "Bạn không còn xem được tài liệu này, hoặc tài liệu đã bị xoá.",
    en: "You can no longer see this document, or it was deleted.",
  },
  "document.openOnWeb": { vi: "Mở trên web", en: "Open on the web" },
  "settings.title": { vi: "Cài đặt thông báo", en: "Notification settings" },
  "settings.explanation": {
    vi: "Chọn sự kiện nào được gửi lên điện thoại. Sự kiện bắt buộc luôn được gửi.",
    en: "Choose which events are pushed to your phone. Mandatory events are always pushed.",
  },
  "settings.mandatory": { vi: "Bắt buộc", en: "Mandatory" },
  "home.todo": { vi: "Việc cần làm", en: "To-do list" },
  "home.newTask": { vi: "Tạo nhiệm vụ", en: "New task" },
  "day.summary": {
    vi: "{open} việc đang mở, {overdue} việc quá hạn, {today} việc đến hạn hôm nay",
    en: "{open} open, {overdue} overdue, {today} due today",
  },
  "day.plannedToday": { vi: "Kế hoạch hôm nay", en: "Planned today" },
  "day.nextUp": { vi: "Việc tiếp theo", en: "Next up" },
  "day.nothingToDo": { vi: "Bạn không có việc nào đang mở.", en: "You have no open tasks." },
  "day.claimable": { vi: "Đang chờ trong hàng đợi ({count})", en: "Waiting in your queues ({count})" },
  "day.seeQueue": { vi: "Xem hàng đợi", en: "See the queue" },
  "tasks.title": { vi: "Việc cần làm", en: "To-do list" },
  "tasks.open": { vi: "Đang mở", en: "Open" },
  "tasks.finished": { vi: "Đã xong", en: "Finished" },
  "tasks.queue": { vi: "Hàng đợi", en: "Queue" },
  "tasks.openEmpty": { vi: "Bạn không có việc nào đang mở.", en: "You have no open tasks." },
  "tasks.finishedEmpty": { vi: "Bạn chưa hoàn thành việc nào.", en: "You have not finished any task." },
  "tasks.queueEmpty": { vi: "Không có việc nào đang chờ nhận.", en: "No task is waiting to be claimed." },
  "task.status.open": { vi: "Chờ nhận", en: "Open" },
  "task.status.assigned": { vi: "Đã giao", en: "Assigned" },
  "task.status.in_progress": { vi: "Đang làm", en: "In progress" },
  "task.status.done": { vi: "Đã xong", en: "Done" },
  "task.status.cancelled": { vi: "Đã huỷ", en: "Cancelled" },
  "task.deadline": { vi: "Hạn {date}", en: "Due {date}" },
  "task.doneAt": { vi: "Xong lúc {date}", en: "Done {date}" },
  "task.gone": {
    vi: "Bạn không còn xem được nhiệm vụ này, hoặc nhiệm vụ đã bị xoá.",
    en: "You can no longer see this task, or it was deleted.",
  },
  "task.claim": { vi: "Nhận việc", en: "Claim" },
  "task.start": { vi: "Bắt đầu", en: "Start" },
  "task.done": { vi: "Đánh dấu xong", en: "Mark done" },
  "task.assign": { vi: "Giao việc", en: "Assign" },
  "task.openDocument": { vi: "Mở {code}", en: "Open {code}" },
  "task.type": { vi: "Loại", en: "Type" },
  "task.statusLabel": { vi: "Trạng thái", en: "Status" },
  "task.deadlineLabel": { vi: "Hạn chót", en: "Deadline" },
  "task.planned": { vi: "Bắt đầu dự kiến", en: "Planned start" },
  "task.plannedEnd": { vi: "Kết thúc dự kiến", en: "Planned end" },
  "task.doneAtLabel": { vi: "Hoàn thành lúc", en: "Done at" },
  "task.department": { vi: "Phòng ban", en: "Department" },
  "task.assignee": { vi: "Người thực hiện", en: "Assignee" },
  "task.assignedBy": { vi: "Người giao", en: "Assigned by" },
  "task.location": { vi: "Nơi lấy mẫu", en: "Sampling location" },
  "task.reason": { vi: "Lý do chuyển", en: "Reason for the move" },
  "task.steps": { vi: "Các bước của phương pháp", en: "Method steps" },
  "task.step": { vi: "Bước {number} · {minutes} phút", en: "Step {number} · {minutes} min" },
  "task.stepLocation": { vi: "Tại: {location}", en: "At: {location}" },
  "assignee.label": { vi: "Giao cho", en: "Assign to" },
  "assignee.chosen": { vi: "Đã chọn: {name}", en: "Chosen: {name}" },
  "assignee.search": { vi: "Tìm theo tên", en: "Search by name" },
  "assignee.find": { vi: "Tìm", en: "Find" },
  "assignee.none": { vi: "Không tìm thấy ai.", en: "Nobody is found." },
  "assignee.queueOf": { vi: "Hàng đợi {department}", en: "{department} queue" },
  "assign.title": { vi: "Giao việc", en: "Assign the task" },
  "assign.current": { vi: "Hiện tại: {who}", en: "Now: {who}" },
  "assign.reason": { vi: "Lý do", en: "Reason" },
  "assign.reasonHint": {
    vi: "Cần lý do khi chuyển việc sang người hoặc phòng ban khác.",
    en: "A reason is needed to move the task to another person or department.",
  },
  "assign.submit": { vi: "Giao", en: "Assign" },
  "newTask.title": { vi: "Tạo nhiệm vụ", en: "New task" },
  "newTask.name": { vi: "Tên nhiệm vụ", en: "Task name" },
  "newTask.note": { vi: "Ghi chú", en: "Note" },
  "newTask.deadline": { vi: "Hạn chót", en: "Deadline" },
  "newTask.deadlineHint": { vi: "Theo dạng 2026-11-12 17:00, giờ của điện thoại.", en: "As 2026-11-12 17:00, in the phone's time." },
  "newTask.missing": { vi: "Nhập tên nhiệm vụ và chọn người thực hiện.", en: "Enter the task name and choose the assignee." },
  "newTask.invalidDeadline": { vi: "Hạn chót không phải ngày giờ hợp lệ.", en: "The deadline is not a valid date and time." },
  "newTask.submit": { vi: "Tạo", en: "Create" },
  "back": { vi: "Quay lại", en: "Back" },
  "loading": { vi: "Đang tải...", en: "Loading..." },
} as const satisfies Record<string, Record<Locale, string>>;

export type MessageKey = keyof typeof messages;

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Translates a message into the locale and fills in its `{name}` variables. */
export function translate(locale: Locale, key: MessageKey, vars?: Record<string, string | number>): string {
  let text: string = messages[key][locale];
  for (const [name, value] of Object.entries(vars ?? {})) {
    text = text.split(`{${name}}`).join(String(value));
  }
  return text;
}

export function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value);
}
