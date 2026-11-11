# WF-05 Outsourced testing: thay đổi cần đưa vào tài liệu

Những điểm của sơ đồ `[Flow] WF-05 Outsourced testing.drawio` khác với `## WF-05 Outsourced testing` trong `docs/functional/business-flows.md` mà chủ dự án đã chấp nhận. Mỗi mục ghi sơ đồ giờ thể hiện gì, phần nào của tài liệu liên quan và câu chữ mới để cập nhật tài liệu sau.

## 1. Hệ thống đề xuất thuê ngoài khi không máy nào kịp hạn

- **Sơ đồ thể hiện:** luồng bắt đầu ở ● "No machine meets due date (WF-03 Testing assignment and scheduling)". Bước đầu tiên là System "Suggest outsourcing", sau đó trưởng bộ phận "Accept suggestion". WF-05 chỉ có một điểm vào là WF-03.
- **Phần liên quan:** mục **Trigger**, **Starts from** và sơ đồ mermaid của WF-05. *Starts from* hiện ghi "sample tests with an outsourcing suggestion, and accredited subcontractors", tức là đề xuất đã có trước khi WF-05 bắt đầu. Mermaid mở đầu bằng `h1[Review the outsourcing suggestion]` và không có bước của hệ thống.
- **Câu chữ mới:**
  - Starts from: "sample tests whose agreed way no machine can meet by the due date (WF-03 Testing assignment and scheduling), and accredited subcontractors."
  - Mermaid: thêm `start([No machine meets the due date: WF-03 Testing assignment and scheduling]) --> suggest[Suggest outsourcing] --> h1`, đặt `suggest` ngoài các lane như các bước của hệ thống.
- **Cần quyết khi sửa tài liệu:**
  - SF-10-E2 ghi "Outsourcing to a subcontractor with the same method follows WF-05", nhưng sơ đồ không có điểm vào từ SF-10 Scheduling plan and revisions.
  - Trigger còn có trường hợp "the sample test's way is subcontracted", tức là cách thử vốn do thầu phụ làm, không phải vì không máy nào kịp hạn. Điểm vào của sơ đồ chưa có trường hợp này.

## 2. Nhà thầu phụ nhận mẫu

- **Sơ đồ thể hiện:** sau khi trưởng bộ phận ghi ngày gửi, người mang và ngày dự kiến, bước đầu tiên của nhà thầu phụ là "Receive samples", sau đó mới "Enter result".
- **Phần liên quan:**
  - Mermaid của WF-05: `s1[See the dispatch and its tests]`.
  - US-SUB01 trong `laboratory_module/features/subcontractor.md` chỉ nói nhà thầu phụ xem các phiếu gửi cùng sample test và ngày dự kiến của chúng.
  - Mục **States** có "dispatch draft → sent → received", nhưng không tài liệu nào nói ai chuyển phiếu gửi sang received, và vào lúc nào.
- **Câu chữ mới:**
  - Mermaid: `s1[Receive the samples of the dispatch] --> s2[Enter the results]`.
- **Cần quyết khi sửa tài liệu:** "Receive samples" là nhà thầu phụ xác nhận đã nhận mẫu trong hệ thống, việc này chuyển phiếu gửi sang received, hay chỉ là việc nhận mẫu ngoài đời? Nếu là thao tác trong hệ thống thì `subcontractor.md` cần thêm một quy tắc và tiêu chí chấp nhận cho việc xác nhận nhận mẫu.

## 3. Hệ thống ghi ngày gửi, người mang và ngày dự kiến

- **Sơ đồ thể hiện:** khi nhân viên giao mẫu "Carry the dispatch to the subcontractor", **System** "Record when it is sent, who took it and the expected date", sau đó nhà thầu phụ "Receive samples". Trưởng bộ phận không tự ghi những thông tin này.
- **Phần liên quan:**
  - Mermaid của WF-05: `h3[Record when it is sent and the expected date]` nằm trong lane "Head of department".
  - US-HD11 trong `laboratory_module/features/head-of-department.md`: "As a head of department, I want to record when a dispatch is sent, who or which delivery service takes it, and when its results are expected back, …".
  - Dòng *Carrier* của `laboratory_module/features/sample-delivery-staff.md`: "… as the head of department records on it."
- **Câu chữ mới:**
  - Mermaid: bỏ `h3` khỏi lane "Head of department"; đặt ngoài các lane như bước của hệ thống: `d1 --> sent[Record when it is sent, who took it and the expected date] --> s1`.
  - US-HD11: "As a head of department, I want to see when a dispatch was sent, who or which delivery service took it, and when its results are expected back, so that the outsourcing schedule shows where every outsourced test is."
  - Thêm vào dòng *Dispatch* của `head-of-department.md`: "When the dispatch is carried, the system records the date sent, who took it and the expected date from the way's turnaround."
- **Cần quyết khi sửa tài liệu:**
  - Ngày dự kiến có tính từ ngày gửi cộng thời gian xoay vòng (turnaround) của cách thử không?
  - Khi phiếu gửi đi qua đơn vị vận chuyển (WF-05-A1), ai nhập tên đơn vị vận chuyển và mã vận đơn, vì hệ thống không tự biết được những thông tin này?

## 4. Kết quả của nhà thầu phụ đi thẳng tới trưởng bộ phận

- **Sơ đồ thể hiện:** nhà thầu phụ "Enter result", **System** "✉ Notify head", rồi trưởng bộ phận "Review result". Lab QA không gửi kết quả của nhà thầu phụ đi duyệt.
- **Phần liên quan:**
  - Main path của WF-05 ("results are entered and independently approved") và mermaid (`s2 --> h4`) không mâu thuẫn, nhưng chưa có bước thông báo.
  - `laboratory_module/features/subcontractor.md`:
    - Dòng *Approval*: "Results entered by a subcontractor go through the same approval as the laboratory's own results: a lab QA of the department sends them, and the head of department approves them."
    - Dòng *First say*: "While a result the subcontractor entered waits to be sent, a lab QA cannot enter another result for the test."
    - Tiêu chí chấp nhận: "A lab QA cannot enter a result for a test whose subcontractor's result waits to be sent."
  - Dòng *Entered by* của `laboratory_module/overview.md`: "The subcontractor's result comes first: while a result the subcontractor entered waits to be sent, a lab QA cannot enter another one for the test. A lab QA sends them for approval like their own."
- **Câu chữ mới:**
  - Mermaid: `s2 --> notify[Notify the head] --> h4`, đặt `notify` ngoài các lane.
  - `subcontractor.md`, *Approval*: "A result entered by a subcontractor goes to the head of department for approval as soon as it is entered, and the head is notified; it is approved like the laboratory's own results."
  - `subcontractor.md`, *First say*: "While a result the subcontractor entered waits for approval, a lab QA cannot enter another result for the test." Tiêu chí chấp nhận tương ứng: "… whose subcontractor's result waits for approval."
  - `overview.md`, *Entered by*: "… The subcontractor's result comes first: while a result the subcontractor entered waits for approval, a lab QA cannot enter another one for the test. A subcontractor's result goes to approval when entered; a lab QA sends the results they enter like their own."

## 5. Sau khi duyệt, chỉ chuyển sang WF-06 khi cả mẫu đã xong

- **Sơ đồ thể hiện:** sau "Approve result", **System** quyết định "Every test of the sample approved?". Nếu yes thì kết thúc ở ◉ "Sample completed → WF-06 Report signing, release and delivery; SF-01 Invoicing and payment collection". Nếu no thì kết thúc ở ◉ "Wait for other tests". Cách kết thúc này giống WF-04 Result entry and approval.
- **Phần liên quan:** mermaid của WF-05 kết thúc ở `h4 -->|approve| done([Outsourced test approved])` và không chuyển sang luồng nào. Mục **Result** ("the subcontractor's result is approved like any other result") và dòng *Progress* của `laboratory_module/overview.md` (một mẫu hoàn thành khi mọi test còn lại của nó đã được duyệt) đã khớp với sơ đồ.
- **Câu chữ mới:** mermaid: `h4 -->|approve| done([Outsourced test approved])`, `done --> wf06([WF-06 when every test of the sample is approved])`.
- **Cần quyết khi sửa tài liệu:** sơ đồ WF-04 cũng đã bỏ "or cancelled" (mục "Hệ thống kiểm tra mọi test của mẫu đã được duyệt chưa" của `wf-04-doc-changes.md`); dòng *Progress* của `overview.md` vẫn không tính các test đã huỷ.

## 6. Giao cho thầu phụ thất bại thì quay về WF-02 để lấy lại mẫu

- **Sơ đồ thể hiện:** sau "Carry the dispatch to the subcontractor", nhân viên giao mẫu quyết định "Delivered?". Nếu yes thì **System** ghi ngày gửi, người mang và ngày dự kiến như trước. Nếu no thì kết thúc ở ⊗ "Delivery failed → WF-02 Sample reception and handover"; ở WF-02, trưởng bộ phận yêu cầu lấy lại đúng mẫu đó (mục "Lấy lại đúng mẫu khi giao cho thầu phụ thất bại" của `wf-02-doc-changes.md`). Chú giải có thêm dòng "Flow final".
- **Phần liên quan:** mục **Exceptions**, **Paths in other flows** và mermaid của WF-05 (`d1 --> h3`, không có bước kiểm tra giao hàng).
- **Câu chữ mới:**
  - Exceptions: "WF-05-E3: Delivery to the subcontractor fails; the sample is requested again through WF-02 Sample reception and handover."
  - Paths in other flows: "SF-06 for subcontractor accreditation expiry; WF-02 for requesting a sample again after a failed delivery."
  - Mermaid, lane "Sample delivery staff": `d1 --> delivered{Delivered?}`, `delivered -->|yes| sent`, `delivered -->|no| wf02([WF-02 requests the same sample again])`.
- **Cần quyết khi sửa tài liệu:**
  - Phiếu gửi bị huỷ như WF-05-E2 và các test vẫn ở trạng thái outsourced chờ phiếu gửi mới không?
  - Khi mẫu được nhận lại ở WF-02, test quay về WF-05 để vào phiếu gửi mới, hay được xếp lại từ WF-03 Testing assignment and scheduling?
