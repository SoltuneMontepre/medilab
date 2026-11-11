# WF-01: khác biệt đã chấp nhận so với business-flows.md

Mỗi mục ghi điều sơ đồ của Tuyên đang thể hiện, phần của `## WF-01 Order to confirmed test request` trong `docs/functional/business-flows.md` mà nó liên quan, và câu chữ mới để cập nhật tài liệu sau.

## 1. Head of Sales từ chối báo giá vượt ngưỡng

- **Sơ đồ thể hiện:** sau "Review quotation", Head of Sales quyết định "Approve?". Nếu không duyệt: "✉ Notify sales" → Sales "Adjust quotation" → "Request approval" lại. Nếu duyệt: "Sign approval" → "Send quotation". Trang Demo scenarios minh hoạ đường này ở "DS-01d Head of Sales declines quotation ↔ WF-01-E3".
- **Phần liên quan:** mục **Exceptions** và sơ đồ mermaid của WF-01. Tài liệu hiện chỉ có "Approve the quotation before Send", không có đường từ chối. `ecommerce_module/features/sales.md`, dòng "Quotation approval", cũng chỉ nói báo giá bị chặn gửi cho tới khi được duyệt.
- **Câu chữ mới:**
  - Thêm vào Exceptions: "WF-01-E3: The Head of Sales declines a quotation above the approval thresholds with a reason; sales adjusts it and requests approval again, and the Head of Sales approves it."
  - Mermaid, lane Head of Sales: thay `h0[Approve the quotation before Send]` bằng `h0{Approve the quotation?}`, thêm `h0 -->|yes| s3` và `h0 -->|decline with a reason| s7[Adjust the quotation] --> h0`, với `s7` trong lane Sales.

## 2. Trả số dư trước khi kết thúc WF-01

- **Sơ đồ thể hiện:** "Confirm order" → System "Create test request" → "Paid or on credit?". Nếu khách đã trả đủ hoặc được mua chịu, luồng kết thúc. Nếu không, khách "Pay balance (PayOS)" → System "Record payment". Luồng kết thúc ở ◉ "Test request paid → WF-02 Sample reception and handover".
- **Phần liên quan:** các mục **Result**, **Main path** và sơ đồ mermaid của WF-01. Mục **States** đã có "test request draft → confirmed → paid", khớp với sơ đồ.
- **Câu chữ mới:**
  - Result: "the order is confirmed and its test request is paid, unless its customer may order on credit, with expected samples and their selected ways calculated from the accepted order and sampling requirements, and sample collection can start."
  - Main path, thay đoạn cuối: "… sales confirms the order, which creates its test request; unless the customer may order on credit, the customer pays the balance online, and sample collection can start."
  - Mermaid: thay `s4 --> done(...)` bằng `s4 --> paid{Paid in full or on credit?}`, `paid -->|yes| done`, `paid -->|no| c7[Pay the balance online] --> done`, với `c7` trong lane Customer; `done(["Test request paid; sample collection can start"])`.
- **Cần quyết khi sửa tài liệu:** SF-01 Invoicing and payment collection hiện lập hoá đơn cuối ("total minus the advance") sau khi kiểm nghiệm xong. Nếu số dư đã trả trong WF-01, SF-01 phải trừ cả số dư này, hoặc chỉ còn lại hoá đơn điều chỉnh. Dòng "Credit gate" của `ecommerce_module/features/sales.md` hiện chỉ chặn theo tiền tạm ứng ("until its advance is paid in full").
