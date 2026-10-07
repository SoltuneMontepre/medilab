# Laboratory File Sync & Collaboration Platform

## 1. Tổng quan dự án

### 1.1. Bối cảnh

Trong quá trình kiểm nghiệm, một kỹ thuật viên có thể làm việc trên nhiều máy tính, tại nhiều phòng khác nhau và với nhiều thiết bị kiểm nghiệm khác nhau.

Một quy trình kiểm nghiệm có thể được chia thành nhiều công đoạn:

- Kỹ thuật viên A thực hiện công đoạn 1.
- Kỹ thuật viên B thực hiện công đoạn 2.
- Kỹ thuật viên C thực hiện công đoạn đối chiếu hoặc xác nhận.
- Các kỹ thuật viên có thể sử dụng nhiều máy tính khác nhau.
- Dữ liệu có thể được sinh ra từ thiết bị kiểm nghiệm, chỉnh sửa bằng Excel, Word hoặc các phần mềm chuyên dụng.
- Một tài liệu, biểu mẫu hoặc folder của cùng một mẫu có thể được nhiều người sử dụng hoặc chỉnh sửa gần như đồng thời.

Hiện trạng này dễ phát sinh các vấn đề:

- File nằm rải rác trên nhiều máy.
- Người dùng phải copy file thủ công.
- Khó xác định file nào là phiên bản mới nhất.
- Có nguy cơ ghi đè file của người khác.
- Không biết ai đã chỉnh sửa file.
- Không có lịch sử phiên bản rõ ràng.
- Mất dữ liệu khi mạng lỗi hoặc upload bị gián đoạn.
- Khó đồng bộ dữ liệu giữa các phòng hoặc thiết bị.
- Khó truy vết khi cần audit.

Dự án hướng đến việc xây dựng một nền tảng đồng bộ file nội bộ tương tự Google Drive/Dropbox, nhưng được tối ưu cho môi trường kiểm nghiệm và có khả năng tích hợp hệ thống quản lý phòng thí nghiệm.

---

## 2. Mục tiêu

### 2.1. Mục tiêu chính

Xây dựng một desktop application cho phép kỹ thuật viên:

1. Đăng nhập bằng tài khoản của hệ thống.
2. Chọn một hoặc nhiều folder trên máy tính.
3. Cấu hình quy tắc xác định file cần đồng bộ.
4. Tự động phát hiện thay đổi file.
5. Upload file ở background.
6. Có thể tiếp tục sử dụng máy trong khi upload.
7. Tự retry khi mất mạng.
8. Resume upload sau khi ứng dụng hoặc máy tính restart.
9. Hỗ trợ sync một chiều hoặc hai chiều.
10. Lưu lịch sử phiên bản của file.
11. Ghi nhận người dùng và thiết bị tạo ra mỗi phiên bản.
12. Phát hiện concurrent editing/conflict.
13. Cho phép mở và đồng chỉnh sửa file Office bằng ONLYOFFICE.
14. Cho phép restore phiên bản cũ.

---


## 2.3. Quyết định kiến trúc đã chốt

Hệ thống web chính hiện tại là **Odoo 19 monolith**. Vì vậy, ở giai đoạn hiện tại dự án **không tạo một hệ thống account/auth riêng cho Sync App**.

Quyết định:

- Desktop Sync App dùng **chung tài khoản Odoo**.
- Không tạo username/password riêng cho ứng dụng Sync.
- Không đồng bộ password qua event.
- Không tạo một database identity riêng.
- Dùng **chung PostgreSQL với Odoo** ở giai đoạn hiện tại.
- Dùng `res.users` làm identity chính.
- Dùng **Odoo Groups / Access Rights / Record Rules** để quyết định user nào được phép sử dụng Sync App.
- Sync feature được triển khai dưới dạng module Odoo, đề xuất tên `medilab_sync`.
- File binary lớn không lưu trực tiếp trong PostgreSQL; lưu trên **MinIO/S3**.
- ONLYOFFICE vẫn là service riêng để phục vụ collaborative editing.
- Desktop Tauri/Rust gọi API của Odoo và chỉ được hoạt động khi user có permission tương ứng.

Kiến trúc này ưu tiên đơn giản, tận dụng auth/permission sẵn có của Odoo và vẫn giữ đường nâng cấp để tách Sync thành service riêng trong tương lai.

---

## 3. Phạm vi chức năng

## 3.1. Desktop Application

Desktop app hoạt động tương tự một sync client.

Các chức năng chính:

- Login.
- Logout.
- Remember session.
- Chọn folder cần theo dõi.
- Chọn nhiều folder.
- Bật/tắt sync theo từng folder.
- Chạy nền.
- System tray.
- Auto start cùng hệ điều hành.
- Theo dõi filesystem.
- Background upload.
- Background download.
- Retry.
- Resume.
- Queue management.
- Local cache.
- Local metadata database.
- Sync status.
- Error status.
- Conflict status.
- Manual retry.
- Open file.
- Open file bằng ONLYOFFICE.
- Xem history.
- Restore version.

---

## 3.2. Quy tắc xác định file cần sync

Không hardcode theo tên file.

Hệ thống nên hỗ trợ `SyncRule`.

Ví dụ:

```yaml
mode: prefix
pattern: ABC
extensions:
  - xlsx
  - docx
  - pdf
recursive: true
```

Các loại rule nên hỗ trợ:

- Prefix.
- Suffix.
- Glob.
- Regex.
- Extension.
- Folder.
- Recursive/non-recursive.

Ví dụ:

```text
ABC*
```

sẽ match:

```text
ABC_001.xlsx
ABC_002.docx
ABC_RESULT.pdf
```

và ignore:

```text
XYZ_001.xlsx
TEMP.txt
```

Ví dụ nâng cao:

```text
SAMPLE-2026-*-RESULT.xlsx
```

---

## 4. Sync Mode

## 4.1. Upload-only sync

Dữ liệu chỉ đi từ local lên server.

```text
LOCAL
  |
  +-------> SERVER
```

Thay đổi từ server không tự động ghi xuống local.

Use case:

- Máy thiết bị sinh kết quả.
- Máy chỉ có nhiệm vụ đẩy file lên hệ thống.
- Không muốn server overwrite file trên máy thiết bị.

---

## 4.2. Two-way sync

Dữ liệu đi hai chiều.

```text
LOCAL
   |
   +-------> SERVER
   |
   <-------+
```

Use case:

- Kỹ thuật viên cần nhận file mới nhất về máy.
- File được chỉnh sửa ở nhiều máy.
- Folder dùng chung giữa nhiều kỹ thuật viên.

---

## 5. Kiến trúc đề xuất

```text
+------------------------------------------------------+
|                   Desktop Sync App                   |
|                                                      |
|   React + TypeScript UI                              |
|   Tauri 2                                            |
|      |                                               |
|      v                                               |
|   Rust Sync Engine                                   |
|                                                      |
|   - File Watcher / Poll Fallback                     |
|   - Rule Matcher                                     |
|   - Hash / Checksum                                  |
|   - Upload Queue                                     |
|   - Download Queue                                   |
|   - Retry / Resume                                   |
|   - Conflict Detection                               |
|   - Local SQLite                                     |
|   - System Tray / Auto Start                         |
+------------------+------------------+----------------+
                   |                  |
       Control     |                  | Heavy binary payload
       plane       |                  | direct transfer
                   v                  v
+--------------------------------+  +-----------------------+
|       Odoo 19 Monolith         |  |      S3 / MinIO       |
|                                |  |                       |
| Existing Auth / res.users      |  | Object Storage        |
| Groups / ACL / Record Rules    |  | Multipart Upload      |
|                                |  | Presigned URLs        |
| Module: medilab_sync           |  | Checksums             |
|                                |  +-----------+-----------+
| - Authorization                |              ^
| - Upload session orchestration |              |
| - Presigned URL issuance       |              |
| - Device Management            |              |
| - File Metadata                |              |
| - FileVersion / Audit          |              |
| - Conflict Handling            |              |
| - ONLYOFFICE Integration       |              |
|                                |              |
| PostgreSQL (same DB as Odoo)   |              |
+---------------+----------------+              |
                |                               |
                +-------------------------------+
                    metadata / verification

                +------------------------+
                | ONLYOFFICE             |
                | Document Server        |
                | DOCX/XLSX/PPTX editing |
                +------------------------+
```

### 5.1. Nguyên tắc

- Odoo là backend chính và là source of truth cho user, permission, metadata và nghiệp vụ.
- Desktop app **không truy cập PostgreSQL trực tiếp**.
- Desktop app chỉ gọi API Odoo cho control plane: authentication, authorization, upload-session creation, metadata và finalize.
- **Payload file lớn không đi xuyên qua Odoo** trong luồng upload/download thông thường.
- Odoo cấp quyền truy cập object storage bằng presigned URL hoặc cơ chế credential tạm thời tương đương.
- Rust Sync Engine upload/download trực tiếp với MinIO/S3.
- Sau khi transfer hoàn tất, Odoo xác minh object/checksum rồi mới tạo `FileVersion`.
- PostgreSQL chỉ lưu metadata; MinIO/S3 lưu binary file.
- ONLYOFFICE không phải source of truth của file; file sau khi save vẫn phải được đưa về storage do hệ thống quản lý.
- WebSocket chỉ là kênh notification/invalidation, không phải nguồn consistency duy nhất của Sync Engine.

### 5.2. Control Plane và Data Plane

Hệ thống tách hai loại traffic:

#### Control Plane

Đi qua Odoo:

```text
Login
Permission check
Create upload session
Issue presigned URL
Finalize upload
Create FileVersion
Audit
Conflict metadata
ONLYOFFICE config/callback
```

#### Data Plane

Đi trực tiếp Desktop <-> Object Storage:

```text
File chunks
Large binary upload
Large binary download
Resume transfer
Checksum-aware multipart transfer
```

Mục tiêu của việc tách này là tránh giữ các Odoo HTTP worker cho payload 500 MB, 1 GB hoặc lớn hơn.

## 6. Stack đề xuất

| Layer | Technology |
|---|---|
| Desktop Framework | Tauri 2 |
| Desktop Core | Rust |
| Desktop UI | React + TypeScript |
| UI Library | shadcn/ui |
| Async Runtime | Tokio |
| File Watcher | notify |
| Local Database | SQLite |
| Hash | SHA-256 hoặc BLAKE3 |
| Backend | **Odoo 19 / Python** |
| API | REST cho control plane; presigned S3/MinIO URLs cho data plane |
| Realtime | Odoo WebSocket ban đầu; có thể tách Hub khi scale |
| Database | **PostgreSQL dùng chung với Odoo** |
| Object Storage | S3 hoặc MinIO |
| Cache/Event | Redis khi thực sự cần |
| Collaborative Office Editor | ONLYOFFICE Document Server |
| Deployment | Docker/Podman |
| Reverse Proxy | Nginx / Traefik / Caddy |
| CI/CD | GitHub Actions |
| Installer | Tauri Bundler |
| Auto Update | Tauri Updater |

---

## 7. Tại sao chọn Tauri + Rust

Desktop application không chỉ là UI.

Phần quan trọng nhất là sync engine.

Sync engine cần:

- Theo dõi filesystem.
- Hash file.
- Xử lý nhiều event.
- Queue.
- Retry.
- Resume.
- Detect conflict.
- Background processing.
- Consume RAM thấp.
- Chạy lâu dài trong system tray.

Rust phù hợp cho các tác vụ này.

Tauri cho phép sử dụng frontend web hiện đại nhưng backend desktop sử dụng Rust.

Desktop app có thể build ra:

### Windows

- `.exe`
- `.msi`

### macOS

- `.dmg`
- `.app`

### Linux

- `.deb`
- `.rpm`
- `.AppImage`

---

## 8. File Watcher

Khi user chọn folder:

```text
D:\Laboratory\Samples
```

sync engine sẽ recursive watch folder đó.

Ví dụ:

```text
Samples/
├── ABC_001.xlsx
├── ABC_002.docx
├── ABC_RESULT.pdf
├── XYZ_001.xlsx
└── temp.txt
```

Nếu rule là:

```text
prefix = ABC
```

thì chỉ sync:

```text
ABC_001.xlsx
ABC_002.docx
ABC_RESULT.pdf
```

### 8.1. Native watcher không phải nguồn sự thật tuyệt đối

`notify` sử dụng filesystem notification API phù hợp với từng OS. Native watcher giúp phát hiện thay đổi nhanh nhưng **không được xem là cơ chế đảm bảo 100% event**.

Các tình huống cần dự phòng:

- Folder có số lượng file/folder rất lớn.
- Linux đạt giới hạn `inotify`.
- Network filesystem không phát event đầy đủ.
- Event queue của OS bị overflow.
- App không chạy trong khoảng thời gian file được thay đổi.
- Editor thực hiện save bằng nhiều thao tác create/rename/delete khác nhau.

### 8.2. Watcher fallback

Sync Engine phải bắt lỗi watcher, đặc biệt nhóm lỗi tương đương:

```text
MaxFilesWatch
Watch initialization failed
Event stream degraded
```

Khi native watcher không còn đáng tin cậy:

```text
Native Watcher
      |
      | error / watch limit
      v
Polling / Reconciliation Mode
```

Ứng dụng có thể dùng:

- `notify::PollWatcher`, hoặc
- reconciliation scan định kỳ do Sync Engine tự triển khai.

UI phải hiển thị warning, ví dụ:

```text
Thư mục này có quá nhiều file để theo dõi realtime.
Ứng dụng đã chuyển sang chế độ quét định kỳ.
```

### 8.3. Không chỉ yêu cầu người dùng xóa file

Nếu gặp giới hạn watcher, giải pháp có thể là:

1. Chuyển sang polling/reconciliation.
2. Thu hẹp folder/rule cần watch.
3. Archive file cũ.
4. Với endpoint Linux được quản trị tập trung, có thể tăng giới hạn `inotify` theo policy vận hành.
5. Không phụ thuộc vào việc người dùng thủ công "dọn file" để hệ thống hoạt động đúng.

Native watcher chỉ giúp giảm latency; **reconciliation mới là safety net đảm bảo eventual consistency**.

## 9. Debounce filesystem events

Không upload ngay mỗi khi filesystem phát event.

Một lần Save bằng Word/Excel có thể sinh nhiều event:

```text
WRITE
WRITE
CREATE TEMP
RENAME
DELETE TEMP
WRITE
```

Nếu upload mỗi event thì sẽ sinh rất nhiều version không cần thiết.

Luồng đúng:

```text
Filesystem Event
        |
        v
     Debounce
        |
        v
File Stable Check
        |
        v
 Rule Matching
        |
        v
 Calculate Hash
        |
        v
 Hash Changed?
        |
        v
 Upload Queue
```

Khoảng debounce có thể cấu hình:

```text
500 ms
1000 ms
2000 ms
```

---

## 10. Reconciliation Scan

Filesystem watcher không phải nguồn dữ liệu duy nhất.

Desktop agent **luôn** cần reconciliation scan, kể cả khi native watcher đang hoạt động bình thường.

Ví dụ:

```text
Every 5-15 minutes
```

Khoảng thời gian có thể điều chỉnh theo:

- Số lượng file.
- Loại máy.
- Network.
- Sync policy.
- Chế độ native watcher hay polling fallback.

So sánh:

```text
Actual Filesystem
       vs
Local SQLite
       vs
Server Sync Cursor / Metadata
```

Mục đích:

- Phát hiện event bị miss.
- Phát hiện file thay đổi khi app không chạy.
- Phục hồi state sau restart.
- Phát hiện sai lệch sau network interruption.
- Tự chữa state sau WebSocket disconnect.
- Đảm bảo eventual consistency.

Nếu native watcher bị lỗi hoặc vượt giới hạn OS, reconciliation frequency có thể tăng lên để trở thành cơ chế phát hiện chính.

## 11. Local SQLite

Desktop app cần local database.

Ví dụ:

```text
sync.db
```

### Table: sync_folders

```text
id
local_path
sync_mode
enabled
created_at
```

### Table: sync_rules

```text
id
folder_id
rule_type
pattern
extensions
recursive
```

### Table: files

```text
id
local_path
remote_file_id
size
mtime
local_hash
remote_version
sync_status
last_synced_at
```

### Table: sync_jobs

```text
id
file_id
operation
status
retry_count
error_message
created_at
updated_at
```

Possible status:

```text
PENDING
UPLOADING
DOWNLOADING
SYNCED
FAILED
CONFLICT
```

Nhờ SQLite:

```text
Mất mạng
   |
   v
Queue vẫn còn

Restart app
   |
   v
Queue vẫn còn

Restart máy
   |
   v
App auto start

Có mạng lại
   |
   v
Resume
```

---

## 12. Upload Protocol

### 12.1. Không stream file lớn xuyên qua Odoo

Không nên:

```text
Desktop
   |
   | 500 MB - 1 GB binary body
   v
Odoo HTTP Worker
   |
   v
MinIO
```

Odoo nên xử lý **authorization + metadata**, không nên trở thành data proxy cho file lớn.

Luồng đề xuất:

```text
Desktop/Rust
    |
    | 1. POST /sync/uploads/prepare
    v
Odoo
    |
    | authorize user
    | check baseVersion
    | create UploadSession
    | reserve object key
    | initiate multipart upload
    | issue presigned URL(s)
    v
Desktop/Rust
    |
    | 2. upload parts DIRECTLY
    v
MinIO / S3
    |
    | 3. multipart object complete
    v
Desktop/Rust
    |
    | 4. POST /sync/uploads/{id}/finalize
    v
Odoo
    |
    | verify object exists
    | verify size/checksum/upload session
    | re-check conflict conditions
    | create immutable FileVersion
    | write audit log
    v
DONE
```

### 12.2. Prepare Upload

Desktop tính hash/checksum và gửi metadata:

```json
{
  "path": "ABC_RESULT.xlsx",
  "size": 524288000,
  "contentHash": "...",
  "baseVersion": 12
}
```

Odoo kiểm tra:

- User có `SYNC_UPLOAD`.
- User có quyền với sample/folder tương ứng.
- File/version có tồn tại không.
- `baseVersion` còn hợp lệ không.
- Có thể deduplicate không.
- Object key nào được phép ghi.
- Upload session expiry.

Odoo trả ví dụ:

```json
{
  "uploadSessionId": "...",
  "objectKey": "...",
  "uploadId": "...",
  "partSize": 16777216,
  "parts": [
    {
      "partNumber": 1,
      "url": "<temporary presigned URL>"
    }
  ]
}
```

Presigned URL phải:

- Có thời hạn ngắn.
- Chỉ cho đúng bucket/object/operation cần thiết.
- Không cấp permanent MinIO credential cho Desktop.
- Không cho Desktop tự chọn arbitrary object key ngoài authorization của Odoo.

### 12.3. Multipart Upload

Rust upload trực tiếp:

```text
Desktop
   |
   +-- part 1 --> MinIO
   +-- part 2 --> MinIO
   +-- part 3 --> MinIO
   +-- ...
```

Các part có thể upload song song trong giới hạn cấu hình.

Nếu mạng lỗi ở 80%:

```text
không upload lại toàn bộ file
```

chỉ retry các part thiếu hoặc lỗi.

### 12.4. Finalize

Không nên giả định MinIO/S3 tự động "báo Odoo thành công" là luồng duy nhất.

Luồng mặc định nên là:

```text
Desktop completes transfer
        |
        v
POST finalize to Odoo
        |
        v
Odoo verifies object/storage state
```

Odoo chỉ tạo `FileVersion` sau khi xác minh thành công.

Có thể bổ sung MinIO bucket notification/webhook sau này cho:

- observability,
- orphan detection,
- security monitoring,
- asynchronous reconciliation,

nhưng event đó không cần là transaction boundary chính của MVP.

### 12.5. Checksum

Không dùng ETag như giả định rằng nó luôn là MD5 toàn file, đặc biệt với multipart upload.

Hệ thống cần lưu checksum rõ ràng theo algorithm đã chọn, ví dụ:

```text
SHA-256
CRC32C
```

Metadata cần ghi:

```text
content_hash
checksum_algorithm
size
storage_key
upload_session_id
```

### 12.6. Orphan Upload Cleanup

Có trường hợp:

```text
upload lên MinIO thành công
nhưng client chết trước finalize
```

Do đó cần cleanup job:

```text
UploadSession expired
AND no FileVersion committed
=> abort multipart / delete orphan object
```

Không tạo `FileVersion` chỉ dựa vào việc object tồn tại.

## 13. Object Storage

Không lưu binary file trực tiếp trong PostgreSQL.

PostgreSQL chỉ lưu metadata.

Binary file lưu tại:

- MinIO.
- Amazon S3.
- S3-compatible storage.

Ví dụ:

```text
samples/
└── SAMPLE-001/
    └── ABC_RESULT.xlsx/
        ├── version-001
        ├── version-002
        ├── version-003
        └── version-004
```

Mỗi version là immutable.

Object key do Odoo cấp, Desktop không tự quyết định đường dẫn storage.

Storage chứa binary; **Odoo/PostgreSQL chứa authoritative metadata** về object nào đã được commit thành một `FileVersion`.

Một object upload dở hoặc chưa finalize không được xem là version hợp lệ.

---

## 14. File Versioning

Mỗi khi một file ổn định sau một đợt thay đổi và hash thay đổi:

```text
Create FileVersion
```

Không tạo version cho từng keypress.

Desktop app không biết người dùng vừa gõ ký tự gì trong Word.

Nó chỉ quan sát filesystem.

Ví dụ:

```text
10:31:01 WRITE
10:31:01 WRITE
10:31:02 WRITE
10:31:03 RENAME
10:31:04 WRITE
```

Sau debounce:

```text
10:31:06
Create 1 version
```

---

## 15. Version History

Ví dụ:

```text
ABC_RESULT.xlsx

v14
Nguyễn Văn A
LAB-PC-01
09:13

v15
Trần Văn B
LAB-PC-07
09:42

v16
Nguyễn Văn A
LAB-PC-01
10:01

v17
Trần Văn C
LAB-PC-02
10:32
```

Mỗi version có thể lưu:

```text
version_id
file_id
version_number
parent_version_id
created_by_user_id
created_by_device_id
hash
size
storage_key
created_at
source
```

Source có thể là:

```text
DESKTOP_SYNC
ONLYOFFICE
RESTORE
SYSTEM
```

---

## 16. Concurrent Editing

Đây là một trong những phần quan trọng nhất của hệ thống.

Giả sử:

```text
Server version = 10
```

A tải version 10.

B tải version 10.

A chỉnh sửa và upload:

```text
baseVersion = 10
```

Server tạo:

```text
version 11
```

B sau đó upload file của mình:

```text
baseVersion = 10
```

nhưng server hiện là:

```text
version 11
```

=> Conflict.

Không được silent overwrite.

---

## 17. Conflict Model

Có thể biểu diễn:

```text
File
|
+-- v10
    |
    +-- v11 (User A)
    |
    +-- v12-conflict (User B)
```

### 17.1. Không silent overwrite

Khi client upload với:

```text
baseVersion = 10
```

nhưng server đã ở:

```text
currentVersion = 11
```

server không được ghi đè version 11.

Nội dung của client B phải được upload và lưu thành một artifact/version conflict riêng trước khi user thực hiện resolve.

### 17.2. Office documents

Với file được quản lý qua ONLYOFFICE:

```text
DOCX
XLSX
PPTX
```

ưu tiên collaborative editing của ONLYOFFICE để giảm conflict do nhiều người cùng sửa.

Nếu file Office vẫn được phép chỉnh bằng desktop app ngoài ONLYOFFICE, conflict detection vẫn bắt buộc.

### 17.3. Raw/Binary files

Ví dụ:

```text
.dat
.raw
spectrometer output
instrument binary
proprietary measurement files
```

Desktop UI **không được giả định có thể Compare/Merge** các file này.

Policy an toàn:

```text
Conflict detected
      |
      +--> preserve server version
      |
      +--> preserve client version
      |
      +--> create conflicted copy/version
      |
      +--> require explicit resolution
```

Tuyệt đối không xóa file local chưa sync chỉ vì user chọn version server làm canonical.

Nếu user/manager chọn:

```text
Use server version as canonical
```

thì conflicting version vẫn phải tồn tại trong version history/audit dưới trạng thái ví dụ:

```text
REJECTED
SUPERSEDED
CONFLICT_RESOLVED
```

Nghĩa là "Keep server" chỉ thay đổi **canonical current version**, không làm mất evidence.

### 17.4. Raw instrument data nên ưu tiên append-only

Nếu file là dữ liệu gốc do thiết bị kiểm nghiệm sinh ra, thiết kế tốt hơn là:

```text
capture
   |
   v
immutable raw artifact
```

thay vì cho phép cùng một logical file bị edit/overwrite nhiều lần.

Có thể định danh bằng:

```text
sample_id
instrument_id
captured_at
content_hash
```

Raw data:

- Không overwrite.
- Không merge.
- Không edit tại chỗ.
- Mỗi capture là một immutable artifact/version.
- File xử lý/phân tích phát sinh sau đó là derivative artifact riêng.

Điều này giảm đáng kể conflict và phù hợp hơn với yêu cầu traceability/audit.

### 17.5. Resolution UI theo loại file

#### Text / supported semantic format

Có thể:

- Compare.
- Manual merge.
- Choose canonical.
- Save both.

#### Binary / proprietary format

Chỉ nên:

- Download version A.
- Download version B.
- Save both.
- Open bằng phần mềm chuyên dụng.
- Mark canonical after review.
- Ghi người resolve, thời gian, lý do.

## 18. Atomic Download

Không download trực tiếp đè lên file chính.

Sai:

```text
download -> ABC_RESULT.xlsx
```

Nếu mất mạng giữa chừng file có thể bị corrupt.

Đúng:

```text
download
    |
    v
.ABC_RESULT.xlsx.sync-temp
    |
    v
verify checksum
    |
    v
atomic rename
    |
    v
ABC_RESULT.xlsx
```

---

# 19. ONLYOFFICE Integration

## 19.1. Mục đích

ONLYOFFICE Document Server được sử dụng cho collaborative editing các file:

- DOCX.
- XLSX.
- PPTX.

ONLYOFFICE không thay thế sync engine.

ONLYOFFICE chịu trách nhiệm:

- Browser/web editor.
- Office document rendering.
- Collaborative editing.
- Realtime co-editing.
- Track changes.
- Editor session.

Sync engine chịu trách nhiệm:

- Local folder.
- Background sync.
- Offline.
- Device files.
- Raw files.
- Retry.
- Resume.
- File discovery.

---

## 19.2. Kiến trúc ONLYOFFICE

```text
Desktop App
     |
     v
Odoo Backend
     |
     +------------------> PostgreSQL
     |
     +------------------> MinIO / S3
     |
     +------------------> ONLYOFFICE
```

ONLYOFFICE không phải nơi lưu file chính.

Source of truth vẫn là:

```text
Object Storage
```

---

## 19.3. Open document

Khi người dùng mở:

```text
ABC_RESULT.xlsx
```

backend tạo ONLYOFFICE editor config.

Ví dụ:

```text
document key:
FILE-ID + VERSION-ID

user:
USER-ID
USER-NAME
```

User A:

```text
A
```

User B:

```text
B
```

Nếu cùng document key, cả hai tham gia cùng editing session.

---

## 19.4. Save flow từ ONLYOFFICE

```text
User edits document
        |
        v
ONLYOFFICE
        |
        v
Callback
        |
        v
Odoo Backend
        |
        v
Download final file
        |
        v
Verify
        |
        v
S3 / MinIO
        |
        v
Create FileVersion
        |
        v
Create Audit Log
```

---

## 19.5. File policy

Nên phân biệt:

### Managed documents

```text
DOCX
XLSX
PPTX
```

Khuyến nghị mở bằng ONLYOFFICE khi cần collaboration.

### Raw/device files

Ví dụ:

```text
PDF
CSV
TXT
JSON
JPG
instrument output
binary files
```

được sync bằng desktop sync engine.

---

## 19.6. Không nên edit cùng lúc qua Excel Desktop và ONLYOFFICE

Không khuyến nghị:

```text
User A:
Excel Desktop

User B:
ONLYOFFICE
```

cùng chỉnh một file tại cùng thời điểm.

Điều này có thể dẫn tới hai version riêng biệt.

Nên có chính sách:

```text
Managed document
=> Edit via ONLYOFFICE

Raw document
=> Desktop sync
```

Hoặc nếu vẫn cho phép desktop edit:

```text
server-side conflict detection
```

phải luôn hoạt động.

---

## 20. Audit Log

Trong môi trường kiểm nghiệm, audit log rất quan trọng.

Ví dụ:

```text
10:30:12
Nguyễn Văn A
LAB-PC-01
MODIFY ABC_RESULT.xlsx

10:30:18
Nguyễn Văn A
LAB-PC-01
UPLOAD VERSION 17

10:35:01
Trần Văn B
LAB-PC-07
DOWNLOAD VERSION 17

10:46:55
Trần Văn B
LAB-PC-07
UPLOAD VERSION 18
```

Audit log nên lưu:

```text
id
timestamp
user_id
device_id
action
file_id
version_id
ip_address
metadata
```

Possible action:

```text
LOGIN
LOGOUT
REGISTER_DEVICE
CREATE_SYNC_FOLDER
UPDATE_SYNC_RULE
UPLOAD
DOWNLOAD
CREATE_VERSION
RESTORE_VERSION
OPEN_DOCUMENT
ONLYOFFICE_EDIT
CONFLICT_CREATED
CONFLICT_RESOLVED
DELETE
```

---

## 21. Device Management

Một user có thể đăng nhập trên nhiều thiết bị.

Ví dụ:

```text
User Nguyễn Văn A
|
+-- LAB-PC-01
+-- LAB-PC-05
+-- Laptop-A
```

Device lưu:

```text
device_id
device_name
os
app_version
user_id
last_seen_at
created_at
revoked_at
```

Admin có thể:

- Xem danh sách device.
- Revoke device.
- Logout remote.
- Xem last seen.
- Xem app version.

---

## 22. Authentication và quyền truy cập Sync App

Desktop Sync App sử dụng **chung identity của Odoo**.

Không tồn tại:

```text
Sync username riêng
Sync password riêng
Sync user database riêng
```

User đăng nhập Desktop App bằng tài khoản hiện có của Odoo.

Luồng:

```text
Desktop Sync App
      |
      | credentials / auth request
      v
Odoo Authentication
      |
      +-- Validate account
      +-- Validate active user
      +-- Check Sync App permission
      |
      +-- allowed --> authenticated session/token
      |
      +-- denied  --> access denied
```

Điều kiện tối thiểu để sử dụng Sync App:

```text
User active
AND
User thuộc group Sync App / User hoặc cao hơn
```

User có thể sử dụng web Odoo bình thường nhưng không được sử dụng Desktop Sync App nếu không có group tương ứng.

### 22.1. Không lưu password trong Sync module

`medilab_sync` không có credential riêng.

Identity luôn tham chiếu:

```text
res.users
```

Ví dụ:

```text
sync.device.user_id -> res.users
sync.folder.user_id -> res.users
sync.file.version.created_by -> res.users
sync.audit.log.user_id -> res.users
```

### 22.2. Dùng Odoo permission thay vì account riêng

Đề xuất group:

```text
Sync App / User
Sync App / Manager
Sync App / Admin
```

Có thể mở rộng thành các quyền chi tiết hơn:

```text
SYNC_APP_ACCESS
SYNC_UPLOAD
SYNC_DOWNLOAD
SYNC_TWO_WAY
SYNC_VIEW_HISTORY
SYNC_RESTORE_VERSION
SYNC_RESOLVE_CONFLICT
SYNC_ADMIN
```

Trong Odoo, quyền được triển khai bằng:

- `res.groups`
- `ir.model.access.csv`
- Record Rules
- Permission check trong controller/service

Không chỉ check quyền lúc login. Mỗi API quan trọng phải enforce permission server-side.

## 23. Realtime Notification / WebSocket

WebSocket được dùng để **giảm latency khi có thay đổi**, không được dùng làm nguồn duy nhất để đảm bảo consistency.

Ví dụ event:

```text
FILE_VERSION_CREATED
FILE_CHANGED
FILE_DELETED
CONFLICT_CREATED
DOCUMENT_LOCKED
DOCUMENT_UNLOCKED
SYNC_RULE_UPDATED
```

Ví dụ:

```json
{
  "type": "FILE_VERSION_CREATED",
  "fileId": "...",
  "version": 18
}
```

Desktop nhận event:

```text
WebSocket event
      |
      v
Treat as invalidation signal
      |
      v
Query authoritative metadata/cursor
      |
      v
Download queue if required
```

### 23.1. Phase 1-3: có thể dùng WebSocket của Odoo

Odoo 19 có dedicated gevent/WebSocket worker trong multiprocessing deployment.

Vì vậy không cần tách Go service ngay từ MVP chỉ vì có WebSocket.

Cần:

- Reverse proxy route `/websocket/` đúng vào gevent worker.
- Monitoring connection count.
- Monitoring memory/CPU.
- Reconnect strategy.
- Heartbeat.
- Backoff.
- Reconciliation sau reconnect.

### 23.2. Khi nào cân nhắc tách WebSocket Hub

Nếu số lượng Desktop clients và event rate tăng đủ lớn, có thể tách realtime fan-out:

```text
                    +----------------+
                    |      Odoo      |
                    |  transaction   |
                    +-------+--------+
                            |
                     committed event
                            |
                    +-------v--------+
                    | Event Transport |
                    +-------+--------+
                            |
                    +-------v--------+
                    | Go WebSocket Hub|
                    +---+---+---+----+
                        |   |   |
                        v   v   v
                      PC1  PC2  PC3
```

Go phù hợp với số lượng lớn connection dài hạn, nhưng đây là **scale-out optimization**, không phải dependency bắt buộc cho Phase 1.

### 23.3. Redis Pub/Sub không phải durability layer

Không nên thiết kế:

```text
DB commit
   |
Redis Pub/Sub
   |
WebSocket
```

rồi coi event đó là bằng chứng duy nhất rằng client đã nhận thay đổi.

Redis Pub/Sub có thể dùng cho fan-out realtime, nhưng message bị miss khi subscriber disconnect.

Sync correctness phải dựa vào:

```text
PostgreSQL metadata
version number
change sequence / cursor
reconciliation
```

Nếu cần reliable event delivery giữa Odoo và realtime service, cân nhắc:

- Transactional outbox.
- Redis Streams.
- Durable message broker.
- Một cơ chế event log có replay.

### 23.4. Recommended pattern

```text
Odoo transaction
      |
      +--> commit metadata + outbox record
                    |
                    v
              event publisher
                    |
                    v
         realtime transport / hub
                    |
                    v
               Desktop App
                    |
                    v
        fetch authoritative state
```

WebSocket giúp nhanh; reconciliation/cursor giúp đúng.

## 24. Odoo Module: `medilab_sync`

Sync feature được triển khai thành một module riêng trong Odoo:

```text
medilab_sync/
├── __manifest__.py
├── models/
├── controllers/
├── security/
├── views/
├── data/
└── services/
```

### 24.1. Models đề xuất

```text
sync.device
sync.folder
sync.rule
sync.file
sync.file.version
sync.conflict
sync.audit.log
sync.upload.session
```

Các model liên kết trực tiếp tới `res.users`.

Ví dụ:

```python
user_id = fields.Many2one("res.users", required=True)
```

### 24.2. Security Groups

```text
Sync App / User
Sync App / Manager
Sync App / Admin
```

#### Sync App / User

- Được sử dụng Desktop Sync App.
- Được đăng ký device của chính mình.
- Được upload/download trong phạm vi được cấp quyền.
- Được xem trạng thái sync của chính mình.

#### Sync App / Manager

Bao gồm quyền User và thêm:

- Xem version history.
- Restore version nếu được cấp quyền.
- Resolve conflict.
- Xem audit trong phạm vi phụ trách.

#### Sync App / Admin

Bao gồm quyền Manager và thêm:

- Quản lý sync rules.
- Quản lý devices.
- Revoke device.
- Quản lý cấu hình.
- Xem audit toàn hệ thống.

### 24.3. Server-side authorization

Các API cần kiểm tra quyền:

```text
/upload
/download
/version/history
/version/restore
/conflict/resolve
/device/register
/device/revoke
/sync-folder/*
```

ACL kiểm soát quyền CRUD trên model.

Record Rules kiểm soát user được truy cập record nào.

Ví dụ:

```text
Technician
=> chỉ thấy file/sample/phòng ban được phân công

Manager
=> thấy dữ liệu thuộc laboratory/phạm vi mình quản lý

Admin
=> quyền toàn hệ thống
```

## 25. Data Model cấp cao

```text
User
 |
 +-- Device
 |
 +-- SyncFolder
       |
       +-- SyncRule

File
 |
 +-- FileVersion
       |
       +-- created_by User
       +-- created_by Device

File
 |
 +-- Conflict

File
 |
 +-- AuditLog

File
 |
 +-- UploadSession
```

---

## 26. Entity đề xuất

### User

```text
id
username
email
display_name
status
created_at
```

### Device

```text
id
user_id
name
os
app_version
last_seen_at
revoked_at
```

### SyncFolder

```text
id
user_id
device_id
local_path
remote_root_id
sync_mode
enabled
```

### SyncRule

```text
id
sync_folder_id
type
pattern
extensions
recursive
```

### File

```text
id
parent_id
name
logical_path
current_version_id
created_at
```

### FileVersion

```text
id
file_id
version_number
parent_version_id
storage_key
hash
size
created_by_user_id
created_by_device_id
source
created_at
```

### Conflict

```text
id
file_id
server_version_id
client_version_id
status
resolved_by
resolved_at
```

### UploadSession

```text
id
file_id
user_id
device_id
size
hash
chunk_size
status
expires_at
```

### AuditLog

```text
id
user_id
device_id
file_id
version_id
action
metadata
created_at
```

---

## 27. Trạng thái file trên Desktop

UI có thể hiển thị:

```text
✓ Synced

↑ Uploading

↓ Downloading

⟳ Pending

! Failed

Conflict

Online only

○ Local only
```

---

## 28. System Tray

Khi đóng cửa sổ:

```text
App UI closes
```

nhưng sync engine vẫn chạy.

System tray:

```text
Laboratory Sync

✓ All files synced

Open App
Pause Sync
Resume Sync
View Errors
Settings
Quit
```

---

## 29. Auto Start

Sau khi user bật:

```text
Start Laboratory Sync when computer starts
```

app tự chạy khi user đăng nhập OS.

Có thể khởi động ở background mà không cần mở main window.

---

## 30. Offline Support

Desktop app phải hoạt động được khi mất mạng.

Ví dụ:

```text
Network offline

User edits:
ABC_001.xlsx
ABC_002.xlsx
ABC_003.docx
```

SQLite lưu:

```text
3 pending upload jobs
```

Khi có mạng:

```text
Online
  |
  v
Process queue
  |
  v
Check server version
  |
  +-- no conflict -> upload
  |
  +-- conflict -> conflict state
```

---

## 31. Retry Strategy

Có thể sử dụng exponential backoff.

Ví dụ:

```text
1s
2s
4s
8s
15s
30s
60s
```

Không retry vô hạn với lỗi permanent như:

```text
403
invalid rule
file rejected
permission denied
```

Retry với:

```text
timeout
connection reset
502
503
504
```

---

## 32. Security

Các yêu cầu security cơ bản:

- HTTPS bắt buộc.
- JWT short-lived.
- Refresh token rotation.
- Secure token storage.
- Device registration.
- Server-side permission check.
- Signed S3 upload/download URL.
- File checksum validation.
- Rate limiting.
- Audit log.
- Optional antivirus scan.
- Optional file encryption.
- Role-based access control.

---

## 33. Permission Model

Có thể hỗ trợ:

```text
ADMIN
LAB_MANAGER
TECHNICIAN
VIEWER
```

Permission theo:

- Project.
- Sample.
- Folder.
- File.
- Department.
- Laboratory.

Ví dụ:

```text
Technician A
=> Lab Chemistry

Technician B
=> Lab Microbiology
```

Không phải user nào cũng thấy mọi file.

---

## 34. Restore Version

User có permission có thể:

```text
Restore version 12
```

Không overwrite version history.

Thay vào đó:

```text
v12
  |
  v
create v19
```

v19 có metadata:

```text
source = RESTORE
restored_from = v12
```

History luôn immutable.

---

## 35. Delete Strategy

Không nên hard delete ngay.

Nên:

```text
Soft Delete
```

hoặc Trash.

Ví dụ:

```text
File deleted locally
        |
        v
Mark deleted
        |
        v
Create delete event
```

Admin có retention policy.

Ví dụ:

```text
Trash retention = 30 days
```

---

## 36. Observability

Server cần:

- Structured logging.
- Metrics.
- Tracing.
- Health check.

Ví dụ metrics:

```text
active_devices
pending_uploads
failed_uploads
upload_bytes
download_bytes
sync_conflicts
onlyoffice_sessions
api_latency
```

Có thể sử dụng:

```text
Prometheus
Grafana
OpenTelemetry
```

---

## 37. Deployment

Production deployment phải cho Desktop truy cập trực tiếp S3/MinIO data endpoint bằng TLS.

Reverse proxy/Odoo không nên proxy file payload lớn nếu không có yêu cầu hạ tầng đặc biệt.

Luồng network:

```text
Desktop ---> Odoo HTTPS
            auth/control/metadata

Desktop ---> MinIO/S3 HTTPS
            large file data

Odoo -----> PostgreSQL
Odoo -----> MinIO/S3 metadata verification
Odoo <---> ONLYOFFICE
```



Ví dụ production deployment:

```text
Reverse Proxy
     |
     +--> Odoo Backend
     |
     +--> ONLYOFFICE
     |
     +--> MinIO Console/API

PostgreSQL

Redis
```

Có thể chạy bằng:

```text
Docker Compose
```

hoặc:

```text
Podman Compose
```

---

## 38. Repository Structure đề xuất

```text
laboratory-sync/
│
├── apps/
│   ├── desktop/
│   │   ├── src/
│   │   └── src-tauri/
│   │
│   └── admin-web/
│
├── services/
│   └── api/
│
├── packages/
│   └── shared/
│
├── deploy/
│   ├── compose/
│   ├── nginx/
│   ├── onlyoffice/
│   └── minio/
│
├── docs/
│   ├── architecture/
│   ├── api/
│   └── sync-protocol/
│
└── README.md
```

---

# 39. MVP Roadmap

## Phase 1 - Background Upload

Mục tiêu:

Xây dựng một sync client ổn định trước.

Features:

- Login.
- Device registration.
- Choose folder.
- Prefix/Glob rule.
- File watcher.
- Debounce.
- Hash.
- SQLite.
- Upload queue.
- Direct-to-MinIO/S3 multipart upload bằng presigned URL.
- UploadSession + finalize verification.
- Orphan upload cleanup.
- Retry.
- Resume.
- System tray.
- Auto start.
- Upload-only sync.
- Basic audit.

Không làm:

- Two-way sync.
- ONLYOFFICE.
- Conflict UI phức tạp.

---

## Phase 2 - Version History

Features:

- Immutable FileVersion.
- User history.
- Device history.
- Version list.
- Download version.
- Restore version.
- Deduplication.
- Audit log.
- Admin file viewer.

---

## Phase 3 - Two-way Sync

Features:

- Odoo WebSocket notification.
- Change cursor/reconciliation sau reconnect.
- Server change notification.
- Download queue.
- Atomic download.
- Remote delete.
- Conflict detection.
- Conflict UI.
- Multi-device consistency.
- Load test WebSocket/gevent worker.
- Chỉ tách Go WebSocket Hub nếu connection/event volume thực tế yêu cầu.

---

## Phase 4 - ONLYOFFICE

Features:

- Self-host ONLYOFFICE.
- Open DOCX.
- Open XLSX.
- Open PPTX.
- User identity integration.
- Co-editing.
- Save callback.
- FileVersion integration.
- Audit integration.

---

## Phase 5 - Laboratory Integration

Features:

- Sample-based folder mapping.
- LIMS integration.
- Permission by sample/project.
- Approval workflow.
- File locking policy.
- Electronic signatures.
- Advanced audit.
- Retention policy.
- Report generation.
- Device/instrument integration.

---

# 40. Những vấn đề cần chốt trước khi development

## 40.1. File ownership

Cần xác định:

```text
File thuộc về:
- User?
- Sample?
- Project?
- Department?
- Laboratory?
```

Khuyến nghị:

```text
File thuộc Sample/Project
```

không thuộc một user cụ thể.

---

## 40.2. Local path mapping

Ví dụ cùng một remote folder:

```text
/SAMPLE-001
```

có thể map:

Máy A:

```text
D:\Lab\SAMPLE-001
```

Máy B:

```text
C:\Users\Lab\Samples\SAMPLE-001
```

Do đó server không nên phụ thuộc absolute local path.

---

## 40.3. Delete behavior

Cần chốt:

```text
Delete local
=> delete server?

Delete server
=> delete local?
```

Nên có setting riêng cho từng sync mode.

---

## 40.4. Rename

Cần phân biệt:

```text
rename
```

với:

```text
delete old + create new
```

Có thể dùng combination:

```text
file identity
hash
filesystem event
```

---

## 40.5. File size

Cần chốt maximum:

```text
100 MB?
1 GB?
10 GB?
```

để thiết kế chunk size và retention.

---

## 40.6. File retention

Cần chốt:

```text
giữ tất cả version?
90 ngày?
1 năm?
theo SOP?
```

Trong môi trường kiểm nghiệm có thể cần retention dài hạn.

---

## 40.7. Concurrent editing policy

Cần quyết định:

```text
Office document
=> ONLYOFFICE collaboration

Desktop Office edit
=> allowed?
```

Nếu allowed thì conflict detection vẫn bắt buộc.

---

# 41. Nguyên tắc thiết kế quan trọng

## 41.1. Server là source of truth

Local machine không phải nguồn sự thật duy nhất.

Server giữ:

- Metadata.
- Version graph.
- Audit.
- Permission.
- Current version.

---

## 41.2. FileVersion immutable

Version cũ không được chỉnh sửa.

Mọi thay đổi tạo version mới.

---

## 41.3. Không silent overwrite

Nếu concurrent edit:

```text
CONFLICT
```

không ghi đè.

---

## 41.4. Upload phải resumable

Upload file lớn phải có chunk/resume.

---

## 41.5. Download phải atomic

Không ghi file partial lên đường dẫn chính.

---

## 41.6. Offline-first desktop

Desktop agent không được phụ thuộc hoàn toàn vào network.

Queue phải tồn tại sau restart.

---

## 41.7. Audit by design

Mọi thao tác quan trọng phải có:

```text
who
when
where
what
which device
which version
```

---

## 41.8. Tách Control Plane khỏi Data Plane

Odoo xử lý quyền và metadata.

MinIO/S3 xử lý payload file lớn.

```text
Control Plane -> Odoo
Data Plane    -> MinIO/S3
```

Không đưa file 500 MB - 1 GB xuyên qua Odoo nếu không có lý do đặc biệt.

---

## 41.9. Realtime không thay thế Reconciliation

Mất WebSocket event không được làm hệ thống sai dữ liệu.

Client luôn có khả năng lấy lại state bằng:

```text
version/cursor + reconciliation
```

---

## 41.10. Raw Evidence là immutable

Dữ liệu gốc do thiết bị kiểm nghiệm sinh ra nên được lưu append-only khi nghiệp vụ cho phép.

Không overwrite hoặc discard raw evidence trong quá trình conflict resolution.

---

## 41.11. Khả năng tách Sync Service trong tương lai

Dùng chung database với Odoo ở giai đoạn đầu không khóa kiến trúc vĩnh viễn.

Hiện tại:

```text
Desktop
   |
   v
Odoo + medilab_sync
   |
   v
Shared PostgreSQL
```

Nếu Sync lớn lên:

```text
                 Odoo
                  |
             user identity
                  |
                  v
Desktop ---> Sync Service
                  |
                  v
              Sync DB
```

Để giữ khả năng migration:

- Desktop không truy cập DB trực tiếp.
- Desktop chỉ gọi API.
- Models Sync nằm trong module/namespace riêng.
- File binary nằm ngoài PostgreSQL.
- Dùng identifier ổn định cho user/file/device.
- Business logic Sync nên có service layer rõ ràng thay vì phụ thuộc chặt vào controller.


---

# 41.12. Design Review - Các bottleneck đã được xử lý

## Odoo I/O bottleneck

**Kết luận:** Góp ý đúng.

Giải pháp chính thức:

```text
Odoo = authorization + metadata
MinIO/S3 = binary data plane
```

Desktop transfer trực tiếp bằng temporary presigned authorization.

## File Watcher OS limits

**Kết luận:** Góp ý đúng.

Native watcher chỉ là fast path.

Reconciliation luôn tồn tại; khi watcher degraded có thể fallback sang polling.

## WebSocket scaling

**Kết luận:** Đúng về rủi ro scale, nhưng chưa phải lý do để tách service ngay.

Odoo WebSocket/gevent worker được sử dụng trước.

Go WebSocket Hub chỉ được tách khi load test/metrics cho thấy cần thiết.

Realtime event không phải consistency source.

## Binary conflict

**Kết luận:** Góp ý đúng và được siết chặt hơn.

Binary conflict phải preserve both versions.

"Keep server" chỉ được phép thay đổi canonical version sau khi conflicting artifact đã được lưu immutable; không được xóa evidence.

Raw instrument data nên ưu tiên append-only để tránh conflict ngay từ mô hình dữ liệu.

---

# 42. Kết luận

Kiến trúc đề xuất:

```text
Desktop
Tauri 2
Rust
React
SQLite

        |

Control Plane
REST + WebSocket
        |
        v
Odoo 19 / Python
PostgreSQL dùng chung
Odoo ACL / Record Rules

Data Plane
Desktop <---- direct multipart ----> S3 / MinIO
        via temporary presigned authorization

        |

Document Collaboration
ONLYOFFICE Document Server
```

Hệ thống được chia thành hai bài toán riêng:

### File Synchronization

Được xử lý bởi:

```text
Tauri + Rust Sync Engine
```

Bao gồm:

- Folder watcher.
- Background upload.
- Offline queue.
- Resume.
- Two-way sync.
- Versioning.
- Conflict detection.

### Office Collaboration

Được xử lý bởi:

```text
ONLYOFFICE Document Server
```

Bao gồm:

- DOCX/XLSX/PPTX editing.
- Multi-user editing.
- Realtime collaboration.
- Track changes.

Backend của hệ thống đóng vai trò trung tâm:

```text
Authentication
Metadata
Permissions
Versioning
Audit
Storage orchestration
ONLYOFFICE integration
Realtime events
```

Cách tiếp cận này tránh việc tự xây dựng một Google Docs/Excel collaborative engine từ đầu, đồng thời vẫn giữ được khả năng đồng bộ file nền trên nhiều máy tính và nhiều phòng kiểm nghiệm.

MVP nên bắt đầu từ:

```text
Login
Choose Folder
Sync Rules
Background Upload
SQLite Queue
Retry/Resume
Version History
Audit
```

sau đó mới mở rộng sang:

```text
Two-way Sync
Conflict Handling
ONLYOFFICE Collaboration
LIMS Integration
Advanced Laboratory Audit
```
