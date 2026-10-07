# Laboratory File Sync — maintenance

## Local dev

```bash
task upgrade                 # install/update medilab_sync (includes office session model)
task sync-app:onlyoffice-up  # optional: starts ONLYOFFICE (own compose file, opt-in — not part of `task up`)
task onlyoffice-health       # optional Document Server check
task sync-app:dev            # or: task sync-app:run (Linux Hyprland env is in the taskfile)
```

Desktop mong đợi Odoo ở `http://localhost:8069`, MinIO ở `http://localhost:29000`, và ONLYOFFICE ở `http://localhost:28880`.

`task sync-app:dev` chạy `bun install` rồi `bun run tauri:dev`. Chỉ trên Linux/Hyprland: nó đặt `WEBKIT_DISABLE_COMPOSITING_MODE=1`, `GDK_BACKEND=x11`, `GTK_USE_PORTAL=1`, và `MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING=true`. Khởi động lại task sau khi pull thay đổi đó; hot-reload không nhận env mới. Bộ chọn thư mục dùng `zenity`/`kdialog` trên Linux; Windows và macOS dùng hộp thoại chọn thư mục native của Tauri. Tab thư mục cũng nhận kéo-thả native **một thư mục** từ trình quản lý file (Rust kiểm path; file bị từ chối). Loại rule dùng list trong webview, không dùng `<select>` native (popup combo WebKitGTK/GTK bị lệch vị trí trên Hyprland). Windows lưu API key trong Credential Manager. Tray dùng icon cửa sổ của bundle (`TrayIconBuilder::icon`); bỏ nó thì ô tray Windows 11 trống hoặc hiện placeholder hamburger trên Linux. Build production không được đặt env insecure-file. Windows cần MSVC toolchain trên PATH (`vcvars64`) để build Rust.

Gán cho user **Sync App / User** (`medilab_sync.group_sync_user`) trước khi đăng nhập. User kiểm thử thật: `sync_user_a` / `sync_user_b` (Sync App / User) và `plain_user` (chỉ Internal User). Fixture tự động `--test-tags=/medilab_sync` dùng `medilab_sync_test_a` / `medilab_sync_test_b` / `medilab_sync_test_plain` để không đụng các user thật đó trên database development dùng chung.

### Transfer tests

`cargo test` chạy test multipart song song trên server giả (`upload_tests.rs`, phần Stage B: cửa sổ 3 hoàn tất lệch thứ tự, file đổi giữa các part, 403 của một part trong lúc part khác đang bay, Pause/restart khi nhiều part đang bay, ngân sách chung qua nhiều file, part vượt ngân sách lỗi ngay), và test integrity upload trên server giả (`src-tauri/src/sync/upload_tests.rs`, server ở `test_server.rs`): file đổi trước/giữa/sau khi đọc part, dedup, URL presigned bị từ chối, Pause/Resume và restart giữa upload.

`cargo test` cũng chạy test dispatcher (`src-tauri/src/sync/dispatcher_tests.rs`): claim nguyên tử qua hai kết nối, loại trừ upload/download cùng tệp, giới hạn slot, không chặn đầu hàng, version mới trong lúc download, compare-and-set, và Pause/restart/mất quyền khi nhiều upload đang chạy.

Live test với Odoo + MinIO thật (`src-tauri/src/sync/live_tests.rs`) bị `#[ignore]`; cần `task up` và một user có quyền tạo folder sync. Mỗi lần chạy tạo folder `e2e-<uuid>` mới trên server dev.

```bash
cd applications/laboratory-file-sync-application
export MEDILAB_E2E_URL=http://localhost:8069 MEDILAB_E2E_LOGIN=admin MEDILAB_E2E_PASSWORD=admin
cargo test --manifest-path src-tauri/Cargo.toml live_ -- --ignored --test-threads=1 --skip live_proxy --skip live_benchmark --skip live_multipart
# Nhiều transfer song song (overlap, download không chờ upload lớn, Pause, restart, mất quyền):
cargo test --manifest-path src-tauri/Cargo.toml live_concurrent_transfers -- --ignored --nocapture
# Benchmark BEFORE (1 worker FIFO) vs AFTER (dispatcher mặc định); chạy release để hash không bị debug làm chậm:
cargo test --release --manifest-path src-tauri/Cargo.toml live_benchmark_transfers -- --ignored --nocapture
# Multipart song song (release): benchmark 256 MiB qua proxy giới hạn theo kết nối + Pause/restart khi nhiều part đang bay,
# rồi benchmark loopback. Proxy đặt HTTP_PROXY nên test đầu phải chạy riêng tiến trình (--exact):
cargo test --release --manifest-path src-tauri/Cargo.toml -- --ignored --exact sync::live_tests::live_multipart_proxy_benchmark_and_failures --nocapture
cargo test --release --manifest-path src-tauri/Cargo.toml -- --ignored --exact sync::live_tests::live_multipart_loopback_benchmark --nocapture
# Pause/Resume multipart và kill TIẾN TRÌNH giữa multipart rồi restart từ SQLite (~1 phút, chạy riêng tiến trình):
task sync-app:e2e-multipart
# Proxy đặt HTTP_PROXY cho client dùng chung của cả tiến trình nên chạy riêng (~3 phút, upload bị giới hạn 96 KiB/s):
cargo test --manifest-path src-tauri/Cargo.toml -- --ignored --exact sync::live_tests::live_proxy_connection_reuse_and_slow_upload
```

`task sync-app:e2e-multipart` (`live_multipart_pause_resume_and_process_kill`) thay cho kiểm thử GUI của multipart. Mọi request đi qua proxy giới hạn 4 MiB/s mỗi kết nối, ghi lại từng PUT part và đường dẫn request:

- Pause (cờ pause + `StopProbe` như app) khi ≥ 2 PUT đang bay, rồi Resume: cùng `upload_session_id`, không `prepare` mới, chỉ PUT đúng các part chưa lưu ETag (mỗi part một lần), finalize đúng session cũ, SHA-256 của object trên MinIO khớp.
- Một tiến trình con (`live_multipart_kill_worker`, cùng binary test) claim job và upload qua proxy; khi ≥ 1 part đã lưu ETag và ≥ 2 PUT đang bay thì bị SIGKILL. Tiến trình cha mở lại SQLite hiện tại, `recover_jobs`, resume cùng session, không PUT lại part đã lưu, SHA-256 khớp.

Chỉ còn một kiểm tra GUI thủ công (nối nút, không phải multipart): khi **Đang tải lên** > 0, nút **Tạm dừng** trên `AppHeader` vẫn bấm được; bấm thì tạm dừng và nhãn đổi sang **Tiếp tục**; bấm **Tiếp tục** thành công kể cả khi lượt đối soát nền đang chạy.

### Hidden transfer settings

`upload_concurrency`, `download_concurrency` và `part_concurrency` nằm trong JSON settings (`app_meta.settings` của `sync.sqlite`), không có trên form Settings. Mặc định 3; giá trị ngoài `1..=4` bị kẹp lúc dùng; đổi xong phải khởi động lại app. JSON cũ không có các field này nhận mặc định. Form và các đường lưu khác (đổi ngôn ngữ, đăng nhập) gửi lại nguyên object nên không làm mất giá trị đã chỉnh.

`part_concurrency` là số PUT part của **một** tệp cùng bay. Mọi upload chung một ngân sách buffer 128 MiB (`DEFAULT_PART_BUDGET_MIB`, part 16 MiB ⇒ tối đa 8 part đang đọc/PUT trong cả app); 3 upload × 3 part × 16 MiB = 144 MiB nên khi mọi slot upload đều chạy tệp lớn, ngân sách — không phải cửa sổ — là giới hạn, và part chờ ngân sách thay vì cấp phát thêm. Log `transfer dispatcher started` ghi `part_concurrency` và `part_budget_mib`; `upload job finished` ghi `part_budget_peak_mib`. Job lỗi “Kích thước part … vượt ngân sách bộ nhớ upload …” nghĩa là server cấp part lớn hơn toàn bộ ngân sách (lỗi cấu hình server, không tự hết).

Default `part_concurrency = 3` được chọn theo benchmark 27-09-2026 (release, tệp 256 MiB, MinIO dev): qua proxy giới hạn 4 MiB/s **mỗi kết nối** (mô phỏng đường truyền có độ trễ × băng thông lớn) 64,9 s ở mức 1 và 24,5 s ở mức 3 (2,65×); loopback không giới hạn 1,08 s ở mức 1 và 0,67–0,69 s ở mức 3; ngân sách cao nhất 16 MiB và 48 MiB. Đặt `part_concurrency = 1` nếu đường truyền bị giới hạn tổng (không theo kết nối) và cần giảm tải cho MinIO. Chạy lại benchmark: `live_multipart_proxy_benchmark_and_failures` và `live_multipart_loopback_benchmark` (xem Transfer tests).

Job `failed` với “Đã thử 20 lần: …” là lỗi server/storage lặp lại (5xx, URL presigned bị từ chối, tệp đổi liên tục trong lúc upload), không phải mất mạng; kiểm log `sync job failed` với `error_category = "server"` trước khi bấm Thử lại. Mất mạng hiện `retry_wait` và tự chạy lại khi có mạng.

## Build

```bash
task sync-app:build
```

hoặc trong app:

```bash
cd applications/laboratory-file-sync-application
cargo fmt --check --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml
bun run build
```

Chạy local tương đương CI:

```bash
task sync-app:ci
```

## Linux pilot packages

Pilot có kiểm soát tại PTN (phòng thử nghiệm) trên Linux dùng **DEB và RPM**, không dùng AppImage.

```bash
task sync-app:package-linux
```

Lệnh đó chạy `bun run tauri build --bundles deb,rpm` với `CARGO_TARGET_DIR` nằm trong app và `TMPDIR=.tmp-cargo` để việc đóng gói không làm đầy `/tmp`.

**AppImage không được hỗ trợ / hoãn lại.** `linuxdeploy` đã lỗi trong repo này; PTN có kiểm soát không cần AppImage. Đừng coi thiếu AppImage là blocker của release.

Installer Windows do CD tạo ra nhưng **việc kiểm chứng trên Windows đang PENDING** cho tới khi một máy Windows smoke-test WebView2, Credential Manager, tray, autostart và gỡ cài đặt.

## CI/CD

Pull request đụng tới `applications/laboratory-file-sync-application/` chạy
[ci.sync-app.yml](../../../.github/workflows/ci.sync-app.yml): một job Linux với
`cargo fmt`/`clippy`/`test` và `bun run build`. `tauri build` đầy đủ chỉ chạy qua workflow
dispatch thủ công hoặc release của [cd.sync-app.yml](../../../.github/workflows/cd.sync-app.yml).

Release dùng [cd.sync-app.yml](../../../.github/workflows/cd.sync-app.yml). Workflow suy ra
URL Odoo/API production cho desktop từ
[`infra/clusters/environments/lims/apps/medilab/ingress.yaml`](../../../infra/clusters/environments/lims/apps/medilab/ingress.yaml)
và inject thành `MEDILAB_SYNC_ODOO_URL` cho build Tauri/Rust. Workflow production lỗi
trước khi đóng gói nếu không đọc được host của ingress, host resolve về localhost, hoặc không tạo ra
URL `https://`. Development local tiếp tục dùng mặc định localhost.

Server production vẫn cần URL dịch vụ public, nhưng chúng không phải input của build desktop:

| Biến server | Mục đích |
| --- | --- |
| `PUBLIC_ENDPOINT` | Endpoint MinIO/S3 public mà Odoo dùng khi trả presigned URL cho desktop |
| `ONLYOFFICE_PUBLIC_URL` | URL public của ONLYOFFICE Document Server trả về trong office session |

Secret của server chỉ được nằm phía server: `ONLYOFFICE_JWT_SECRET`, access key MinIO, secret key
MinIO, credential database, mật khẩu Odoo và API key thiết bị không bao giờ được nhúng vào build
desktop. Credential ký/notarization, khi có, nên là secret của GitHub Environment.

Tình trạng runtime production hiện tại:

- Endpoint Odoo: `https://lims.soltunemontepre.tech` lấy từ ingress đang được track.
- Endpoint truyền trực tiếp MinIO: `https://bucket.soltunemontepre.tech`, được overlay GitOps production
  route tới port service S3 API của MinIO.
- Hạ tầng ONLYOFFICE production: chưa có trong GitOps. Chỉnh sửa Office đang chờ, nhưng
  khởi động Odoo và sync file lõi không cần nó.

Release matrix tạo package native trên runner do GitHub host:

| Nền tảng | Runner | Bundle |
| --- | --- | --- |
| Windows x64 | `windows-latest` | NSIS `.exe`, MSI `.msi` |
| Linux x64 | `ubuntu-latest` | DEB, RPM |
| macOS arm64 | `macos-latest` | archive `.app`, `.dmg` |

Bản phân phối chính trên Windows là NSIS `.exe`; MSI là package phụ cho IT/admin. AppImage bị
hoãn/không hỗ trợ. Installer macOS và Windows vẫn chưa ký cho tới khi cấu hình credential ký thật;
đừng tuyên bố phân phối production đã notarize hoặc code-sign trước lúc đó.

Build có ký (tag `filesync-v*`, hoặc dispatch với `test_channel`) truyền thêm
`--config src-tauri/tauri.updater.conf.json` để bật `bundle.createUpdaterArtifacts: "v1Compatible"`,
sinh `*.nsis.zip` + `*.nsis.zip.sig` cho updater. Cờ này không nằm trong `tauri.conf.json` vì khi có
`plugins.updater.pubkey` mà thiếu private key thì `tauri build` fail, làm gãy mọi build không ký.
Linux package chạy trên runner GitHub, không qua Blacksmith: cache của GitHub scope theo tag ref nên
release nào cũng cold build (~18 phút), vượt trần timeout của Blacksmith.

Các bước release:

1. Tăng `version` trong `src-tauri/tauri.conf.json` và `package.json` cùng lúc.
2. Push tag `filesync-v<version>` (ví dụ `filesync-v0.1.0`) hoặc tag RC như
   `filesync-v0.1.0-rc.1`. Tag chứa `-rc.` publish một GitHub prerelease.
3. Với build pilot thủ công, chạy workflow từ GitHub Actions; nó suy ra URL Odoo/API production cho
   desktop từ ingress đang được track và từ chối output localhost hoặc không phải HTTPS.
4. Mở GitHub Release, kiểm installer, rồi publish nếu phù hợp.

Installer chưa ký ở Phase 1. Code signing macOS/Windows có thể thêm sau qua secret
`APPLE_*` / secret ký Windows trên workflow release.

Kiểm chứng installer Windows không nằm trong đợt hiện thực trên Linux này. Cùng binary Tauri đó dự kiến dùng cho Windows (Credential Manager + hộp thoại chọn thư mục native + autostart). Bắt buộc có WebView2. Đường này chưa được test thật.

## Phase 3 limitations

- **Đổi tên** và **xóa** phía remote không được lan truyền. Không có tombstone trong phase này.
- Entry change-feed được giữ lại; chưa có fallback prune `CURSOR_TOO_OLD`.
- Chưa hiện thực invalidation qua WebSocket. Polling + reconciliation là đường đảm bảo nhất quán.
- Chưa hiện thực merge nội dung Office / CRDT / OT. ONLYOFFICE là editor.
- SHA-256 của upload phía server vẫn là ranh giới tin cậy (chỉ HEAD size). Desktop **có** kiểm SHA-256 khi download. Ingest Office **có** hash byte callback được stream.
- Kiểm chứng trên hai PC thật, test thật installer Windows và TLS production vẫn hoãn lại.

## Phase 2 limitations (historical; superseded for restore propagation)

- Lịch sử phiên bản được lấy từ Odoo khi cần. SQLite không phải bản mirror lịch sử.
- Khôi phục vẫn tạo phiên bản RESTORE **mới**; không bao giờ ghi `current_version_id` đè về một dòng cũ.

## Phase 1 limitations

- Đổi tên/xóa local không được lan truyền; đổi tên là một logical path mới nếu tên mới vẫn khớp rule.
- Đăng xuất giữ các liên kết thư mục local của cùng user. Đăng nhập bằng user **khác** sẽ xóa các dòng thư mục/job/file local và cursor remote để User B không thừa hưởng mapping của User A. `client_uid` được giữ làm định danh máy trạm.
- Object multipart mồ côi còn lại sau crash được cron server dọn, không phải desktop dọn ngay.
- Watcher bỏ qua enqueue khi SHA-256 local khớp một dòng **đã sync** hoặc `suppress_hash` của download. Dòng chưa sync/pending có cùng hash được xếp hàng lại.
- Nếu upload session trả HTTP 409 (hết hạn hoặc không active), desktop bỏ session đó và retry bằng một lần prepare mới. Upload mất quyền sở hữu job giữa chừng (thư mục bị gỡ/gắn lại, xem [database](database.md)) không finalize và không gọi abort: API không có abort cho desktop, session dở và part đã PUT trên MinIO được cron `Sync: dọn phiên tải lên hết hạn` (30 phút) abort sau `expires_at`. Nếu finalize đã tới server trước khi task phát hiện, version đó vẫn là version chuẩn trên server; chỉ SQLite cục bộ không ghi nhận. Bản thân finalize là idempotent sau khi thành công, nên crash giữa finalize và `completed` của SQLite phục hồi được mà không tạo phiên bản canonical thứ hai khi hash không đổi.
