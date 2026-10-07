# Laboratory File Sync — database

## Version model

State canonical trên server là `sync.file.current_version_id`. Khi con trỏ đó được đặt, tối đa một phiên bản có `is_canonical`.

- `parent_version_id` — phiên bản canonical trước đó (hoặc phiên bản hiện tại lúc đó) khi dòng này được tạo
- `restored_from_version_id` — phiên bản lịch sử mà dòng RESTORE này copy byte
- Khôi phục v1 trong khi v3 là hiện tại sẽ tạo v4: `parent=v3`, `restored_from=v1`, `source=RESTORE`, `current_version_id=v4`. v1 vẫn bất biến.

Artifact xung đột giữ `source=CONFLICT` và `is_canonical=false`. Khôi phục một artifact xung đột vẫn tạo phiên bản canonical RESTORE mới.

## Binary dedup vs version history

Định danh là SHA-256 **và** size, trong phạm vi **cùng** một `sync.file` (không chéo user, không chéo thư mục).

| Sự kiện | Có dòng phiên bản mới? | Có object MinIO mới? |
| --- | --- | --- |
| Upload khớp hash+size **hiện tại** | Không (`deduplicated: true`) | Không |
| Upload khớp một phiên bản **lịch sử** của cùng file | Có (`DESKTOP_SYNC`, `object_reused: true`) | Không — dùng lại `storage_key` |
| Khôi phục tường minh, kể cả khi byte khớp hiện tại | Có (`RESTORE`) | Không — dùng lại `storage_key` |
| Cùng hash trong thư mục của user khác | Không lộ; prepare cấp key mới | Có |

Dọn dẹp không được xóa object MinIO khi còn phiên bản đã commit tham chiếu `storage_key` của nó. Object bị mất vẫn để lịch sử hiển thị (`object_available=false` ở chi tiết); khi đó khôi phục lỗi HTTP 409.

`prepare` có thể trả `object_reused: true` kèm session và không có multipart. Desktop finalize với danh sách part rỗng. Khôi phục một file local sạch là một lần download Phase 3 của phiên bản canonical RESTORE mới.

Object key do Odoo cấp: `sync/{file_id}/{token}`. Desktop không bao giờ chọn bucket hay key.

## SQLite / offline

DB local: thư mục dữ liệu của OS `com.medilab.filesync/sync.sqlite`.

- WAL, foreign key, busy_timeout=5000
- Bảng: `sync_folder`, `sync_rule`, `sync_file`, `sync_job`
- “Ngừng đồng bộ” (`unregister_sync_folder`) chỉ xóa dòng thư mục local (CASCADE rule/file/job) — **không gọi server**, kể cả khi có `remote_id`, nên chạy được cả lúc offline. Thư mục trên server vẫn bật; rule, file, thành viên phía server và user/máy khác không bị ảnh hưởng; file trên đĩa không bị xóa. Thư mục đã bỏ binding hiện lại ở khối “Được chia sẻ với bạn” (thành viên) hoặc “Thư mục của bạn chưa đồng bộ trên máy này” (chủ sở hữu) và gắn lại theo remote id (`bind_shared_folder`, không POST). Đăng ký thư mục mới vẫn POST `/folders`. App không bao giờ bật/tắt thư mục trên server (không còn `PATCH enabled` nào trong client): thư mục bị Sync Manager tắt trả 403 `Folder is disabled` lúc prepare, job ở `retry_wait` với thông báo “tạm tắt” và tự chạy khi được bật lại. Thư mục bị client cũ tắt được bật lại một lần bởi migration `19.0.1.4.1` của `medilab_sync`.
- Job được lưu bền trước khi upload **hoặc** download
- Khi khởi động `running -> pending` (cả hai thao tác, mọi job đang chạy song song; `rerun_requested` được xóa vì job đã `pending`)
- **Hydrate lúc gắn folder.** `register_sync_folder` và `bind_shared_folder` đặt cờ bền `app_meta.needs_hydration:<local id>` rồi gọi ngay `hydrate_pending_folders`: (1) tua change feed tới đầu H mà không áp dụng, (2) liệt kê `GET /folders/{id}/files` và áp từng tệp hiện tại qua `plan_remote_change` (cùng logic quyết định/rule/xung đột với poll thường, không có lối tắt ghi đè), (3) lưu cursor = H. Nguồn là danh sách tệp hiện tại chứ không phải change feed: cursor `change_cursor:<remote id>` lưu theo remote id nên còn nguyên sau “Ngừng đồng bộ” → gắn lại, khi đó feed không trả gì. Hydrate lỗi (mất mạng, 5xx) giữ nguyên binding và cờ; mỗi lượt poll thử lại. Một tệp lỗi không chặn các tệp khác.
- Không có tệp cục bộ mà server có version chuẩn → luôn `Download`, kể cả khi base đã bằng server (tệp từng đồng bộ rồi bị xóa trên máy). App không lan truyền thao tác xóa.
- **Claim job** (`Db::claim_next_job`) là một câu `UPDATE … RETURNING` nguyên tử: chọn job `pending` hoặc `retry_wait` đã tới hạn theo FIFO `id`, lọc theo loại (`upload`/`download`) và kích thước tối đa (slot tệp nhỏ), rồi chuyển sang `running` trong cùng câu lệnh — hai task hay hai kết nối không thể claim cùng một job. Job của tệp đang có **bất kỳ** job nào `running` (upload hay download) bị bỏ qua: một `file_id` có tối đa một transfer tại một thời điểm. Index `idx_active_job` vẫn chỉ chặn trùng theo `(file_id, operation)`.
- **Worker ghi kết quả bằng compare-and-set** (`Db::transition_running_job`): chỉ ghi khi job vẫn `running`. Job đã bị chuyển đi (ví dụ `conflict` do `cancel_active_uploads`/`mark_file_conflict`, hoặc `pending` do khôi phục) thì kết quả của worker bị bỏ, không ghi đè.
- **`sync_job.rerun_requested`** (`INTEGER NOT NULL DEFAULT 0`, thêm bằng `ensure_column`): enqueue gặp job cùng tệp + thao tác đang `running` (version remote mới trong lúc download, hoặc tệp đổi trong lúc upload) không sửa target của job đang chạy mà đặt cờ này. Khi job rời `running` với `completed`/`failed`/`retry_wait`, nó quay lại `pending` ngay (attempt 0) để chạy lượt mới — version mới không phải chờ reconcile. Base của lượt vừa xong vẫn là hash của đúng byte nó đã truyền. Xung đột/khôi phục xóa cờ.
- `Db::claim_next_job` bỏ qua job của thư mục có `access_state = 'denied'`: job giữ nguyên `pending`/`retry_wait` (tạm dừng, không xóa, không `failed`) và tự chạy lại khi thư mục về `ok`. Job đang chạy mà nhận 403/404 thì app đối chiếu lại `GET /folders` ngay; nếu thư mục đã mất quyền, job trở về `pending` với thông báo “Mất quyền truy cập — đồng bộ đã tạm dừng.”. 401 vẫn là chuyện phiên/thiết bị, không đánh dấu thư mục.
- Job active trùng cho cùng file+thao tác bị từ chối. Lần enqueue sau dùng lại dòng `failed` (đặt lại thành `pending`) nên **Lỗi** giảm khi file đó được xếp hàng hoặc hoàn tất. Dashboard đếm các file có job mới nhất vẫn `failed`, không phải tổng từ trước tới nay. Khởi động xóa các dòng failed đã bị thay bởi job pending/completed mới hơn.
- Change cursor theo từng thư mục là `app_meta.change_cursor:{remote_folder_id}`. Nó chỉ tiến sau khi một thay đổi đã được áp dụng bền vững (job đã enqueue, xung đột đã đánh dấu, hoặc base đã tiến). At-least-once; xử lý là idempotent.
- Đổi tài khoản xóa thư mục/file/job **và** change cursor. `client_uid` được giữ.
- **Ghi dựa trên binding folder** (`Db::with_current_binding` / `Db::with_bound_file`): quét cục bộ, poll change feed và hydrate đều đọc danh sách folder trước rồi mới chờ hash tệp hoặc HTTP (nhiều giây), nên thư mục có thể bị gỡ — hoặc gỡ rồi gắn thư mục khác trùng rowid — trước lúc ghi. Mọi ghi như vậy (`record_local_change`, `ensure_remote_mapping_bound`, xếp hàng download / tiến base / đánh dấu xung đột trong `plan_remote_change`, và "Giữ bản server" — `accept_server_version`, đọc tệp cùng binding bằng một truy vấn rồi xóa cờ + xếp hàng download, còn kiểm tệp vẫn đúng đường dẫn + tệp remote đã đọc) chạy trong MỘT transaction dưới cùng mutex với `delete_folder`, chỉ khi folder còn khớp **`id` + `local_path` + `remote_id`** đã đọc; ghi theo `file_id` còn kiểm tệp vẫn thuộc folder đó. Binding đã đổi thì thao tác bị bỏ qua và log (`folder unbound during scan; local change skipped` / `folder unbound during remote change; mapping skipped`): không `FOREIGN KEY constraint failed` (trước đây làm hủy cả lượt đối soát), không tạo lại folder, không gán tệp của binding cũ cho binding mới.
- **Transfer đang chạy chỉ ghi vào đúng dòng nó đã claim.** Job/tệp/folder bị cascade xóa khi gỡ thư mục và SQLite tái dùng rowid khi gắn lại, nên `job_id`/`file_id`/`folder_id` trơn không đủ. Ngay sau khi claim, `process_transfer` chụp `RunningJob` MỘT lần (`Db::running_job`: job `running` cùng id/tệp/folder/loại + tệp đúng đường dẫn, và đúng tệp remote với download + binding `id`/`local_path`/`remote_id`). Task không đọc lại folder/tệp theo id: tệp đích của download và tệp nguồn của upload tính từ binding đã chụp. Mọi lượt ghi bền sau một lần await — chốt lỗi (`record_job_failure`, kể cả bỏ session khi 409), tạm dừng/mất quyền (`settle_stopped_job`), hết phiên, lưu session/ETag/tiến độ, dấu vân tay sau khi hash lại, hash của job, hoàn tất (thường, dedup, object reuse), finalize `conflict`, tiến base/`suppress_hash` của download — đi qua `Db::with_running_job` / `Db::transition_owned_job`: kiểm lại danh tính trong CÙNG transaction với lượt ghi, dưới cùng mutex với `delete_folder`. Upload còn kiểm quyền sở hữu ngay trước `prepare` và `finalize`. Lượt thay tệp đích của download (`atomic_replace`) chạy **bên trong** transaction đó, sau khi tệp tạm đã kiểm và fsync ngoài mutex. Mất quyền sở hữu thì task dừng với `AppError::Superseded` (download: `DownloadReport.superseded`), không ghi gì và log `running job superseded` / `download superseded`; job/tệp của binding mới giữ nguyên status, attempt, lỗi, session và dấu vân tay. Job bị `mark_file_conflict` chuyển khỏi `running` giữa chừng cũng làm task dừng. Giới hạn: nếu mọi thành phần danh tính đều trùng (rowid folder + `local_path` + `remote_id` + rowid tệp + đường dẫn + tệp remote + rowid job + loại, và job mới đang `running`), hai lượt chạy không phân biệt được nếu không thêm token cho mỗi lần claim; hai lượt khi đó nhắm cùng một tệp logic.
- **`sync_job.part_size`** (`INTEGER`, thêm bằng `ensure_column`): part size của session multipart đang dở, lưu cùng `session_id`/`uploaded_parts`/`content_hash` và xóa cùng chúng. Resume dùng đúng giá trị này; job lưu trước khi có cột (NULL) resume với `LEGACY_PART_SIZE` = 16 MiB (part size của server lúc đó). Download luôn NULL.
- Lỗi tạm thời dùng exponential backoff có jitter; lỗi kết nối thử lại vô hạn, lỗi server/storage dừng ở lần thứ 20 (xem [contract](contract.md#concurrent-transfers)); retry thủ công đặt lại `attempt_count` và `last_error`; Odoo HTTP 401 (kiểu `Unauthenticated` / `401 Unauthorized`) và sai lệch validation/integrity không retry. **Đừng** coi các chữ số `401` trong object key MinIO là hết hạn session. Lỗi thay thế file đang mở thì retry.

Watcher (`notify`) là đường nhanh. Reconciliation filesystem luôn chạy (mặc định 10 phút). Polling thay đổi remote mặc định 15 giây (`change_poll_secs`, clamp 10–120). Liệt kê file theo thư mục định kỳ là lưới an toàn để bắt kịp nếu sự kiện lịch sử bị mất. Dòng change-feed được giữ lại (không prune trong Phase 3).
