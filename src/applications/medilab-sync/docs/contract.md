# Laboratory File Sync — contract

## Authentication

1. Desktop gửi username/password tới `POST /api/sync/v1/auth/login`.
2. Server kiểm tra user đang active và thuộc Sync App / User.
3. Server đăng ký/cập nhật `sync.device` và tạo key `res.users.apikeys` gắn với thiết bị đó.
4. API key chỉ trả về một lần. **Production luôn bắt buộc kho lưu trữ bảo mật của OS** (Linux Secret Service, Windows Credential Manager, macOS Keychain). **Không có fallback ngầm sang file**. Khi dev trên Linux có thể đặt `MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING=true` (`task sync-app:dev` chỉ làm vậy trên Linux) để lưu key vào file `0600` `device.apikey` trong thư mục dữ liệu của app. Mật khẩu không bao giờ được lưu. API key không bao giờ được ghi vào SQLite, JSON, log hay state React. Odoo 19 bắt buộc có ngày hết hạn; key Phase 1 hết hạn sau 90 ngày (mức tối đa của server) và đăng nhập sẽ cấp key mới.
5. Các lần gọi sau gửi `Authorization: Bearer <api_key>` và `X-Sync-Device-Id`.
5a. **Keyring là nơi lưu bền, bộ nhớ tiến trình là credential đang dùng.** App đọc keyring đúng một chỗ — `restore_session` lúc khởi động (hoặc khi người dùng bấm “Thử lại”) — rồi giữ key trong bộ nhớ Rust (`auth::Session`, không `Debug`/`Serialize`, không gửi qua IPC). Mọi request, job và `status_snapshot` dùng key trong bộ nhớ: với Secret Service, đọc một item đang khóa sẽ bật hộp thoại mở khóa của OS và chặn luồng gọi, nên keyring bị khóa giữa chừng không được phép ảnh hưởng phiên đang chạy. `StatusDto.auth_state` có bốn giá trị: `authenticated`, `missing_credentials`, `session_expired` (chỉ khi **Odoo** trả 401 — key hết hạn/bị thu hồi hoặc thiết bị bị thu hồi), `credential_store_locked` (keyring khóa/không đọc được lúc khởi động; không xóa, không thu hồi, không coi là hết hạn). Mất mạng, 5xx, 403/404 của thư mục, và 401 của dịch vụ khác (MinIO presigned, ONLYOFFICE, updater) không bao giờ làm hết phiên.
6. Đăng xuất thu hồi key của thiết bị. User Odoo không bị xóa. Đăng nhập bằng mật khẩu với cùng `client_uid` kích hoạt lại thiết bị đó và cấp key mới; key trước vẫn vô hiệu.

## `/api/sync/v1` contract

| Method | Path | Mục đích |
| --- | --- | --- |
| POST | `/auth/login` | Đăng nhập bằng mật khẩu, đăng ký thiết bị, trả API key một lần |
| POST | `/auth/logout` | Thu hồi key của thiết bị hiện tại |
| GET | `/me` | User + thiết bị hiện tại |
| GET/POST | `/folders` | Liệt kê thư mục user đã xác thực được dùng (chủ sở hữu hoặc `sync.folder.member`). POST dùng lại `(user, logical_root)` của chính người gọi mà không đổi `device_id`; nếu user đã là thành viên của một thư mục có `logical_root` đó thì gắn id đó (không tự join theo tên cho người lạ). Mỗi thư mục mang thêm `owner_name`, `my_role` (`owner` / `upload` = thành viên đọc + ghi / `manager`) và `can_manage_members`; client cũ bỏ qua được. |
| PATCH | `/folders/{id}` | Đổi `name` (chủ sở hữu/Sync Manager). Đổi `enabled` — bật/tắt thư mục **cho mọi người** — chỉ Sync Manager/Admin (403 với chủ sở hữu và thành viên). Desktop không bao giờ gửi `enabled`: “Ngừng đồng bộ” chỉ bỏ binding cục bộ, và upload không tự bật lại thư mục. `POST /folders` lên thư mục đã có không đổi `enabled`. Thư mục đang tắt: `/uploads/prepare` trả 403 `Folder is disabled`; đọc/tải xuống vẫn được. |
| POST/PATCH/DELETE | `/folders/{id}/rules` | CRUD rule |
| GET | `/folders/{id}/members` | `{folder_id, owner{id,name}, my_role, can_manage_members, mapped, members[{id, user{id,name,login}, role, effective_access}]}`. Chủ sở hữu/Sync Manager nhận đủ danh sách; thành viên thường chỉ nhận dòng của chính mình. `effective_access=false` = là thành viên nhưng chưa thấy mẫu đã map trong LIMS. |
| POST | `/folders/{id}/members` | Body `{"userId": <id>}`; server luôn gán vai trò `upload`, gửi thêm field bị 422. Chỉ chủ sở hữu/Sync Manager (403). 201; 400 user không hợp lệ (một thông báo chung); 409 đã là thành viên. |
| DELETE | `/folders/{id}/members/{member_id}` | Gỡ thành viên. Chỉ chủ sở hữu/Sync Manager (403). 404 nếu `member_id` không thuộc thư mục này; 409 với dòng chủ sở hữu. |
| GET | `/folders/{id}/member-candidates?q=` | Tìm user thêm được: `q` ≥ 2 ký tự (400), tối đa 10, chỉ `id/name/login`; chỉ user nội bộ active thuộc group Sync và chưa là thành viên. Chỉ chủ sở hữu/Sync Manager của thư mục đó (403). Không có API tìm user chung. |
| POST | `/uploads/prepare` | Cấp object key, bắt đầu multipart, tạo session |
| POST | `/uploads/{id}/parts/presign` | URL UploadPart ngắn hạn. Kiểm lại quyền thư mục hiện tại (404 nếu đã bị gỡ) |
| POST | `/uploads/{id}/finalize` | Server CompleteMultipartUpload + phiên bản/xung đột. Kiểm lại quyền thư mục hiện tại (404 nếu đã bị gỡ) |
| GET | `/files/{id}` | Metadata file + `version_count` (tổng hợp, không tải toàn bộ lịch sử) |
| GET | `/files/{id}/versions` | Lịch sử phân trang, `version_number` mới nhất trước. `limit` mặc định 20, tối đa 100. List **không** HEAD MinIO. |
| GET | `/files/{id}/versions/{version_id}` | Chi tiết phiên bản; `object_available` lấy từ một lần HEAD |
| POST | `/files/{id}/versions/{version_id}/restore` | Tạo phiên bản RESTORE **mới**; không viết lại lịch sử |
| GET | `/folders/{id}/changes` | Change feed bền vững. `after` = `sync.change.id` đã xử lý cuối cùng. Limit mặc định 50, tối đa 100. Sắp theo `id` tăng dần. |
| GET | `/folders/{id}/files` | Metadata file hiện tại, phân trang, để reconciliation. Mặc định/tối đa giống changes. Cũng là nguồn hydrate ngay sau khi gắn một folder có sẵn (không chờ chu kỳ). Chủ sở hữu và thành viên đều đọc được, kể cả tệp do thiết bị của người khác tải lên (`current_version.device` chỉ gồm id + tên). |
| POST | `/files/{id}/versions/{version_id}/download` | Cấp quyền presigned GET ngắn hạn cho phiên bản đó. Không stream byte qua Odoo. |
| GET | `/health` | Liveness. Không cần xác thực. Không probe MinIO hay ONLYOFFICE. |
| GET | `/ready` | Snapshot readiness (odoo/postgres/minio/onlyoffice). HTTP 200 nếu Odoo query được PostgreSQL. MinIO down → `status=degraded`. ONLYOFFICE down không làm hỏng sync lõi. |
| GET | `/office/health` | Readiness của Document Server. Không cần xác thực. Không bao giờ làm hỏng khởi động Odoo. |
| POST | `/files/{id}/office/session` | Mở hoặc tham gia session ONLYOFFICE đang hoạt động. Trả về editor config đã ký. |
| POST | `/office/callback/{callback_token}` | Callback của Document Server. Bắt buộc JWT. Không phải route dùng API key thiết bị. |
| POST | `/files/{id}/approvals` | Yêu cầu review một phiên bản **canonical** |
| POST | `/approvals/{id}/decide` | Người review duyệt/từ chối (`approved`/`rejected`). Actor là user đã xác thực |
| POST | `/files/{id}/signoffs` | Ký duyệt điện tử có xác thực cho một phiên bản canonical (hash lấy phía server từ dòng phiên bản) |
| POST/DELETE | `/files/{id}/lock` | Lấy/gia hạn hoặc nhả khóa độc quyền (chỉ WORKING/RESULT không phải Office) |
| POST | `/files/{id}/lock/force` | Quản lý buộc nhả khóa |
| GET | `/lab/samples/{id}/trace` | Truy vết phân trang cho một `danh.sach.mau` mà người gọi thấy được |

JSON dùng snake_case (`login`, `logical_root`, `content_hash`, `checksum_algorithm`, `base_version_id`, `part_number`, `etag`). Alias được chấp nhận. Field số nguyên tùy chọn như `session_id` / `version_id` trên `/uploads/prepare` là JSON `null`, không bao giờ là Odoo `false`.

DTO phiên bản gồm tên actor/thiết bị, `is_canonical`, `parent_version_id`, `restored_from_version_id`, và `object_available` tùy chọn. Chúng **không** chứa API key, presigned URL hay `storage_key`.

Phân quyền theo tư cách thành viên thư mục: phiên bản → file → thư mục → chủ sở hữu/thành viên. Người ngoài nhận HTTP 404, không lộ metadata. **Sync App / User** được xem lịch sử và khôi phục bất kỳ phiên bản nào của file mà họ truy cập được. Ẩn trên UI không phải là phân quyền.

## Two-way decision matrix

So sánh SHA-256, không so mtime. `B` = hash đã sync lần cuối, `L` = hash local hiện tại, `R` = hash canonical trên server.

| Trường hợp | Hành động |
| --- | --- |
| `L == B`, `R` đổi | Download `R` |
| `L` đổi, `R == B` | Upload (đường Phase 1 có sẵn) |
| `L` đổi và `R` đổi và `L != R` | Xung đột. Giữ byte local. Canonical trên server giữ nguyên. |
| `L == R` | Tiến base / xác nhận cursor. Không download, không upload thêm (self-echo). |

RESTORE của Phase 2 tạo phiên bản canonical mới cũng chỉ là trường hợp `R` đổi. Desktop sạch sẽ download phiên bản đó.

Tạm dừng áp dụng cho worker **upload và download**. Việc phát hiện thay đổi vẫn có thể enqueue job; truyền binary không chạy cho tới khi tiếp tục.
Job đang truyền lúc bấm tạm dừng dừng trong khoảng 250 ms: không part mới nào được lên lịch, mọi part upload đang gửi bị hủy (request HTTP bị drop, part đó không có ETag và được đọc, hash và PUT lại khi tiếp tục; S3/MinIO ghi đè part cùng số), download dừng sau chunk vừa nhận. Job trở về `pending` mà không tăng `attempt_count` hay ghi lỗi. ETag các part đã upload xong và file tạm download được giữ, nên khi tiếp tục job chạy tiếp từ chỗ dừng. Job bị tạm dừng hiện là `pending` không có lỗi; trạng thái tạm dừng hiện ở thẻ Paused của cửa sổ app.

## Concurrent transfers

Dispatcher (`src-tauri/src/sync/dispatcher.rs`) thay worker tuần tự: claim job cho slot trống và chạy song song trong `JoinSet`, không spawn vô hạn.

- **Slot:** mặc định 3 upload + 3 download (`UPLOAD_CONCURRENCY`, `DOWNLOAD_CONCURRENCY`), tối đa 6 transfer. Setting ẩn `upload_concurrency` / `download_concurrency` trong settings (không có trên UI) đổi được số slot, kẹp `1..=4`, áp dụng khi app khởi động (xem [maintenance](maintenance.md)). Upload và download có semaphore riêng nên upload lớn không chiếm slot của download. Trong mỗi loại, slot 0 chỉ nhận job ≤ 16 MiB (`SMALL_TRANSFER_BYTES`, một part), nên tệp nhỏ không phải xếp sau tệp lớn; tệp lớn dùng tối đa 2 slot mỗi loại. FIFO theo `id` trong từng loại.
- **Mỗi tệp tối đa một transfer:** claim bỏ qua tệp đang có job `running` bất kể thao tác (xem [database](database.md)). Upload và download của cùng tệp không bao giờ chạy đồng thời.
- **Multipart của một tệp:** tối đa `part_concurrency` PUT song song cho mỗi tệp, dưới ngân sách buffer chung 128 MiB (xem [Direct MinIO upload](#direct-minio-upload)). Pause hay lỗi dừng lên lịch part mới, lưu ETag của mọi PUT đã xong, và hủy các PUT dở (không có ETag, gửi lại khi resume).
- **Tạm dừng:** dispatcher ngừng claim; mọi transfer đang chạy dừng trong khoảng 250 ms (part upload đang gửi bị hủy, download dừng sau chunk hiện tại) và về `pending` không tăng `attempt_count`.
- **Tiếp tục** (`start_sync`) tắt cờ tạm dừng, lưu settings rồi trả về ngay; poll change feed + đối soát toàn bộ chạy nền (qua `reconcile_gate`, lỗi được log), và các lần Tiếp tục dồn dập trong lúc lượt nền đang chạy được gộp thành đúng một lượt chạy tiếp. Nút Tạm dừng/Tiếp tục trên header chỉ bị khóa khi chính lệnh đó đang chạy, không theo các lệnh khác của app (gắn thư mục, đối soát…), nên luôn dừng được transfer đang chạy.
- **Mất quyền folder:** job của folder `denied` không được claim. Transfer đang chạy đọc lại quyền folder tối đa mỗi giây ở điểm an toàn; folder đã `denied` thì dừng và về `pending` với “Mất quyền truy cập — đồng bộ đã tạm dừng.”. Nhiều job cùng gặp 403 chỉ gọi đối chiếu `GET /folders` một lần mỗi 5 giây.
- **Retry:** backoff 1→60 giây cộng jitter ngẫu nhiên tới 1/4 mức nền. Lỗi kết nối mạng (timeout, không kết nối được, mất kết nối giữa chừng — phân loại theo loại lỗi reqwest/`io::ErrorKind`, không theo chuỗi) thử lại vô hạn vì máy PTN có thể mất mạng lâu. Lỗi server/storage/ứng dụng đáng thử lại (5xx, presigned bị từ chối lặp lại, tệp đổi liên tục, 409) dừng ở lần thứ 20 (`MAX_SERVER_ERROR_ATTEMPTS`): job thành `failed` với “Đã thử 20 lần: …”. Nút Thử lại (một job hoặc cả folder) đặt lại `attempt_count = 0`.
- **Version mới trong lúc chạy:** xem `rerun_requested` trong [database](database.md).
- **Log:** mỗi transfer có `transfer started` / `transfer finished` với `job_id`, `file_id`, `operation`, `slot`, `duration_ms` (không có API key hay query presigned).
- Mọi request đã xác thực tới Odoo từ cùng thiết bị có thể song song; server chỉ ghi `sync.device.last_seen_at` tối đa mỗi phút để các request không tranh ghi một dòng.

## Direct MinIO download

1. Odoo cấp quyền `POST /files/{id}/versions/{vid}/download` (tư cách thành viên, phiên bản thuộc file, object tồn tại).
2. Response là presigned GET ngắn hạn kèm size/SHA-256/version id mong đợi. Không có credential vĩnh viễn. Không có `storage_key` do client chọn.
3. Rust GET trực tiếp MinIO. Presigned URL không bao giờ tới React. Query string không được ghi log.
4. Byte ghi vào `{name}.medilab-download-{job_id}.tmp` trong cùng thư mục. Size + SHA-256 phải khớp trước khi thay thế.
5. Sau fsync, rename atomic đè lên file đang dùng. File tạm chưa hoàn tất không bao giờ được đưa lên. File tạm cũ không có job đang chạy bị xóa khi khởi động.
6. Chặn watcher: `suppress_hash` / hash đã sync lần cuối bằng digest vừa download, cộng với bỏ qua tên `.medilab-download-` và ` (conflict - `.
7. Cập nhật remote dồn dập: worker download luôn lấy metadata file **hiện tại** và download phiên bản đó, không phải mọi binary trung gian.
8. Resume bằng HTTP Range được dùng khi file tạm ngắn hơn object phiên bản bất biến mong đợi.
9. GET không có timeout tổng: file lớn trên mạng chậm là hợp lệ. Kết nối bị cắt khi quá 60 giây không nhận được byte nào (read timeout), rồi retry và resume bằng Range.

Nếu user chấp nhận bản trên server trong khi local khác, desktop trước tiên copy bản local sang `{stem} (conflict - {device} - {timestamp}){ext}`.

## Direct MinIO upload

1. Desktop chọn **expected hash** từ một lượt đọc toàn file độc lập: SHA-256 lưu lúc watcher/reconcile enqueue (`sync_file.sha256`) được dùng lại khi size và mtime (giây) hiện tại khớp dòng đó; không khớp thì hash lại toàn file và lưu làm dấu vân tay mới. Size/mtime chỉ quyết định có cần đọc lại hay không, không phải bằng chứng nội dung.
2. Odoo `prepare` với expected hash bắt đầu multipart trên endpoint **nội bộ** (`MAIN_BUCKET_ENDPOINT`, local `http://minio:9000`). Session cũ chỉ được tiếp tục khi hash đã lưu của nó bằng expected hash.
3. Desktop đọc tuần tự **mọi** part (kể cả part đã upload ở lượt trước, chỉ đọc để hash, không PUT lại) vào một hasher SHA-256 và PUT đúng buffer vừa hash tới URL **presigned public** (`PUBLIC_ENDPOINT`, local `http://localhost:29000`), dạng path-style. **Đọc và hash luôn tuần tự theo thứ tự part; chỉ PUT chạy song song**: tối đa `part_concurrency` PUT của một file cùng bay (mặc định 3, setting ẩn kẹp `1..=4`), mỗi PUT là một task riêng mang đúng buffer đã hash, nên server có thể trả các part lệch thứ tự. Buffer của mọi upload trong app nằm dưới một ngân sách bộ nhớ chung 128 MiB tính theo MiB (`PartBudget`): part lấy ngân sách *trước* khi đọc và giữ tới khi PUT xong hoặc bị hủy; part lớn hơn toàn bộ ngân sách làm job lỗi ngay thay vì chờ mãi. Chỉ task sở hữu job ghi ETag (theo thứ tự part) cùng `part_size` vào session sau mỗi PUT xong; thứ tự hoàn tất không quan trọng vì server kiểm đủ tập `1..N` lúc finalize. Desktop presign theo lô `max(part_concurrency, 4)` part ngay trước part đầu cần PUT và xin lại khi lô đã quá `expires_in` trừ 60 giây, tính từ lúc gửi presign. Storage trả 403 (URL hết hạn) thì desktop xin URL mới cho **đúng part đó** và gửi lại cùng buffer một lần, không đụng các part khác đang bay; lỗi lặp lại là lỗi server/storage đáng thử lại, tính vào trần 20 lần. Timeout của một PUT tăng theo kích thước part (tốc độ sàn 16 KiB/s, tối thiểu 120 giây).
4. Chỉ khi SHA-256 của các byte đã stream **bằng** expected hash thì desktop mới gọi `finalize` với số part + ETag. Khác nhau nghĩa là file đổi trước hoặc giữa lúc đọc (object trên MinIO có thể là trộn của hai trạng thái): desktop không finalize, bỏ session, hash lại file, và retry bằng lần prepare mới với hash mới.
5. `prepare` trả `deduplicated` hoặc `object_reused` thì không có byte nào được stream: desktop hash lại toàn file và chỉ ghi nhận hoàn tất khi bằng expected hash. Hash đã chứng minh được lưu vào job, nên `last_synced_hash` là đúng hash đó.
6. Odoo hoàn tất multipart trên endpoint nội bộ, HEAD object, kiểm `ContentLength`, rồi commit `sync.file.version` hoặc artifact xung đột.
7. File đổi **sau** khi part cuối đã được đọc: version vừa finalize vẫn đúng là snapshot đã chứng minh. Nếu size/mtime đã khác lúc bắt đầu, hoặc watcher đã ghi SHA-256 mới vào `sync_file` trong lúc upload, desktop xếp hàng ngay upload kế tiếp. Nếu thay đổi giữ nguyên size + mtime và không có sự kiện watcher, `last_synced_hash` vẫn là hash của bản đã upload nên lượt reconcile kế tiếp (300–900 giây) phát hiện và upload bản mới.

Ranh giới tin cậy: Odoo **không** đọc lại 5 GiB để tính lại SHA-256. ETag multipart không bao giờ được coi là SHA-256. Hash của client được lưu làm checksum đã commit; bước 4 là nơi desktop chứng minh hash đó là hash của đúng các byte đã PUT. Nếu sau này chế độ checksum của MinIO cung cấp SHA-256 toàn object với chi phí thấp, kiểm nó ở finalize mà không đổi contract này.

## Phase 4 — ONLYOFFICE

Document Server tự host (`onlyoffice` trong `applications/laboratory-file-sync-application/docker-compose.yml`, khởi động bằng `task sync-app:onlyoffice-up`, URL trình duyệt `http://localhost:28880`). JWT luôn bật (`ONLYOFFICE_JWT_SECRET`). Secret không bao giờ tới React, log hay response API. Odoo ký editor config và kiểm JWT của callback (Bearer hoặc `body.token`).

**Loại file:** `.docx` / `.xlsx` / `.pptx` (không phân biệt hoa thường). File khác chỉ giữ sync/lịch sử của Phase 1–3.

**Quyền:** chủ sở hữu thư mục hoặc thành viên `upload` được mở chế độ sửa. Config editor do server dựng đặt tường minh `customization.uiTheme = theme-gray` (theme sáng trung tính). Không đặt thì Document Server 8.x theo `prefers-color-scheme` của hệ điều hành: máy để dark sẽ ra thanh công cụ tối bao quanh trang tính vẫn sáng. `api.js` chuyển giá trị này cho iframe editor qua tham số `uitheme`; id mà Document Server không biết sẽ rơi về theme sáng mặc định, không rơi về tối. Khi app có theme tối thì đổi ở `services/office.py` (`OFFICE_UI_THEME`). Không chèn CSS vào iframe ONLYOFFICE. Người ngoài nhận 404. Download/in trong editor bị tắt.

**Nguồn tài liệu:** Document Server lấy `GET /office/source/{callback_token}` trên URL nội bộ của Odoo. Odoo stream phiên bản base của session từ MinIO. Editor config **không** nhúng query string presigned của MinIO. Download trên desktop vẫn dùng `POST .../download` + MinIO public.

**Status của callback:**

| Status | Ý nghĩa | MediLab |
| --- | --- | --- |
| 1 | đang sửa | chỉ activity / người tham gia |
| 2 | đóng và có thay đổi | stream byte, SHA-256+size, MinIO, phiên bản hoặc xung đột, đóng session |
| 3 | lỗi lưu | `state=error`, không có phiên bản |
| 4 | đóng, không thay đổi | đóng, không có phiên bản |
| 6 | force-save | chỉ activity — **không** có FileVersion |
| 7 | lỗi force-save | `state=error`, không có phiên bản |

Hash+size giống hệt ở status 2 thì đóng mà không tạo phiên bản mới (khác với RESTORE tường minh). URL callback phải có origin là Document Server (`http`/`https`); `localhost` được viết lại thành `ONLYOFFICE_INTERNAL_URL`. Gửi lại status 2 trả về `committed_version_id` / `conflict_id` đã có.

Ingest Office dùng cùng giới hạn 5 GiB `MAX_FILE_SIZE` như upload và stream ra file tạm (không phải buffer toàn bộ trong bộ nhớ). Bản thân Document Server cũng áp giới hạn chuyển đổi/editor riêng (mặc định của image là 100 MiB trừ khi đổi `local.json`).

**Optimistic concurrency:** base của office ≠ canonical hiện tại → artifact `source=CONFLICT` không canonical + `sync.conflict`. Canonical giữ nguyên. Không có `sync.change` cho artifact. Thành công (base == hiện tại, byte đổi) → `source=ONLYOFFICE`, `_set_canonical_version`, một dòng change-feed.

UI desktop: **Edit online** / **Chỉnh sửa trực tuyến** trên file được hỗ trợ. DocsAPI được tải từ `document_server_url`. API key Odoo không gửi tới React; JWT ONLYOFFICE trong `config.token` là thứ DocsAPI bắt buộc và không phải JWT secret.

`task onlyoffice-health` kiểm Document Server. Odoo và sync Phase 3 vẫn khởi động dù ONLYOFFICE down. `task restart` cũng khởi động lại converter của Document Server để nó không cache địa chỉ `odoo` cũ sau khi container Odoo nhận IP mới.

## Event cadence and delta IPC

Tách biệt rõ giữa ba loại sự kiện từ backend sang frontend:

1. **`upload-progress` & `download-progress` (delta):**
   - Payload: `{ jobId: number, done: number, total: number }`.
   - Chỉ cập nhật tiến độ cho duy nhất job tương ứng; giữ nguyên tham chiếu đối tượng của mọi job và folder khác.
   - Không phát lại `sync-status-changed` (không tạo full snapshot) trong vòng lặp multipart part của upload.
2. **`sync-status-changed` (full snapshot):**
   - Payload: `StatusDto`.
   - Chỉ phản ánh thay đổi vòng đời và trạng thái hệ thống: job hoàn tất/thất bại, đăng nhập/đăng xuất, tạm dừng, đổi quyền truy cập folder.
   - Không tự động kích hoạt `listRemoteFiles()`.
3. **`sync-files-changed` (file-list invalidation):**
   - Payload: `{ revision: number }`.
   - Phát khi danh sách tệp có thay đổi ngữ nghĩa: tệp cục bộ mới được enqueue, upload hoàn tất/xung đột, download hoàn tất, hydrate/poll phát hiện thay đổi trên server, giải quyết xung đột, hoặc gắn/gỡ folder.
   - Frontend dùng refresh controller (latest-only, tối đa một request in-flight, gộp các lượt gọi liên tiếp) để gọi `listRemoteFiles()`.

