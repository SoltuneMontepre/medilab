# Laboratory File Sync

Client desktop đồng bộ upload và download cho file kết quả của PTN (phòng thử nghiệm).

## Stack

- Tauri 2 + Rust + React/TypeScript/Vite/Bun
- Source: `applications/laboratory-file-sync-application/`
- Icon: `src-tauri/icons/logo.svg` (tạo lại bằng `bunx tauri icon src-tauri/icons/logo.svg`). Tray **bắt buộc** đặt ảnh này; trên Linux tray không có icon sẽ fallback về glyph hamburger/menu.
- Control plane Odoo: `src/modules/medilab_sync` tại `/api/sync/v1`
- Data plane cho object: multipart MinIO/S3, không bao giờ proxy qua Odoo

UI desktop mặc định tiếng Việt và có thể chuyển sang tiếng Anh từ màn hình
đăng nhập, header hoặc **Settings**. Lựa chọn được lưu trong settings của app dưới dạng
`locale` (`vi` / `en`) và khôi phục ở lần mở sau. Lưu settings hiện thông báo
xác nhận (và lỗi màu đỏ nếu lưu thất bại). Nhãn menu tray theo
locale đã lưu lúc process khởi động.

## Architecture

```text
Desktop Rust  --auth/metadata/prepare/finalize/changes/download-auth/office-session-->  Odoo 19 + medilab_sync
Desktop Rust  --multipart PUT / GET-->                                  MinIO / S3
Desktop / browser  --DocsAPI-->                                         ONLYOFFICE Document Server
ONLYOFFICE  --callback JWT-->                                           Odoo
Odoo / Document Server  --presigned GET / PUT-->                        MinIO / S3
Desktop SQLite                                                          local durable queue
res.users + res.users.apikeys                                           identity + device-bound auth
```

Phase 3 là **hai chiều** cho nội dung canonical: sửa local vẫn upload; thay đổi canonical phía remote thì download. Xóa/đổi tên local không được lan truyền. Xóa/đổi tên phía remote bị hoãn lại.

## Folder membership vs device vs local path

- **Thư mục remote** = `sync.folder.id`. Dùng chung giữa các user/thiết bị có quyền.
- **Thiết bị** = `sync.device` + API key gắn với thiết bị. Xác thực, audit, nguồn gốc phiên bản, thu hồi.
- **Đường dẫn local** = chỉ trong SQLite của desktop. Không bao giờ gửi lên Odoo.

`GET /folders` trả về mọi thư mục remote mà user hiện tại có quyền dùng, bất kể thiết bị nào đã tạo nó.

Đăng ký thư mục của chính mình luôn `POST /folders` (server upsert theo `(user, logical_root)` của người gọi). Thư mục **được người khác chia sẻ** hiện ở khối “Được chia sẻ với bạn” (`GET /folders`, `my_role = upload`, chưa gắn cục bộ) và được gắn theo **remote id**, không `POST /folders` — nên không tạo thư mục trùng lặp và không vướng thư mục trùng tên của chính mình. Mỗi user/máy chọn đường dẫn local riêng. “Ngừng đồng bộ” chỉ bỏ binding trên máy đó (không gọi server); thư mục hiện lại trong danh sách chưa gắn và gắn lại được, không phải tạo lại.

Chia sẻ làm được từ desktop (“Quản lý quyền truy cập”: chủ sở hữu hoặc Sync Manager thêm/gỡ thành viên) hoặc từ form thư mục trong Odoo (Manager/Admin). Thành viên chỉ có một mức đọc + ghi (key lưu `upload`); không có vai trò chỉ đọc, không tự rời thư mục, và desktop không chuyển chủ sở hữu. Ẩn/hiện nút trên desktop không phải phân quyền — server kiểm ở từng lần gọi.

Thu hồi thiết bị B không gỡ tư cách thành viên của user B. Một thiết bị C mới xác thực của user B có thể dùng thư mục nếu tư cách thành viên vẫn còn.

## Phase 5 — laboratory integration

Phân cấp (model thực tế):

```text
yeu.cau.thu.nghiem → danh.sach.mau → sync.folder (category) → sync.file → sync.file.version
                                      ↳ sync.file.approval / signoff / lock
```

**Phân quyền:** key thiết bị VÀ tư cách thành viên thư mục VÀ quyền thấy mẫu (khi đã map). Cô lập thử nghiệm viên dùng lại rule `phong_ban_ids` của `tpc_thu_nghiem` cho `group_thu_nghiem_vien`. Internal user không có các group đó không bị lọc dòng trên mẫu — khi đó mapping chỉ thêm tư cách thành viên thư mục, như ở Phase 1–4.

**Ký duyệt** (sign-off) là bản ghi audit có xác thực cho một phiên bản/hash cụ thể. Nó không phải chữ ký số đủ điều kiện về mặt mật mã.

Dữ liệu **RAW** là bằng chứng chỉ ghi thêm (append-only). File **Office** được đồng sửa trong ONLYOFFICE mà không có khóa độc quyền của MediLab. File binary WORKING/RESULT có thể dùng khóa có thời hạn thuê (lease); kiểm xung đột phiên bản vẫn áp dụng khi commit.

**Lưu giữ** (retention) lưu trữ metadata; nó không xóa object MinIO trong phase này.
