# WF-06 Report signing, release and delivery: thay đổi cần đưa vào tài liệu

Những điểm của sơ đồ `[Flow] WF-06 Report signing, release and delivery.drawio` khác với `## WF-06 Report signing, release and delivery` trong `docs/functional/business-flows.md` mà chủ dự án đã chấp nhận. Mỗi mục ghi sơ đồ giờ thể hiện gì, phần nào của tài liệu liên quan và câu chữ mới để cập nhật tài liệu sau.

## 1. Lab Head từ chối: trưởng bộ phận duyệt lại rồi Lab Head xem lại

- **Sơ đồ thể hiện:** ở "Report OK?", nhánh "no, name result" tới trưởng bộ phận "Re-approve result", rồi quay về "Review report" của Lab Head. Luồng không rời WF-06.
- **Phần liên quan:**
  - WF-06-E2: "the results go back to the head of department's queue, are approved again and the lab head signs the new task."
  - Mermaid của WF-06: `l2 -->|reject naming the results and the reason| h1 --> wf04([WF-04 approves them again])`, với `h1[Results sent back wait in the queue unassigned]`.
- **Câu chữ mới:**
  - WF-06-E2: "The lab head rejects the report naming results and a reason; the head of department approves the named results again, and the lab head reviews the report again."
  - Mermaid: thay `h1[Results sent back wait in the queue unassigned]` bằng `h1[Re-approve the named results]`, thay `h1 --> wf04([WF-04 approves them again])` bằng `h1 --> l1`.
- **Cần quyết khi sửa tài liệu:** dòng *Rejection* của `laboratory_module/features/lab-head.md` ghi các kết quả bị từ chối được rút chữ ký, mẫu và yêu cầu quay lại kiểm nghiệm, một nhiệm vụ kiểm nghiệm mới chờ trong hàng của bộ phận, và Lab Head nhận một nhiệm vụ ký **mới**. Như vậy kết quả có thể được đo lại theo WF-04 Result entry and approval chứ không chỉ được duyệt lại. Cần chọn: sửa dòng này cho khớp với sơ đồ, hoặc ghi rõ vòng lặp của sơ đồ đã gộp cả việc kiểm nghiệm lại.

## 2. Báo cáo luôn được ký số

- **Sơ đồ thể hiện:** sau "Keep final internal approval bound to reviewed PDF", hệ thống luôn "Digitally sign the reviewed PDF". Sơ đồ không có quyết định "Digital signing enabled?" và không có nhánh lưu PDF không chữ ký số.
- **Phần liên quan:**
  - Main path của WF-06: "With digital signing enabled, MediLab digitally signs that same PDF and stores it before issuing the report."
  - WF-06-A4: "With digital signing disabled, MediLab stores the reviewed PDF without a digital signature and issues it after final internal approval."
  - Mermaid của WF-06: `approved --> enabled{Digital signing enabled?}`, `enabled -->|yes| digital`, `enabled -->|no| plain[Store reviewed PDF without digital signature]`, `plain --> issued`.
- **Câu chữ mới:**
  - Main path: "… then gives final internal approval. MediLab digitally signs that same PDF and stores it before issuing the report. …"
  - Bỏ WF-06-A4.
  - Mermaid: thay `approved --> enabled{...}` và `enabled -->|yes| digital` bằng `approved --> digital`; bỏ `enabled -->|no| plain[...]` và `plain --> issued`.
- **Cần quyết khi sửa tài liệu:** chức năng tắt ký số vẫn được mô tả ở nơi khác. `docs/specs/digital-signing.md` ghi "Digital signing is off until an administrator turns it on in the Laboratory settings", và dòng *Issued* của `laboratory_module/features/lab-head.md` ghi "When signing is off, store the approved prepared PDF and issue it without a digital signature." Cần chọn: bỏ cài đặt tắt ký số khỏi hệ thống, hoặc giữ cài đặt này và chỉ coi sơ đồ là đường khi ký số đang bật.

## 3. Các bước của hệ thống và đường giao báo cáo trong mermaid

- **Sơ đồ thể hiện:**
  - Ở đầu luồng, hệ thống "Create draft report" rồi "✉ Notify lab head", trước khi Lab Head sửa bản nháp.
  - Sau khi phát hành, hệ thống "✉ Notify customer". Từ đó luồng tách hai nhánh: khách "Download report", nhân viên giao "Record delivery".
  - Sau "Record delivery", quyết định "Delivered by e-mail?": yes thì hệ thống "✉ Email report PDF", no thì không gửi e-mail. Cả hai cùng kết thúc ở "Report delivered".
- **Phần liên quan:** mermaid của WF-06. Câu chữ đã khớp: Trigger ("the system creates the draft report and a signing task for the lab head"), Main path ("enables delivery and customer notification"), WF-06-A1, và dòng *Delivery* của `laboratory_module/features/sample-delivery-staff.md` ("A report sent by email is emailed to its recipient from the system"). Riêng mermaid chưa có các bước này, và đang vẽ giao trước rồi mới ghi nhận (`d1[Deliver in person, by post or by e-mail] --> d2[Record the delivery]`).
- **Câu chữ mới cho mermaid:**
  - Đầu luồng: `draft[Create the draft report] --> notifyLab[Notify the lab head] --> p1`, đặt ngoài các lane như các bước khác của hệ thống.
  - Thay `issued --> c1` và `issued --> d1` bằng `issued --> notifyCustomer[Notify the customer]`, `notifyCustomer --> c2`, `notifyCustomer --> d2`.
  - Bỏ `c1[Notified that the report is issued]` và `d1[Deliver in person, by post or by e-mail]`. Thêm `d2 --> email{Delivered by e-mail?}`, `email -->|yes| send[E-mail the report PDF]`.
