# WF-04 Result entry and approval: thay đổi cần đưa vào tài liệu

Những điểm sơ đồ `[Flow] WF-04 Result entry and approval.drawio` đã được chấp nhận khác với `## WF-04 Result entry and approval` trong `docs/functional/business-flows.md`. Mỗi mục ghi sơ đồ giờ thể hiện gì, phần nào của tài liệu bị ảnh hưởng và câu chữ mới.

## Lưu tệp kết quả nằm trên luồng chính

- **Sơ đồ thể hiện:** sau "Start booking; mark machine busy", tester quyết định "Testing produces files?". Nhánh yes đi qua "Save result file" và System "Sync file version" rồi tới "Enter result with snapshot unit and LOD/LOQ"; nhánh no đi thẳng tới bước nhập kết quả.
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

## Hệ thống hiện giới hạn, tester đánh giá kết quả

- **Sơ đồ thể hiện:** khi có yêu cầu so sánh quy chuẩn, System "Show related regulation limit" rồi tester "Assess the result". Trang Demo scenarios dùng hai nhãn này ở DS-04a.
- **Phần tài liệu liên quan:** mermaid của `## WF-04 Result entry and approval`, nơi nhánh yes của `q` đi thẳng tới `t3[Assess exact type limit: pass, fail or insufficient basis]` mà không có bước của hệ thống. Các dòng *Limit copy* và *Conclusion* của [Tester](../../../../functional/laboratory_module/features/tester.md) đã nói hệ thống chép và hiện giới hạn đúng loại, còn tester đánh giá pass, fail hoặc insufficient basis.
- **Câu chữ mới:** mermaid: `q -->|yes| limit[Show related regulation limit] --> t3`, với `limit` ngoài các lane người, và `t3[Assess the result]`.

## Báo trưởng bộ phận khi kết quả được gửi

- **Sơ đồ thể hiện:** sau "Sign and send", "Close testing task" và "Mark machine available", System gửi "✉ Notify head", rồi trưởng bộ phận "Review result".
- **Phần tài liệu liên quan:** Main path ("then sends and signs the result for Head of Department approval; submitting it completes the testing task") và mermaid (`t5 --> h1`).
- **Câu chữ mới:**
  - Main path: "… then sends and signs the result for Head of Department approval, and the head is notified; submitting it completes the testing task."
  - Mermaid: `free --> notify[Notify the head] --> h1`, với `free` ở mục "Máy bận khi booking bắt đầu, rảnh khi kết quả được gửi".

## Hệ thống kiểm tra mọi test của mẫu đã được duyệt chưa

- **Sơ đồ thể hiện:** sau "Approve result", **System** quyết định "Every test of the sample approved?". Nếu yes thì kết thúc ở ◉ "Sample completed → WF-06 Report signing, release and delivery; SF-01 Invoicing and payment collection", nếu no thì ở ◉ "Wait for other tests". Câu hỏi không nhắc tới test đã huỷ, giống WF-05 Outsourced testing.
- **Phần tài liệu liên quan:** mermaid của `## WF-04 Result entry and approval` (`done --> wf06([WF-06 when every test is approved or cancelled])`) và mục **Result** ("the sample completes when all its tests do").
- **Câu chữ mới:** mermaid: `done --> wf06([WF-06 when every test of the sample is approved])`.
- **Cần quyết khi sửa tài liệu:** dòng *Progress* của `laboratory_module/overview.md` và WF-04-E3 vẫn nói một mẫu hoàn thành khi các test còn lại đã được duyệt, không tính test đã huỷ. Câu hỏi trên sơ đồ có cần nói rõ "remaining tests" không?

## Máy bận khi booking bắt đầu, rảnh khi kết quả được gửi

- **Sơ đồ thể hiện:** từ điểm bắt đầu, System "Start booking; mark machine busy" rồi tới "Testing produces files?"; bước Tester "Follow the method and measure in the booking" không còn. Đường "retest with a new booking" cũng quay về "Start booking; mark machine busy". Sau "Sign and send" và "Close testing task", System "Mark machine available" rồi "✉ Notify head". Trang Demo scenarios thể hiện hai bước này ở DS-04a, DS-04b (máy bận khi thử lại với booking mới) và DS-04c (máy rảnh sau khi gửi).
- **Phần tài liệu liên quan:**
  - `## WF-04 Result entry and approval`: **States** (chưa có trạng thái máy), Main path ("The tester follows the agreed method, records the result …; submitting it completes the testing task.") và mermaid (`t1[Follow the method and measure in the booking]`, `t6 --> t2`, `t5 --> h1`).
  - [Administrator](../../../../functional/laboratory_module/features/admin.md), dòng *Machine*: trạng thái máy chỉ có "in use, under repair or retired".
  - [Laboratory overview](../../../../functional/laboratory_module/overview.md), dòng *Machine unavailable* và SF-05 Machine calibration and unavailability: "unavailable" là máy hỏng hoặc mất hiệu chuẩn, làm các booking chưa bắt đầu bị xếp lại. Busy không phải unavailable và không xếp lại booking nào.
- **Câu chữ mới:**
  - States: thêm "machine available → busy when its booking starts → available when the result is submitted".
  - Main path: "When a booked test starts, the system marks its machine busy. The tester records the result of the booking …; submitting it completes the testing task and marks the machine available."
  - Mermaid: thay `t1` bằng `start[Start booking; mark machine busy]` ngoài các lane người, mọi đường đi ra từ `t1` giờ đi ra từ `start`; thay `t6 --> t2` bằng `t6 --> start`; thay `t5 --> h1` bằng `t5 --> free[Mark machine available] --> h1`.
  - Administrator, dòng *Machine*: "While a booking runs on a machine, the machine is busy; it is available again when the result of the booking is submitted. Busy is not unavailability: it returns no booking to the plan."
- **Cần quyết khi sửa tài liệu:** một máy có thể chạy nhiều booking cùng khung giờ (dòng *No overlap* của overview), và cách thử không cần máy thì không có máy. Máy rảnh lại khi booking cuối cùng trong khung gửi kết quả, hay khi từng booking gửi?

