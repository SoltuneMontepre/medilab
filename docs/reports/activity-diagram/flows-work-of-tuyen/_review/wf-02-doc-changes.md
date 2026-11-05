# WF-02 Sample reception and handover: thay đổi cần đưa vào tài liệu

Những điểm sơ đồ `[Flow] WF-02 Sample reception and handover.drawio` đã được chấp nhận khác với `## WF-02 Sample reception and handover` trong `docs/functional/business-flows.md`. Mỗi mục ghi sơ đồ giờ thể hiện gì, phần nào của tài liệu bị ảnh hưởng và câu chữ mới.

## Khác với business-flows.md

### Hệ thống loại mẫu không dùng được

- **Sơ đồ thể hiện:** nhân viên nhận mẫu xét tình trạng ở "Condition?"; với nhánh unusable, **System** "Reject sample" rồi kết thúc ◉ "Sample rejected". Nhân viên không tự bấm loại mẫu; ghi chú tình trạng đã được ghi ở bước "Adjust expected samples and record differences".
- **Phần tài liệu liên quan:**
  - Mermaid của WF-02: `d2 -->|unusable| d6[Reject with a condition note]` nằm trong lane "Sample delivery staff".
  - `laboratory_module/features/sample-delivery-staff.md`, US-SD10: "As sample delivery staff, I want to reject a sample that cannot be tested, with the reason, so that nobody works on it."
- **Câu chữ mới:**
  - Mermaid: bỏ `d6` khỏi lane "Sample delivery staff"; đặt ngoài các lane như `keep`: `d2 -->|unusable| reject[Reject sample] --> rejected([Sample rejected])`.
  - US-SD10: "As sample delivery staff, I want to record a sample that cannot be tested as unusable, with the reason, so that the system rejects it and nobody works on it."
  - *Acceptance criteria* của WF-02 giữ nguyên: "An unusable sample is rejected with its condition note and gets no testing task."
- **Trang Demo scenarios:** "DS-02c One of two samples unusable ↔ WF-02 unusable sample" cũng dùng System "Reject sample". Đường loại mẫu chưa có mã riêng trong tài liệu, nên tên dải ghi "WF-02 unusable sample".

### Mẫu dư được trả lại ở SF-04

- **Sơ đồ thể hiện:** từ "Confirm actual samples and sign the record", cạnh nét đứt "extra samples or excess material" tới System "Kept with the sample, no test added; returned on request", rồi ⊗ "→ SF-04 Sample retention, return and disposal".
- **Phần tài liệu liên quan:** WF-02-E4 và mermaid của WF-02 (`keep[...]` không có điểm kết thúc); SF-04 có US-SD15 trong *Stories* nhưng không nhắc tới mẫu dư của WF-02.
- **Câu chữ mới:**
  - WF-02-E4: "… they add no test, change no order and stay with the sample until the customer asks for them back; SF-04 Sample retention, return and disposal owns the return."
  - Mermaid: `keep --> sf04([SF-04 Sample retention, return and disposal])`.

### Lấy lại đúng mẫu khi giao cho thầu phụ thất bại

- **Sơ đồ thể hiện:** điểm vào thứ hai ● "Delivery to the subcontractor failed (WF-05 Outsourced testing)" ở lane Head of department. Trưởng bộ phận "Request the same sample again", rồi **System** "Create collection task" và nhân viên giao mẫu đi lấy mẫu như đường lấy thêm mẫu ở WF-02-E1.
- **Phần tài liệu liên quan:** mục **Trigger**, **Exceptions** và mermaid của `## WF-02 Sample reception and handover`; WF-02 chưa có đường nào nhận việc từ WF-05.
- **Câu chữ mới:**
  - Trigger: "samples arrive at the laboratory, sample delivery staff collect them from the customer, or a sample must be collected again after a failed delivery to a subcontractor (WF-05 Outsourced testing)."
  - Exceptions: "WF-02-E5: A sample whose delivery to a subcontractor failed is requested again: the head of department asks for the same sample, and its collection task brings it back to received."
  - Mermaid, lane "Head of department": `wf05([WF-05: delivery to the subcontractor failed]) --> h3[Request the same sample again] --> d8`.
- **Cần quyết khi sửa tài liệu:** mẫu lấy lại giữ nguyên mã lab và các sample test cũ, hay là một mẫu mới? Trong lúc chờ, mẫu ở trạng thái on hold như mẫu thiếu không?

## Tài liệu khác mâu thuẫn với business-flows.md

### Thứ tự nhận mẫu và xét tình trạng

- **Sơ đồ thể hiện:** theo business-flows.md. Sau "Adjust expected samples and record differences" là quyết định "Condition?" ba nhánh; chỉ nhánh good tới "Record receipt, time, amount and storage", nhánh unusable tới System "Reject sample", nhánh insufficient tới nhân viên "Put on hold". Mẫu hỏng hoặc thiếu không qua trạng thái received.
- **Mâu thuẫn:** `docs/functional/laboratory_module/overview.md`:
  - Sơ đồ trạng thái *Sample* vẽ `received --> rejected: unusable on arrival` và `received --> on_hold: insufficient on arrival`, tức là mẫu được nhận trước rồi mới bị loại hoặc tạm giữ.
  - Quy tắc *Receipt* (mục Reception) ghi tình trạng good, damaged hoặc insufficient ngay lúc ghi nhận nhận mẫu.
  - Tiêu chí chấp nhận của *Receiving samples* trong `features/sample-delivery-staff.md` ("Recording a sample's receipt sets it to received and creates its testing tasks") cũng ngầm hiểu nhận mẫu xảy ra trước.
- **Câu chữ mới cho overview.md**, sơ đồ trạng thái *Sample*:

  ```
  expected --> received: sample received in good condition
  expected --> rejected: unusable on arrival
  expected --> on_hold: insufficient on arrival
  on_hold --> received: more sample collected
  ```

  Bỏ hai dòng `received --> rejected` và `received --> on_hold`. Quy tắc *Receipt*: "When a sample in good condition arrives, the laboratory records when and by whom it was received, the amount received, its condition note and where it is stored. An unusable sample is rejected and an insufficient one is put on hold before receipt."
