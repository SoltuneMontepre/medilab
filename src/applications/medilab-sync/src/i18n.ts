export type Locale = "vi" | "en";

/** Chuẩn hóa một giá trị locale bất kỳ về "en" hoặc "vi" (mặc định "vi"). */
export function normalizeLocale(value: string | null | undefined): Locale {
  return value === "en" ? "en" : "vi";
}

/** Cú pháp gọn để khai báo một cặp thông điệp vi/en. */
function viEn<V extends string, E extends string>(vi: V, en: E) {
  return { vi, en } as const;
}

const messages = {
  "app.title": { vi: "Đồng bộ tệp phòng lab", en: "Lab file sync" },
  "app.technician": { vi: "Kỹ thuật viên", en: "Technician" },
  "app.degraded": { vi: "Chế độ quét định kỳ", en: "Periodic scan mode" },
  "app.paused": { vi: "Đã tạm dừng", en: "Paused" },
  "login.subtitle": {
    vi: "Đăng nhập Odoo để đăng ký thiết bị và bắt đầu tải lên.",
    en: "Sign in to Odoo to register this device and start uploading.",
  },
  "login.sessionExpired": {
    vi: "Phiên đăng nhập đã hết hạn hoặc thiết bị này đã bị thu hồi. Vui lòng đăng nhập lại.",
    en: "Your session expired or this device was revoked. Please sign in again.",
  },
  "login.odooUrl": { vi: "Địa chỉ máy chủ", en: "Server address" },
  "login.odooUrl.history": { vi: "Chọn địa chỉ đã dùng", en: "Pick a previously used address" },
  "login.account": { vi: "Tài khoản", en: "Username" },
  "login.password": { vi: "Mật khẩu", en: "Password" },
  "login.submit": { vi: "Đăng nhập", en: "Sign in" },
  "login.language": { vi: "Ngôn ngữ", en: "Language" },
  "tab.status": { vi: "Trạng thái", en: "Status" },
  "tab.folders": { vi: "Thư mục", en: "Folders" },
  "tab.settings": { vi: "Cài đặt", en: "Settings" },
  "action.pause": { vi: "Tạm dừng", en: "Pause" },
  "action.resume": { vi: "Tiếp tục", en: "Resume" },
  "action.logout": { vi: "Đăng xuất", en: "Sign out" },
  "action.close": { vi: "Đóng", en: "Close" },
  "action.cancel": { vi: "Hủy", en: "Cancel" },
  "action.retry": { vi: "Thử lại", en: "Retry" },
  "card.synced": { vi: "Đã đồng bộ", en: "Synced" },
  "card.uploading": { vi: "Đang tải lên", en: "Uploading" },
  "card.downloading": { vi: "Đang tải xuống", en: "Downloading" },
  "card.pending": { vi: "Đang chờ", en: "Waiting" },
  "card.failed": { vi: "Lỗi", en: "Errors" },
  "card.conflict": { vi: "Xung đột", en: "Conflicts" },
  "card.paused": { vi: "Tạm dừng", en: "Paused" },
  "files.title": { vi: "Tệp đã đồng bộ", en: "Synced files" },
  "files.col.file": { vi: "Tệp", en: "File" },
  "files.col.status": { vi: "Trạng thái", en: "Status" },
  "files.empty": { vi: "Chưa có tệp nào trên máy chủ.", en: "No files on the server yet." },
  "jobs.title": viEn("Hàng đợi đồng bộ", "Sync queue"),
  "jobs.col.progress": viEn("Tiến độ", "Progress"),
  "jobs.empty": viEn("Chưa có công việc đồng bộ.", "No sync jobs yet."),
  "folders.patternHint.prefix": viEn(
    "Ví dụ: nhập ABC để chỉ đồng bộ các tệp có tên bắt đầu bằng ABC.",
    "For example: enter ABC to sync only files whose name starts with ABC.",
  ),
  "folders.patternHint.glob": viEn(
    "Dấu * thay cho phần bất kỳ của tên. Ví dụ: ABC*.xlsx lấy các tệp Excel có tên bắt đầu bằng ABC.",
    "* stands for any part of the name. For example: ABC*.xlsx picks Excel files whose name starts with ABC.",
  ),
  "folders.patternHint.extension": viEn(
    "Ví dụ: nhập xlsx để chỉ đồng bộ tệp Excel, hoặc pdf để chỉ đồng bộ tệp PDF.",
    "For example: enter xlsx to sync only Excel files, or pdf to sync only PDF files.",
  ),
  "folders.dropHint": viEn(
    "Bạn cũng có thể kéo thả thư mục vào khung này.",
    "You can also drag a folder into this panel.",
  ),
  "files.history": { vi: "Lịch sử phiên bản", en: "Version history" },
  "files.office": { vi: "Chỉnh sửa trực tuyến", en: "Edit online" },
  "files.keepLocal": { vi: "Giữ nguyên file cục bộ", en: "Keep local file" },
  "files.useServer": { vi: "Dùng phiên bản máy chủ", en: "Use server version" },
  "files.useServerConfirm": {
    vi: "Dùng phiên bản máy chủ? Ứng dụng sẽ sao lưu file cục bộ thành bản xung đột trước khi tải xuống.",
    en: "Use the server version? The app will copy your local file to a conflict backup before downloading.",
  },
  "status.pending": { vi: "Đang chờ", en: "Waiting" },
  "status.running": { vi: "Đang tải lên", en: "Uploading" },
  "status.retry_wait": { vi: "Đang chờ thử lại", en: "Waiting to retry" },
  "status.completed": { vi: "Đã đồng bộ", en: "Synced" },
  "status.failed": { vi: "Lỗi", en: "Error" },
  "status.conflict": { vi: "Xung đột", en: "Conflict" },
  "status.synced": { vi: "Đã đồng bộ", en: "Synced" },
  "status.access_paused": { vi: "Tạm dừng — mất quyền", en: "Paused — access lost" },
  "status.access_paused.detail": {
    vi: "Mất quyền truy cập — đồng bộ đã tạm dừng.",
    en: "Access lost — syncing is paused.",
  },
  "status.unauthenticated": { vi: "Phiên đăng nhập hết hạn", en: "Session expired" },
  "conflict.banner": { vi: "Phát hiện xung đột", en: "Conflict detected" },
  "conflict.bannerDetail": { vi: "Phát hiện xung đột: {detail}", en: "Conflict detected: {detail}" },
  "conflict.dismiss": { vi: "Đóng", en: "Close" },
  "keyring.lockedTitle": viEn(
    "Kho lưu trữ đăng nhập trên máy đang bị khóa",
    "This computer's password store is locked",
  ),
  "keyring.lockedBody": viEn(
    "Ứng dụng lưu phiên đăng nhập của bạn trong kho mật khẩu của hệ điều hành, và kho đó đang bị khóa. Hãy mở khóa kho mật khẩu (nhập mật khẩu máy khi được hỏi) rồi bấm Thử lại.",
    "The app keeps your sign-in in the operating system's password store, which is currently locked. Unlock it (enter your computer password when asked), then click Try again.",
  ),
  "keyring.lockedSafe": viEn(
    "Phiên đăng nhập của bạn chưa hết hạn và không có gì bị xóa.",
    "Your sign-in has not expired and nothing was deleted.",
  ),
  "keyring.retry": { vi: "Thử lại", en: "Try again" },
  "keyring.retrying": { vi: "Đang chờ mở khóa…", en: "Waiting for unlock…" },
  "keyring.usePassword": { vi: "Đăng nhập bằng mật khẩu", en: "Sign in with password" },
  "session.expiredBanner": { vi: "Phiên đăng nhập hết hạn", en: "Session expired" },
  "sync.error": { vi: "Lỗi đồng bộ", en: "Sync error" },
  "sync.errorDetail": { vi: "Lỗi đồng bộ: {detail}", en: "Sync error: {detail}" },
  "history.title": { vi: "Lịch sử phiên bản", en: "Version history" },
  "history.col.version": { vi: "Phiên bản", en: "Version" },
  "history.col.time": { vi: "Thời gian", en: "Time" },
  "history.col.source": { vi: "Nguồn", en: "Source" },
  "history.col.status": { vi: "Trạng thái", en: "Status" },
  "history.current": { vi: "Hiện tại", en: "Current" },
  "history.past": { vi: "Lịch sử", en: "History" },
  "history.prev": { vi: "Trước", en: "Previous" },
  "history.next": { vi: "Sau", en: "Next" },
  "history.pick": {
    vi: "Chọn một phiên bản để xem chi tiết.",
    en: "Select a version to see details.",
  },
  "history.tableHint": {
    vi: "Chọn một phiên bản để xem chi tiết hoặc khôi phục.",
    en: "Select a version to view details or restore.",
  },
  "history.alreadyCurrent": {
    vi: "Phiên bản hiện tại",
    en: "Current version",
  },
  "history.createdBy": { vi: "Người tạo", en: "Created by" },
  "history.device": { vi: "Thiết bị", en: "Device" },
  "history.size": { vi: "Dung lượng", en: "Size" },
  "history.source": { vi: "Nguồn", en: "Source" },
  "history.parent": { vi: "Phiên bản cha", en: "Parent version" },
  "history.restoredFrom": { vi: "Khôi phục từ", en: "Restored from" },
  "history.object": { vi: "Đối tượng lưu trữ", en: "Stored object" },
  "history.objectUnavailableHint": {
    vi: "Đối tượng lưu trữ của phiên bản này không còn trên máy chủ.",
    en: "The stored object for this version is no longer available on the server.",
  },
  "history.cannotRestoreClosed": {
    vi: "Thư mục hoặc mẫu đã đóng, không thể khôi phục phiên bản.",
    en: "Folder or sample is closed, cannot restore version.",
  },
  "history.restoreThis": { vi: "Khôi phục phiên bản này", en: "Restore this version" },
  "history.restoreConfirm": {
    vi: "Khôi phục phiên bản v{version}?",
    en: "Restore version v{version}?",
  },
  "history.restoreHelp": {
    vi: "Nội dung của phiên bản này sẽ trở thành phiên bản hiện tại mới. Các phiên bản hiện có vẫn được giữ lại trong lịch sử.",
    en: "The content of this version will become the new current version. Existing history is retained.",
  },
  "history.restore": { vi: "Khôi phục", en: "Restore" },
  "history.restoredNotice": {
    vi: "Đã khôi phục trên máy chủ. Tệp trên máy này không bị ghi đè.",
    en: "Restored on the server. The file on this PC was not overwritten.",
  },
  "history.restoredSuccess": {
    vi: "Đã khôi phục v{version} thành phiên bản hiện tại mới.",
    en: "Restored v{version} as the new current version.",
  },
  "source.conflict": { vi: "Xung đột", en: "Conflict" },
  "source.restore": { vi: "Khôi phục", en: "Restore" },
  "source.restoreFrom": { vi: "Khôi phục từ v{version}", en: "Restored from v{version}" },
  "source.office": { vi: "Chỉnh sửa trực tuyến", en: "Edited online" },
  "source.device": { vi: "Đồng bộ từ máy {device}", en: "Synced from {device}" },
  "source.desktop": { vi: "Đồng bộ từ máy", en: "Synced from this PC" },
  "object.gone": { vi: "Không còn", en: "Unavailable" },
  "object.ok": { vi: "Còn", en: "Available" },
  "object.unknown": { vi: "Chưa kiểm tra", en: "Not checked" },
  "folders.register": { vi: "Thêm thư mục đồng bộ", en: "Add a folder to sync" },
  "folders.registerIntro": viEn(
    "Chọn một thư mục trên máy này. Mọi tệp trong thư mục sẽ được đồng bộ với máy chủ.",
    "Pick a folder on this computer. Every file in it will be synced with the server.",
  ),
  "toggle.on": { vi: "Bật", en: "On" },
  "toggle.off": { vi: "Tắt", en: "Off" },
  "folders.logicalName": { vi: "Tên thư mục trên máy chủ", en: "Folder name on the server" },
  "folders.logicalNameHint": viEn(
    "Tự điền theo tên thư mục bạn chọn; đổi được nếu muốn. Máy khác của bạn dùng cùng tên này sẽ đồng bộ chung một thư mục.",
    "Filled in from the folder you pick; change it if you like. Your other computers that use the same name will sync the same folder.",
  ),
  "folders.localFolder": { vi: "Thư mục trên máy này", en: "Folder on this computer" },
  "folders.choose": { vi: "Chọn thư mục", en: "Choose folder" },
  "folders.pickHint": {
    vi: "Bấm Chọn thư mục hoặc dán đường dẫn vào ô.",
    en: "Click Choose folder or paste the folder path.",
  },
  "folders.hyprlandHint": {
    vi: "Nếu hộp thoại chọn thư mục không hiện, hãy dán đường dẫn vào ô.",
    en: "If the folder dialog does not appear, paste the path instead.",
  },
  "folders.recursiveOnHint": viEn(
    "Tệp nằm trong các thư mục con cũng được đồng bộ.",
    "Files inside subfolders are synced too.",
  ),
  "folders.recursiveOffHint": viEn(
    "Chỉ đồng bộ các tệp nằm trực tiếp trong thư mục này, bỏ qua thư mục con.",
    "Only files directly in this folder are synced; subfolders are skipped.",
  ),
  "folders.filter": viEn("Chỉ đồng bộ một số tệp (tuỳ chọn)", "Sync only some files (optional)"),
  "folders.filterOffHint": viEn(
    "Đang tắt: mọi tệp trong thư mục đều được đồng bộ. Hầu hết người dùng không cần bật mục này.",
    "Off: every file in the folder is synced. Most people do not need this.",
  ),
  "folders.filterOnHint": viEn(
    "Đang bật: chỉ các tệp khớp điều kiện bên dưới được đồng bộ. Để trống điều kiện thì vẫn đồng bộ mọi tệp.",
    "On: only files matching the condition below are synced. Leave the condition empty to still sync every file.",
  ),
  "folders.ruleKind": { vi: "Chọn tệp theo", en: "Pick files by" },
  "folders.rule.prefix": { vi: "Tên bắt đầu bằng…", en: "Name starts with…" },
  "folders.rule.glob": { vi: "Tên khớp mẫu (dùng dấu *)", en: "Name matches a pattern (use *)" },
  "folders.rule.extension": { vi: "Đuôi tệp (ví dụ xlsx)", en: "File type (for example xlsx)" },
  "folders.pattern.prefix": { vi: "Tên tệp bắt đầu bằng", en: "File name starts with" },
  "folders.pattern.glob": { vi: "Mẫu tên tệp", en: "File name pattern" },
  "folders.pattern.extension": { vi: "Đuôi tệp", en: "File type" },
  "folders.recursive": { vi: "Gồm cả các thư mục con", en: "Include subfolders" },
  "folders.submit": { vi: "Thêm thư mục", en: "Add folder" },
  "folders.registered": { vi: "Thư mục đã thêm", en: "Added folders" },
  "folders.empty": { vi: "Chưa thêm thư mục nào.", en: "No folders added yet." },
  "folders.sample": { vi: "Mẫu", en: "Sample" },
  "folders.workflow": { vi: "Trạng thái", en: "Status" },
  "folders.instrument": { vi: "Thiết bị", en: "Instrument" },
  "folders.denied": {
    vi: "Mất quyền truy cập — đồng bộ đã tạm dừng. Tệp trên máy vẫn còn nguyên và các tệp đang chờ sẽ tự đồng bộ lại khi bạn được cấp lại quyền. Hãy liên hệ chủ thư mục hoặc quản trị viên.",
    en: "Access lost — syncing is paused. Your files on this computer are untouched, and waiting files will sync again once access is restored. Contact the folder owner or your administrator.",
  },
  "access.manage": { vi: "Quản lý quyền truy cập", en: "Manage access" },
  "access.title": { vi: "Quyền truy cập thư mục", en: "Folder access" },
  "access.loading": { vi: "Đang tải…", en: "Loading…" },
  "access.owner": { vi: "Chủ sở hữu", en: "Owner" },
  "access.myRole": { vi: "Tư cách của bạn", en: "Your role" },
  "access.role.owner": { vi: "Chủ sở hữu", en: "Owner" },
  "access.role.upload": { vi: "Thành viên", en: "Member" },
  "access.role.manager": { vi: "Quản trị đồng bộ", en: "Sync manager" },
  "access.members": { vi: "Thành viên", en: "Members" },
  "access.memberHint": {
    vi: "Thành viên được đọc và ghi: xem, tải xuống, tải lên và khôi phục phiên bản.",
    en: "Members can read and write: view, download, upload and restore versions.",
  },
  "access.effective.ok": { vi: "Truy cập được", en: "Has access" },
  "access.effective.noSample": {
    vi: "Chưa có quyền truy cập mẫu trong LIMS.",
    en: "No access to the sample in LIMS yet.",
  },
  "access.mappedHint": {
    vi: "Thư mục này gắn với một mẫu. Thêm thành viên không cấp quyền xem mẫu trong LIMS — người chưa thấy mẫu sẽ chưa truy cập được thư mục cho tới khi được cấp quyền mẫu.",
    en: "This folder is linked to a sample. Adding a member does not grant LIMS access to the sample — people who cannot see the sample cannot use the folder until they are granted sample access.",
  },
  "access.readOnlyHint": {
    vi: "Chỉ chủ sở hữu hoặc quản trị đồng bộ thêm và gỡ được thành viên.",
    en: "Only the owner or a sync manager can add and remove members.",
  },
  "access.add": { vi: "Thêm thành viên", en: "Add member" },
  "access.searchPlaceholder": {
    vi: "Nhập tên hoặc tên đăng nhập (ít nhất 2 ký tự)",
    en: "Type a name or login (at least 2 characters)",
  },
  "access.noCandidates": { vi: "Không tìm thấy người phù hợp.", en: "No matching people." },
  "access.addAction": { vi: "Thêm", en: "Add" },
  "access.remove": { vi: "Gỡ quyền", en: "Remove" },
  "access.removeConfirm": {
    vi: "Gỡ quyền truy cập của «{name}»? Tệp trên máy của họ không bị xóa.",
    en: "Remove access for “{name}”? Files on their computer are not deleted.",
  },
  "access.added": { vi: "Đã thêm thành viên.", en: "Member added." },
  "access.removed": { vi: "Đã gỡ quyền.", en: "Access removed." },
  "shared.title": { vi: "Được chia sẻ với bạn", en: "Shared with you" },
  "shared.hint": {
    vi: "Thư mục người khác chia sẻ cho bạn nhưng chưa đồng bộ về máy này. Chọn một thư mục trên máy để bắt đầu.",
    en: "Folders others shared with you that are not synced to this computer yet. Pick a local folder to start.",
  },
  "shared.ownedTitle": {
    vi: "Thư mục của bạn chưa đồng bộ trên máy này",
    en: "Your folders not synced on this computer",
  },
  "shared.ownedHint": {
    vi: "Thư mục bạn sở hữu trên máy chủ nhưng máy này chưa đồng bộ (ví dụ sau khi bấm “Ngừng đồng bộ”). Chọn một thư mục trên máy để đồng bộ lại.",
    en: "Folders you own on the server that this computer is not syncing (for example after “Stop syncing”). Pick a local folder to sync again.",
  },
  "shared.bind": { vi: "Chọn thư mục trên máy", en: "Choose local folder" },
  "folders.unregister": { vi: "Ngừng đồng bộ", en: "Stop syncing" },
  "folders.unregisterConfirm": {
    vi: "Ngừng đồng bộ «{name}» trên máy này? Ứng dụng sẽ không theo dõi thư mục này nữa. Tệp trên máy của bạn không bị xóa. Thư mục trên máy chủ, thành viên và những người khác đang đồng bộ không bị ảnh hưởng; bạn có thể đồng bộ lại sau.",
    en: "Stop syncing «{name}» on this computer? The app will no longer watch this folder. Your files on this computer are not deleted. The server folder, its members and everyone else syncing it are not affected; you can sync it again later.",
  },
  "folders.pickerMissing": {
    vi: "Không mở được hộp thoại chọn thư mục. Hãy dán đường dẫn thư mục vào ô, rồi bấm Thêm thư mục.",
    en: "Could not open the folder dialog. Paste the folder path, then click Add folder.",
  },
  "settings.autostart": {
    vi: "Tự chạy khi khởi động máy",
    en: "Start when the computer starts",
  },
  "settings.autostartHint": viEn(
    "Ứng dụng tự mở và đồng bộ ngay khi bạn bật máy, không cần mở bằng tay.",
    "The app opens and starts syncing when you turn on the computer.",
  ),
  "settings.section.general": { vi: "Chung", en: "General" },
  "settings.section.connection": { vi: "Kết nối", en: "Connection" },
  "settings.section.timing": { vi: "Nhịp đồng bộ", en: "Sync timing" },
  "settings.section.timingHint": viEn(
    "Giá trị mặc định phù hợp với hầu hết mọi người. Chỉ đổi khi quản trị viên hướng dẫn.",
    "The defaults suit most people. Change these only if your administrator asks you to.",
  ),
  "settings.debounce": viEn(
    "Thời gian chờ trước khi bắt đầu đồng bộ (mili giây)",
    "Wait before syncing starts (milliseconds)",
  ),
  "settings.debounceHint": viEn(
    "Sau khi bạn sửa tệp, ứng dụng chờ một lúc rồi mới xử lý để tránh đồng bộ nhiều lần liên tiếp. 1000 = 1 giây.",
    "After you change a file, the app waits a moment so it does not sync many times in a row. 1000 = 1 second.",
  ),
  "settings.reconcile": viEn(
    "Bao lâu kiểm tra lại toàn bộ thư mục (giây)",
    "How often to re-check whole folders (seconds)",
  ),
  "settings.reconcileHint": viEn(
    "Ứng dụng định kỳ rà lại các thư mục để không bỏ sót thay đổi nào.",
    "The app re-scans your folders regularly so no change is missed.",
  ),
  "settings.poll": viEn(
    "Bao lâu kiểm tra thay đổi từ máy chủ (giây)",
    "How often to check the server for changes (seconds)",
  ),
  "settings.pollHint": viEn(
    "Ứng dụng định kỳ hỏi máy chủ xem có tệp mới hoặc thay đổi quyền truy cập hay không.",
    "The app regularly asks the server for new files or access changes.",
  ),
  "settings.odoo": { vi: "Địa chỉ máy chủ", en: "Server address" },
  "settings.odooHint": viEn(
    "Địa chỉ hệ thống MediLab mà ứng dụng kết nối để đồng bộ. Hỏi quản trị viên nếu bạn không chắc.",
    "The MediLab system this app connects to. Ask your administrator if you are not sure.",
  ),
  "settings.language": { vi: "Ngôn ngữ", en: "Language" },
  "settings.language.vi": { vi: "Tiếng Việt", en: "Tiếng Việt" },
  "settings.language.en": { vi: "English", en: "English" },
  "settings.device": {
    vi: "Phiên bản ứng dụng: MediLab File Sync {version}",
    en: "App version: MediLab File Sync {version}",
  },
  "settings.save": { vi: "Lưu cài đặt", en: "Save settings" },
  "settings.saved": { vi: "Đã lưu cài đặt.", en: "Settings saved." },
  "office.title": { vi: "Chỉnh sửa trực tuyến", en: "Edit online" },
  "office.stage.connecting": viEn(
    "Đang kết nối máy chủ chỉnh sửa trực tuyến…",
    "Connecting to the online editing server…",
  ),
  "office.stage.opening": viEn("Đang mở tài liệu…", "Opening the document…"),
  "office.stage.step1": { vi: "Bước 1/2", en: "Step 1 of 2" },
  "office.stage.step2": { vi: "Bước 2/2", en: "Step 2 of 2" },
  "office.retry": { vi: "Thử lại", en: "Try again" },
  "office.openTimeout": viEn(
    "Trình soạn thảo chưa phản hồi sau 1 phút. Máy chủ chỉnh sửa trực tuyến có thể đang quá tải hoặc không lấy được tệp. Hãy thử lại; đồng bộ tệp vẫn hoạt động bình thường.",
    "The editor did not respond after 1 minute. The online editing server may be overloaded or unable to fetch the file. Try again; file sync still works.",
  ),
  "office.openFailed": {
    vi: "Không mở được trình soạn thảo ONLYOFFICE.",
    en: "Could not open the ONLYOFFICE editor.",
  },
  "office.connectFailed": {
    vi: "Không kết nối được máy chủ chỉnh sửa trực tuyến (ONLYOFFICE) — máy chủ có thể đang tắt. Hãy báo quản trị viên rồi thử lại. Đồng bộ tệp vẫn hoạt động bình thường.",
    en: "Could not reach the online editing (ONLYOFFICE) server — it may be switched off. Tell your administrator, then try again. File sync still works.",
  },
  "update.check": viEn("Kiểm tra cập nhật", "Check for updates"),
  "update.checking": viEn("Đang kiểm tra…", "Checking…"),
  "update.upToDate": viEn("Ứng dụng đã cập nhật", "App is up to date"),
  "update.checkFailed": viEn("Không thể kiểm tra cập nhật", "Cannot check for updates"),
  "update.dialogTitle": viEn("Có bản cập nhật mới", "New update available"),
  "update.currentVersion": viEn("Phiên bản hiện tại", "Current version"),
  "update.newVersion": viEn("Phiên bản mới", "New version"),
  "update.releaseNotes": viEn("Ghi chú phát hành", "Release notes"),
  "update.installNow": viEn("Cập nhật ngay", "Update now"),
  "update.later": viEn("Để sau", "Later"),
  "update.downloading": viEn("Đang tải bản cập nhật…", "Downloading update…"),
  "update.ready": viEn(
    "Cập nhật đã sẵn sàng. Ứng dụng sẽ khởi động lại.",
    "Update ready. App will restart.",
  ),
} as const;

export type MessageKey = keyof typeof messages;

/** Dịch một key thông điệp theo locale, thay các biến `{name}` nếu có; rơi về vi nếu thiếu bản
 * dịch. */
export function translate(
  locale: Locale,
  key: MessageKey,
  vars?: Record<string, string | number>,
): string {
  let text: string = messages[key][locale] ?? messages[key].vi;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
  }
  return text;
}

export type Translate = (
  key: MessageKey,
  vars?: Record<string, string | number>,
) => string;
