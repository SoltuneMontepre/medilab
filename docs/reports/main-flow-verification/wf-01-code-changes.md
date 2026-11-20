# WF-01 Việc code theo quyết định

Các quyết định của product owner về WF-01 mà code chưa làm, và tài liệu đã sửa theo các quyết định đó. Code làm theo tài liệu đã sửa; tài liệu là nguồn chuẩn, file này chỉ gom lại cho dễ làm. Bối cảnh của từng quyết định nằm ở mục [Phát hiện](wf-01-order-to-test-request.md#phát-hiện) của báo cáo WF-01.

"Hiện tại" là code của main, đã có [#582](https://github.com/SoltuneMontepre/medilab/issues/582) Request payment before invoicing: tạm ứng và phần còn lại là yêu cầu thanh toán, và đơn chỉ xác nhận được khi tạm ứng đã được xác minh đủ. [PR #613](https://github.com/SoltuneMontepre/medilab/pull/613) chưa merge; việc tự xác nhận yêu cầu khi xác nhận đơn mà nó thêm thì main đã làm.

## Quyết định

| # | Quyết định của product owner | Phát hiện |
| --- | --- | --- |
| Q1 | 18-11-2026. Trưởng phòng kinh doanh là cấp cao nhất của kinh doanh: báo giá do chính họ soạn không cần ai duyệt, kể cả khi vượt ngưỡng. | 1 |
| Q2 | 18-11-2026. WF-01 không có nhân viên giao nhận mẫu; mọi nghiệp vụ về tiền nằm trong WF-01. Hệ thống xác nhận yêu cầu thử nghiệm sang Paid khi tạm ứng đã trả, hoặc On credit khi khách được mua nợ; không ai bấm Confirm. Chỉ khi yêu cầu đã Paid hoặc On credit, khách mới được đưa mẫu cho nhân viên giao nhận mẫu, và WF-02 bắt đầu từ đó. | 6 |
| Q3 | 18-11-2026. Phần còn lại sau tạm ứng được thu ở SF-01 Invoicing and payment collection và không chặn bước nào: mẫu được giao nhận và thử nghiệm khi mới trả tạm ứng. | 3 |
| Q4 | 18-11-2026. Khi đã cài E-commerce, không ai tạo được yêu cầu thử nghiệm không gắn với đơn: danh sách không có nút New, và việc tạo bị từ chối với mọi vai trò. Khách mang mẫu tới thì đi qua sales trước (WF-01-A1). Khi không cài E-commerce, nhân viên giao nhận mẫu vẫn tạo và xác nhận yêu cầu trực tiếp như F-15. | 7 |
| Q5 | 19-11-2026. Báo giá không kèm tạm ứng chỉ gửi được cho khách được mua nợ, kể cả khi Trưởng phòng kinh doanh gửi. Muốn cho khách trả sau thì Trưởng phòng kinh doanh bật cờ mua nợ cho khách. | 8 |
| Q6 | 19-11-2026. Chỉ nhóm kế toán thấy menu Invoices của app E-commerce; nhân viên kinh doanh và Trưởng phòng kinh doanh mở app thì vào Prices hoặc Customer sales terms, không gặp lỗi truy cập. | 9 |

## Việc code

### 1. Yêu cầu thử nghiệm sang Paid ngay khi xác nhận đơn (Q2, Q3)

- **Hiện tại:** `_confirm_order` trong [sale_order_confirmation.py](../../../src/core/modules/sol_commerce/models/orders/sale_order_confirmation.py) tạo yêu cầu phần còn lại rồi gọi `request.action_confirm()`. `_status_after_confirmation` trong [test_request.py](../../../src/core/modules/sol_commerce/models/orders/test_request.py) chỉ trả `paid` khi `_can_collect_samples()` đúng, tức khách được mua nợ hoặc cả đơn đã trả (`payment_status == "paid"`). Vì vậy yêu cầu của khách không mua nợ dừng ở Confirmed cho tới khi phần còn lại được xác minh đủ, lúc `_release_test_request` chuyển nó sang Paid. `_can_collect_samples` còn chặn ba chỗ khác: nhận mẫu (`_check_sample_intake`), nút và phương thức Start sample collection, và cảnh báo chưa thanh toán trên đơn (`show_unpaid_warning`). Thông báo `EVENT_BALANCE_REQUESTED` bảo khách trả phần còn lại "before sample collection".
- **Cần làm:**
  - Xác nhận đơn thì yêu cầu sang Paid ngay, hoặc On credit với khách được mua nợ.
  - Đổi điều kiện của `_can_collect_samples` từ "cả đơn đã trả" sang "yêu cầu đã Paid hoặc On credit", để bốn chỗ dùng nó theo. Khi đó `_release_test_request` không còn chuyển trạng thái nào, và cảnh báo chưa thanh toán trên đơn đã xác nhận không còn trường hợp nào để hiện: bỏ cả hai.
  - Yêu cầu thanh toán phần còn lại vẫn được tạo khi xác nhận đơn và thu ở SF-01; bỏ "before sample collection" khỏi thông báo của nó, kể cả bản dịch.
- **Kiểm thử:** khách không mua nợ, tạm ứng 30%. Xác nhận đơn thì yêu cầu sang Paid, nút Start sample collection hiện và nhận mẫu được, trong khi yêu cầu phần còn lại vẫn mở. Trả phần còn lại không đổi trạng thái của yêu cầu thử nghiệm.

### 2. Bỏ thao tác Confirm bằng tay khi có E-commerce (Q2)

- **Hiện tại:** nút Confirm trên form yêu cầu thử nghiệm ([test_request_views.xml](../../../src/core/modules/sol_laboratory/views/sample_collection/test_request_views.xml)) hiện khi yêu cầu ở Draft, cho ai có quyền sửa mọi yêu cầu; trong demo là Sales, Head of Sales và Sample delivery staff. `action_confirm` gọi được qua RPC.
- **Cần làm:** yêu cầu tạo từ đơn (`from_order`) không có nút Confirm, và người dùng gọi xác nhận trên yêu cầu đó bị từ chối; hệ thống xác nhận qua `_confirm_order`. Yêu cầu không gắn với đơn, chỉ có khi không cài E-commerce, vẫn giữ nút Confirm.

### 3. Nhận mẫu chỉ khi yêu cầu đã Paid hoặc On credit (Q2)

- **Hiện tại:** `action_receive` trong [sample.py](../../../src/core/modules/sol_laboratory/models/sample_collection/sample.py) gọi `_check_sample_intake`. Bản của E-commerce chặn theo `_can_collect_samples` (mục 1); bản của Laboratory không kiểm gì, nên mẫu của một yêu cầu không gắn đơn mà còn Draft vẫn nhận được. Nút Receive trong [sample_views.xml](../../../src/core/modules/sol_laboratory/views/sample_collection/sample_views.xml) chỉ kiểm trạng thái của mẫu.
- **Cần làm:** `_check_sample_intake` của Laboratory từ chối khi yêu cầu chưa tới Paid hoặc On credit, ở mọi lối gọi `action_receive`, kể cả quét nhãn; nút Receive ẩn khi đó. Với E-commerce, sau mục 1, yêu cầu của đơn đã xác nhận luôn đã Paid hoặc On credit.

### 4. Start sample collection chỉ khi yêu cầu đã Paid hoặc On credit (Q2)

Main đã chặn nút và phương thức qua `_can_collect_samples` và `show_unpaid_warning`; làm mục 1 là đủ, không cần chặn thêm. Nút không còn phụ thuộc vào cảnh báo chưa thanh toán khi cảnh báo đó bị bỏ.

### 5. Có E-commerce thì không tạo yêu cầu thử nghiệm bằng tay (Q4)

- **Hiện tại:** nút New luôn hiện; tạo tay một yêu cầu không có đơn thì `_credit_blocks_confirmation` cho qua, nên yêu cầu sang Paid mà không cần tạm ứng. Ba vai trò demo Sales, Head of Sales và Sample delivery staff có `permission_test_request_create_all` ([role.xml](../../../src/core/modules/sol_demo/data/sol_laboratory/role.xml)).
- **Cần làm:**
  - Khi `sol_commerce` được cài, tạo yêu cầu thử nghiệm không qua `create_from_order` (không có `from_order`) bị từ chối với mọi vai trò, và danh sách cùng form không cho tạo mới.
  - Bỏ quyền tạo yêu cầu khỏi các vai trò demo.
  - Không xóa quyền `test_request.create.all`: Laboratory cài riêng vẫn dùng nó. Checklist của [#485](https://github.com/SoltuneMontepre/medilab/issues/485) đang định xóa quyền này nên cần sửa theo; câu hỏi mở của #485 đã được trả lời ở Q4.
- **Những chỗ đang tạo yêu cầu trực tiếp và sẽ hỏng:**
  - Setup Cypress: `staffRequest` của WF-02, setup của WF-06, SF-03, backup signers, scheduling, và spec SF-08 people and approval chains. Các setup này cũng gọi `action_confirm`, nên cũng hỏng theo mục 2. Tìm `"medilab.test.request", "create"` và `action_confirm` để không sót.
  - Demo data: `demo_dispatches.py`, `demo_results.py`.
  - Test Odoo tạo yêu cầu trực tiếp: `request_case.py`, `test_test_request_lifecycle.py`, `test_shared_intervals.py`, `test_is_accredited.py`, `laboratory_files_concurrency_case.py` của `sol_laboratory`; `test_order_confirmation.py`, `test_uninstall.py` của `sol_commerce`. Khi chạy test trong DB có `sol_commerce`, các test này gặp lệnh từ chối mới.
  - TC-F15-01 ("Staff create a test request…") giờ chỉ đúng khi không cài E-commerce; test của nó phải chạy ở trường hợp đó.

### 6. Báo giá của Trưởng phòng kinh doanh không cần duyệt (Q1)

Làm cùng [#414](https://github.com/SoltuneMontepre/medilab/issues/414), vì ngưỡng duyệt báo giá chưa có trong code. Báo giá có salesperson là Trưởng phòng kinh doanh gửi được khi vượt ngưỡng mà không cần duyệt. Cách tính ngưỡng (câu 2 của #414) vẫn chờ quyết định.

### 7. Chỉ gửi báo giá không tạm ứng cho khách được mua nợ (Q5)

- **Hiện tại:** `_check_quotation_can_be_sent` trong [sale_order_advance.py](../../../src/core/modules/sol_commerce/models/orders/sale_order_advance.py) chỉ kiểm người gửi báo giá không tạm ứng có nhóm All orders của Trưởng phòng kinh doanh. Khách không được mua nợ nhận báo giá như vậy thì không vào On credit: `_confirm_order` tạo yêu cầu phần còn lại bằng cả đơn.
- **Cần làm:** gửi báo giá không tạm ứng bị từ chối khi khách không có `allow_credit` trong điều khoản bán hàng, kể cả với Trưởng phòng kinh doanh; thông báo nói phải bật cờ mua nợ cho khách trước. Từ đó đơn đã xác nhận mà không có tạm ứng luôn là đơn On credit.
- **Kiểm lại demo và test gửi không tạm ứng:** ba chỗ `advance_method="none"` trong `demo_quotations.py`, và setup Cypress của WF-01 (`setup.js`), phải dùng khách được mua nợ hoặc chuyển sang có tạm ứng.

### 8. Menu Invoices của app E-commerce chỉ cho nhóm kế toán (Q6)

- **Hiện tại:** `menu_invoice` trong [menus.xml](../../../src/core/modules/sol_commerce/views/system/menus.xml) không giới hạn nhóm, nên hiện với ai đọc được hóa đơn, kể cả Sales qua hóa đơn của đơn mình phụ trách. Đó là menu đầu tiên của app, nên Sales và Head of Sales mở app là gặp lỗi đọc `account.journal`.
- **Cần làm:** giới hạn `menu_invoice` cho nhóm kế toán, cùng nhóm được mở form hóa đơn. App khi đó mở Prices cho Sales, và Prices hoặc Customer sales terms cho Head of Sales.
- **Kiểm thử:** đăng nhập `demo.sales` và `demo.head_of_sales`, mở app E-commerce: không có lỗi, không thấy Invoices; `demo.accountant` vẫn thấy Invoices, Payments và Reconciliation.

## Tài liệu đã sửa

| Tài liệu | Nội dung |
| --- | --- |
| [Business flows](../../functional/business-flows.md#wf-01-order-to-confirmed-test-request) | WF-01: kết quả, trạng thái, main path, acceptance criteria và mermaid theo Q1, Q2, Q3, Q5; bỏ bước khách trả phần còn lại. WF-02: acceptance criteria nhận mẫu khi chưa Paid và tạo yêu cầu không có đơn. SF-01: phần còn lại không chặn giao nhận mẫu hay thử nghiệm. |
| [Activity diagram WF-01](../activity-diagram/final/Core%20flows/WF-01%20Order%20to%20confirmed%20test%20request.drawio) | Trang Workflow: thêm path A1; hệ thống tạo và xác nhận yêu cầu rồi kết thúc luồng; bỏ nhánh "Paid or on credit?" và "Pay balance". Đã xuất lại SVG của trang, chưa build PDF, zip và website. |
| [Sales](../../functional/ecommerce_module/features/sales.md) | US-S15; rule Quotation approval (Q1) và Manager shortcut (Q5) cùng acceptance criteria của chúng; rule Test request, Confirm, Credit gate, Collection và acceptance criteria của mục Confirmation (Q2, Q3). |
| [Accountant](../../functional/ecommerce_module/features/accountant.md) | Hóa đơn cuối thu phần còn lại trong lúc mẫu được giao nhận và thử nghiệm. |
| [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md#2-receiving-samples-us-sd07-to-us-sd12) | Rule Test request và acceptance criteria: hệ thống xác nhận, nhân viên giao nhận mẫu không xác nhận; không tạo yêu cầu khi có E-commerce; không nhận mẫu khi chưa Paid hoặc On credit. |
| [Laboratory overview](../../functional/laboratory_module/overview.md#test-request) | Rule Test request; vòng đời Test request (xác nhận đơn thì yêu cầu sang paid hoặc On credit ngay); ghi chú E-commerce và không có E-commerce thay cho ghi chú "temporary shortcut" của #485. |
| [Invoices](../../specs/invoices.md), [Payments](../../specs/payments.md), [Payment requests](../../specs/payment-requests.md) | Phần còn lại không chặn giao nhận mẫu hay thử nghiệm; xác nhận đơn thì yêu cầu sang Paid ngay; báo giá không tạm ứng chỉ cho khách được mua nợ. |
| [Payment and quotation](../../business/payment-and-quotation.md), [Glossaries](../../glossaries.md) | Báo giá không tạm ứng chỉ cho khách được mua nợ (Q5); thêm thuật ngữ Advance (Tạm Ứng) và Balance (Số Dư). |
| [Module boundaries](../../business/module-boundaries.md#menus) | Hóa đơn, khoản thanh toán và đối soát PayOS trong app E-commerce chỉ dành cho kế toán (Q6). |
| `questions/ecommerce.md` | Gỡ câu "Head of Sales approving their own quotation". |
| `questions/laboratory.md` | Câu "Test requests without E-commerce" chỉ còn hỏi user story và cách đặt ngày trả kết quả cam kết. |
| [Kiểm chứng luồng chính](readme.md#thay-đổi-cho-bm04) | Thay đổi cho BM04: TC-F10-01, TC-F10-02, TC-F15-01. |

## Kết quả mong đợi khi chạy tay

Main path của [báo cáo WF-01](wf-01-order-to-test-request.md#main-path) đã sửa theo các quyết định:

- Bước 11: xác nhận đơn đã trả tạm ứng thì yêu cầu được tạo và sang Paid ngay.
- Bước 12: nhân viên giao nhận mẫu không thấy nút New trong danh sách yêu cầu thử nghiệm, và form yêu cầu không có nút Confirm.
- Bước 14: có nút Start sample collection.

Các bước thanh toán 6 đến 10 được viết cho hóa đơn tạm ứng của code trước #582; chạy trên main thì phải viết lại theo yêu cầu thanh toán.

## Chưa quyết, chưa code

- Cách tính ngưỡng duyệt báo giá: câu "Measuring approval thresholds" trong `questions/ecommerce.md`, chặn #414.
- Sales ghi nhận khoản trả tiền mặt hay chuyển khoản trên đơn (phát hiện 2, path WF-01-A4): code chưa có thao tác này, product owner chưa chọn xây thao tác hay sửa tài liệu.
- Laboratory cài riêng: user story của việc tạo yêu cầu trực tiếp, và cách đặt ngày trả kết quả cam kết khi không có đơn.

## Lưu ý khi rebase PR #613

Nhánh `hoang-test-local` đã thử merge `feat/416-requested-committed-dates` và PR #613 vào main và gặp xung đột ở:

- Version và migration: version mới phải cao hơn của main, nếu không migration không chạy.
- Phần nhận mẫu trong `sample.py`, `test_sample_reception.py`, các file `.pot` (sau khi gộp có msgid trùng), spec Cypress WF-01 (main đã tách thành nhiều file) và hàm quét nhãn của spec WF-02.
- TC-F06-03 "line not on a sample" trong `quotation.cy.js` đã lỗi thời so với hành vi gắn mẫu khi gửi báo giá của #613.

Sau lần thử đó, #582 vào main và sửa chính `_confirm_order`, `_credit_blocks_confirmation` và luồng tạm ứng, nên PR #613 còn xung đột thêm ở các chỗ này.

## Tài liệu liên quan

- [WF-01 Order to confirmed test request](wf-01-order-to-test-request.md)
- [Kiểm chứng luồng chính](readme.md)
- [Business flows](../../functional/business-flows.md)
