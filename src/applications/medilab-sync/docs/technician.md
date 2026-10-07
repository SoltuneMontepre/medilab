# MediLab File Sync — technician guide

Hướng dẫn ngắn cho pilot có kiểm soát tại PTN (phòng thử nghiệm). Hỏi quản trị viên địa chỉ server và tài khoản của bạn. Không chia sẻ mật khẩu.

## Install

Package pilot cho Linux: **DEB** hoặc **RPM** (cùng phiên bản với PTN của bạn). Không hỗ trợ AppImage. Windows chưa được kiểm chứng cho pilot này.

Cài package quản trị viên cung cấp, rồi mở **MediLab File Sync**. Icon tray (bình thí nghiệm màu xanh mòng két trên ô vuông tối) sẽ xuất hiện. Trên Windows, nếu bị ẩn thì tìm trong mũi tên overflow. Nếu chỉ thấy glyph hamburger/menu, tray không có icon app — cài lại hoặc khởi động lại app.

## Login

1. Ô địa chỉ Odoo được điền sẵn: bản release dùng URL production, bản dev dùng `http://localhost:8069`. Đổi nếu cần (production phải là HTTPS). Mỗi địa chỉ đăng nhập thành công được nhớ lại; bấm ô nhập hoặc mũi tên ▾ để chọn nhanh từ danh sách đã dùng.
2. Nhập username và mật khẩu MediLab.
3. App lưu key thiết bị trong kho credential của OS. Bạn sẽ không thấy key đó.

Nếu app báo **“Kho lưu trữ đăng nhập trên máy đang bị khóa”**: phiên của bạn chưa hết hạn. Hệ điều hành đang khóa kho mật khẩu (thường sau khi khóa màn hình hoặc đăng nhập tự động). Mở khóa kho mật khẩu — nhập mật khẩu máy khi hộp thoại của hệ điều hành hiện lên — rồi bấm **Thử lại**. Khi app đang chạy, việc kho mật khẩu bị khóa không làm gián đoạn đồng bộ.

Nếu đăng nhập lỗi: có thể bạn thiếu group Sync App, hoặc thiết bị đã bị thu hồi. Liên hệ quản trị viên. Không dùng lại login của người khác.

## Bind a folder

1. Trong Odoo hoặc hỏi người phụ trách, xác nhận bạn được dùng thư mục mẫu nào (thường là **Kết quả / RESULT**, đôi khi **Dữ liệu thô / RAW**).
2. Trong app, chọn một **thư mục local** trên PC này (bộ chọn, dán đường dẫn, hoặc kéo thư mục từ trình quản lý file vào tab thư mục) và gắn nó với thư mục remote đó.
3. Để RAW và RESULT ở các thư mục local **riêng**. Không trộn lẫn.

Tên thư mục trên máy chủ tự điền theo tên thư mục bạn chọn; đổi được nếu cần. Mặc định app đồng bộ **mọi tệp** trong thư mục, kể cả thư mục con (công tắc **Gồm cả các thư mục con**, đang Bật). Chỉ bật **Chỉ đồng bộ một số tệp (tuỳ chọn)** khi bạn thật sự muốn giới hạn theo tên bắt đầu bằng, mẫu tên (dấu `*`), hoặc đuôi tệp; để trống điều kiện thì vẫn đồng bộ mọi tệp.

App theo dõi thư mục local. Lưu một file (khớp điều kiện lọc, nếu có) sẽ xếp hàng một upload.

## Status meanings

| Tình trạng | Ý nghĩa |
| --- | --- |
| Pending / queued | Đang chờ upload hoặc download |
| Running | Đang truyền |
| Completed | Server đã nhận phiên bản này (hoặc download đã được kiểm) |
| Conflict | Server đã có phiên bản khác. Cả hai bản được giữ. Đừng xóa file để “sửa” nó. |
| Error / retry | Lỗi mạng hoặc server tạm thời. Cứ để app chạy. |
| Paused | Bạn hoặc app đã tạm dừng worker (kể cả sau khi login hết hạn) |
| Tạm dừng — mất quyền | Quyền mẫu hoặc tư cách thành viên thư mục của bạn đã bị gỡ. File đang chờ của thư mục đó tạm dừng (không phải lỗi), file local vẫn nằm trên đĩa. Thư mục hiện dòng “Mất quyền truy cập — đồng bộ đã tạm dừng.” |

Tạm dừng/tiếp tục nằm trong cửa sổ app. Tạm dừng không xóa hàng đợi.

## Conflicts

Xung đột nghĩa là hai người (hoặc PC này và việc sửa Office) đã sửa cùng một file từ các base khác nhau. App sẽ không ghi đè ngầm. Ở **Trạng thái**, dùng **Giữ nguyên file cục bộ** (giữ bản trên PC, ẩn badge xung đột) hoặc **Dùng phiên bản máy chủ** (backup bản local, rồi download bản trên server). **Lịch sử phiên bản** có thể khôi phục phiên bản cũ hơn. Quản trị viên vẫn thấy cả hai phiên bản trong Odoo.

## When access expires

Nếu quyền mẫu hoặc tư cách thành viên thư mục của bạn bị gỡ, app nhận ra trong một chu kỳ hỏi thay đổi máy chủ (mặc định 15 giây): thư mục vẫn nằm trong danh sách, các file đang chờ của thư mục đó **tạm dừng** chứ không bị xóa hay báo lỗi, và không file nào trên PC bị xóa. Khi quyền được cấp lại, thư mục tự trở lại bình thường và các file đang chờ tự đồng bộ tiếp — không cần gắn lại. Đừng copy file từ tài khoản user khác trên cùng PC.

## Stopping sync on this computer

**Ngừng đồng bộ** = bỏ thư mục này khỏi **máy này**. Nó **không** tắt hay xóa thư mục trên máy chủ, **không** gỡ tư cách thành viên của bạn hay của ai khác, **không** ảnh hưởng người khác đang đồng bộ, và **không** xóa file trên máy. Sau đó thư mục hiện lại ở **Được chia sẻ với bạn** (nếu bạn là thành viên) hoặc **Thư mục của bạn chưa đồng bộ trên máy này** (nếu bạn là chủ sở hữu); bấm **Chọn thư mục trên máy** để đồng bộ lại, kể cả vào một thư mục khác.

Khác với **mất quyền**: khi bị gỡ quyền, thư mục vẫn nằm trong danh sách với dòng “Mất quyền truy cập — đồng bộ đã tạm dừng.” và các file đang chờ được giữ lại.

Tắt một thư mục cho tất cả mọi người là thao tác của quản trị đồng bộ trong Odoo, không có trong app desktop. Khi thư mục bị tạm tắt, file mới hiện “Thư mục đang bị quản trị viên tạm tắt trên máy chủ…” và tự tải lên khi quản trị bật lại; bạn không tự bật lại được.

## Sharing a folder

- **Thư mục → Quản lý quyền truy cập** cho thấy chủ sở hữu và tư cách của bạn. Chủ sở hữu (hoặc quản trị đồng bộ) thấy đủ danh sách thành viên, tìm người theo tên/tên đăng nhập để **Thêm thành viên**, và **Gỡ quyền**. Thành viên thường chỉ xem, không tự rời thư mục được — chỉ “Ngừng đồng bộ” trên máy mình.
- Thành viên được **đọc và ghi** (xem, tải xuống, tải lên, khôi phục phiên bản). Không có vai trò chỉ đọc.
- Thư mục gắn với mẫu: thêm thành viên **không** cấp quyền xem mẫu trong LIMS. Người chưa thấy mẫu hiện “Chưa có quyền truy cập mẫu trong LIMS.” và chưa dùng được thư mục cho tới khi được cấp quyền mẫu.
- Thư mục người khác chia sẻ cho bạn hiện ở **Được chia sẻ với bạn**. Bấm **Chọn thư mục trên máy** để đồng bộ về một thư mục tùy chọn trên PC của bạn; không cần gõ tên thư mục. Gỡ quyền không xóa file trên máy của người bị gỡ.

## RAW files

RAW là output của thiết bị đo. **Đừng** sửa RAW trong ONLYOFFICE. Đừng thay RAW bằng file “đã làm sạch” cùng tên nếu người phụ trách cấm. Nếu lưu một file RAW mới, phiên bản trước trên server vẫn nằm trong lịch sử.

## Office editing

Với file **kết quả** Word/Excel/PowerPoint, quản trị viên có thể mở chế độ cùng sửa trong trình duyệt (ONLYOFFICE). Chờ editor lưu xong rồi mới mong bản trên desktop cập nhật. Nếu tránh được, đừng mở cùng file đó trong Word/LibreOffice trên desktop khi đang sửa Office — việc đó gây xung đột hoặc lỗi khóa.

## Who to contact

- Không đăng nhập được, mất tray, không gắn được thư mục: IT của PTN / quản trị viên MediLab
- Sai mẫu hoặc thiếu thư mục RESULT: người phụ trách (mapping LIMS — Laboratory Information Management System)
- Xung đột hoặc phê duyệt/ký duyệt: người phụ trách; họ dùng Odoo, không dùng app này, để phê duyệt

## Editing online

Khi bấm **Chỉnh sửa trực tuyến**, app hiện vòng xoay và bước đang làm: **Bước 1/2** kết nối máy chủ chỉnh sửa trực tuyến (ONLYOFFICE), **Bước 2/2** mở tài liệu. ONLYOFFICE không báo phần trăm nên app không hiện thanh phần trăm. Nếu máy chủ chỉnh sửa đang tắt, app báo lỗi ngay; nếu trình soạn thảo không phản hồi sau 1 phút, app báo lỗi kèm nút **Thử lại**. Đồng bộ tệp không phụ thuộc ONLYOFFICE và vẫn chạy bình thường.
