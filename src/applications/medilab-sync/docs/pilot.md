# Laboratory File Sync — controlled pilot checklist

Dùng một bản cho mỗi máy trạm. Không ghi mật khẩu hay API key lên tờ này.

OS pilot: **Linux DEB hoặc RPM**. Windows = chưa kiểm chứng. AppImage = không hỗ trợ. Kiểm chứng trên hai PC thật là điều kiện tiên quyết riêng trước khi triển khai rộng ra nhiều máy trạm.

## Workstation

| Hạng mục kiểm | Xong |
| --- | --- |
| Đã chỉ định thử nghiệm viên và tạo `res.users` MediLab | ☐ |
| Đã gán nhóm quyền **Sync App / User** | ☐ |
| Đã cấp quyền mẫu (`danh.sach.mau`) cho yêu cầu pilot | ☐ |
| Đã tạo thư mục RAW/RESULT trên mẫu | ☐ |
| Desktop đã cài (DEB hoặc RPM) và khởi động được | ☐ |
| Có kho credential của OS (Secret Service). Không có `MEDILAB_SYNC_ALLOW_INSECURE_FILE_KEYRING` trên production | ☐ |
| Thiết bị đã đăng ký sau lần đăng nhập đầu (`sync.device`) | ☐ |
| Thư mục local đã map đúng thư mục remote (RESULT hay RAW) | ☐ |
| Đủ dung lượng đĩa cho bộ file làm việc + file download tạm | ☐ |
| Mạng: truy cập được URL Odoo và endpoint **public** của MinIO | ☐ |
| Icon tray chạy sau khi đăng nhập | ☐ |
| Upload thử đã hoàn tất (phiên bản mới trong Odoo) | ☐ |
| Đã kiểm download/bắt kịp thử nếu dùng hai chiều | ☐ |
| Thử nghiệm viên đã đọc [hướng dẫn cho thử nghiệm viên](technician.md) | ☐ |

## Site (once)

| Hạng mục kiểm | Xong |
| --- | --- |
| Đã diễn tập quy trình backup PostgreSQL | ☐ |
| Đã diễn tập backup/copy bucket MinIO | ☐ |
| Secret Doppler/production không bị commit vào git | ☐ |
| Đã lên kế hoạch topology HTTPS (desktop→Odoo, desktop→MinIO, trình duyệt→ONLYOFFICE, ONLYOFFICE→Odoo) | ☐ |
| Đã hiểu đường ONLYOFFICE là tùy chọn (sync vẫn chạy nếu nó down) | ☐ |
| Đã diễn tập thu hồi thiết bị + đăng nhập lại | ☐ |
