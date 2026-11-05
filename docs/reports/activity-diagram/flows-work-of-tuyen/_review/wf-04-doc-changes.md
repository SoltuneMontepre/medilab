# WF-04 Result entry and approval: thay đổi cần đưa vào tài liệu

Những điểm sơ đồ `[Flow] WF-04 Result entry and approval.drawio` đã được chấp nhận khác với `## WF-04 Result entry and approval` trong `docs/functional/business-flows.md`. Mỗi mục ghi sơ đồ giờ thể hiện gì, phần nào của tài liệu bị ảnh hưởng và câu chữ mới.

## Lưu tệp kết quả nằm trên luồng chính

- **Sơ đồ thể hiện:** sau "Follow the method and measure in the booking", tester quyết định "Testing produces files?". Nhánh yes đi qua "Save result file" và System "Sync file version" rồi tới "Enter result with snapshot unit and LOD/LOQ"; nhánh no đi thẳng tới bước nhập kết quả.
- **Phần tài liệu liên quan:** Main path ("When testing produces files, the tester saves them in the sample's folder; Medilab Sync uploads new versions and the head signs the result-file version with its hash.") và mermaid, nơi `t1 -.->|testing produces files| f1` là nhánh phụ và `t1 --> t2` đi thẳng tới bước ghi kết quả.
- **Câu chữ mới:**
  - Main path: "The tester follows the agreed method. When testing produces files, the tester saves them in the sample's folder before recording the result; Medilab Sync uploads new versions and the head signs the result-file version with its hash."
  - Mermaid: thay `t1 --> t2` và `t1 -.->|testing produces files| f1` bằng `t1 --> files{Testing produces files?}`, `files -->|yes| f1` và `files -->|no| t2`; thêm `version --> t2`.

## Bản tải lên bị xung đột quay lại bước lưu tệp

- **Sơ đồ thể hiện:** sau "Sync file version", System quyết định "Based on current file version?". Nhánh yes thành "New current version" rồi tới bước nhập kết quả; nhánh no tới bước Tester "Keep both conflict versions and take the server version with a local backup", rồi quay lại "Save result file". Trang Demo scenarios minh hoạ đường này ở "DS-04e Same file changed on two computers ↔ WF-04-E4", kết thúc bằng "Save changes again" và ◉ "Both versions kept; changes saved again".
- **Phần tài liệu liên quan:** WF-04-E4 ("the second upload is kept as a conflict, and the tester takes the server's version with a backup of their own") và mermaid, nơi `current -->|no| f2` dừng ở `f2`.
- **Câu chữ mới:**
  - WF-04-E4: "Two testers change the same file from one version; the second upload is kept as a conflict, and the tester takes the server's version with a backup of their own and saves their changes again."
  - Mermaid: thêm `f2 --> f1`.

## Tester nhập kết quả

- **Sơ đồ thể hiện:** bước của tester là "Enter result with snapshot unit and LOD/LOQ".
- **Phần tài liệu liên quan:** mermaid, `t2[Record value with snapshot unit and LOD/LOQ]`.
- **Câu chữ mới:** trong mermaid, `t2[Enter result with snapshot unit and LOD/LOQ]`.

## Báo trưởng bộ phận khi kết quả được gửi

- **Sơ đồ thể hiện:** sau "Sign and send" và "Close testing task", System gửi "✉ Notify head", rồi trưởng bộ phận "Review result, including own entry".
- **Phần tài liệu liên quan:** Main path ("then sends and signs the result for Head of Department approval; submitting it completes the testing task") và mermaid (`t5 --> h1`).
- **Câu chữ mới:**
  - Main path: "… then sends and signs the result for Head of Department approval, and the head is notified; submitting it completes the testing task."
  - Mermaid: `t5 --> notify[Notify the head] --> h1`.
