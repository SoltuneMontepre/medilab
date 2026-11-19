# WF-01 Order to confirmed test request

Kiểm chứng WF-01 Order to confirmed test request theo [phương pháp](readme.md#phương-pháp) của đợt kiểm chứng luồng chính. Luồng được mô tả trong [Business flows](../../functional/business-flows.md#wf-01-order-to-confirmed-test-request).

## Lượt chạy browser test

[`order-to-test-request.cy.js`](../../../src/tests/cypress/e2e/flows/wf-01-order-to-test-request/order-to-test-request.cy.js) chạy trong Cypress App với Chrome ngày 16-11-2026 tại commit `e7bd7697`: 31 đạt, không có test fail, pending hay skipped, trong 4 phút 30 giây.

Sau lượt chạy này, năm test kiểm acceptance criteria được đổi tiêu đề sang ID test case của [danh sách tính năng](../feature-list/readme.md), và các bảng dưới đây dùng tiêu đề mới. Test của mỗi tính năng sẽ được chuyển về thư mục của flow sở hữu tính năng đó; khi việc sắp lại xong, lượt chạy browser test được chạy lại và mục này được cập nhật.

## Các path

| Path | Tài liệu | BM04 | Browser test | Kết luận | Chạy tay |
| --- | --- | --- | --- | --- | --- |
| Main | Khách hàng đặt hàng trên portal; nhân viên kinh doanh nhận đơn, xác nhận cách thử và nhu cầu lấy mẫu dự kiến, xin Trưởng phòng kinh doanh duyệt khi vượt ngưỡng, rồi gửi báo giá kèm yêu cầu tạm ứng; khách trả tạm ứng trực tuyến; nhân viên kinh doanh xác nhận đơn, hệ thống tạo yêu cầu thử nghiệm và xác nhận nó sang Paid; khách được đưa mẫu, có thể bắt đầu giao nhận mẫu. Phần còn lại thu ở SF-01, không chặn bước nào. | DS-01a | TC-WF01-M, đạt | Partial | [Cần chạy](#main-path) |
| A1 | Nhân viên kinh doanh tạo đơn cho khách gọi điện hoặc mang mẫu tới; mẫu chờ ở quầy nhận mẫu cho tới khi yêu cầu thử nghiệm được thanh toán. | F-05 | TC-WF01-A1, đạt | Partial | Không chạy tay |
| A2 | Khách chưa đăng nhập gửi giỏ hàng kèm thông tin và địa chỉ email. | F-04 | TC-WF01-A2, đạt | Covered | Không chạy tay |
| A3 | Khách quen đặt lại một đơn đã hoàn tất, hoặc nhân viên kinh doanh tạo đơn từ đơn thường dùng của khách. | F-04 | TC-WF01-A3, đạt | Covered | Không chạy tay |
| A4 | Khách trả tạm ứng bằng chuyển khoản hoặc tiền mặt; nhân viên kinh doanh ghi nhận, kế toán xác nhận. | DS-01e | không có | Missing | Trong [main path](#main-path), bước 8 đến 10 |
| A5 | Trưởng phòng kinh doanh gửi báo giá không tạm ứng cho khách được mua nợ; khách chấp nhận trên portal; đơn tiếp tục khi chưa thanh toán. | không có | TC-WF01-A7, đạt | Covered, Drift | Không chạy tay |
| E1 | Khách từ chối báo giá kèm lý do; nhân viên kinh doanh sửa và gửi phiên bản mới, khách chấp nhận. | DS-01b | TC-WF01-A5, đạt | Covered, Drift | [Cần chạy](#e1-báo-giá-bị-từ-chối) |
| E2 | Báo giá quá hạn thanh toán và bị đánh dấu hết hạn; nhân viên kinh doanh gia hạn; khách thanh toán trong hạn mới. | DS-01c | TC-WF01-A6, đạt | Partial, Drift | [Cần chạy](#e2-báo-giá-quá-hạn) |
| E3 | Trưởng phòng kinh doanh từ chối báo giá vượt ngưỡng kèm lý do; nhân viên kinh doanh điều chỉnh và xin duyệt lại; Trưởng phòng kinh doanh duyệt. | DS-01d | không có | Missing | [Bị chặn](#e3-báo-giá-bị-trưởng-phòng-kinh-doanh-từ-chối) |

Căn cứ cho từng kết luận:

- **Main:** test đi theo một đơn portal qua bước nhận đơn, thêm mẫu, đúng một hóa đơn tạm ứng và trang chờ PayOS của khách; sau đó nó xác nhận một đơn thứ hai do `setup.js` đưa sẵn tới `accepted`, rồi kiểm yêu cầu thử nghiệm của đơn này và việc nội dung đơn bị khóa. Test không kiểm bước duyệt vượt ngưỡng, việc khoản thanh toán trực tuyến được khớp vào đơn, hay việc chính đơn này sau khi thanh toán được xác nhận và yêu cầu thử nghiệm của nó sang Paid.
- **A1:** test kiểm nhân viên kinh doanh tạo được đơn, đơn do chính họ nhận, theo giá danh mục. Việc mẫu chờ ở quầy nhận mẫu tới khi thanh toán không được kiểm.
- **A4:** `payAdvance` trong `setup.js` khai một khoản chuyển khoản trên hóa đơn ở portal rồi để kế toán ghi sổ, không có assertion nào. Không test nào cho nhân viên kinh doanh ghi nhận thanh toán.
- **A5, E1, E2:** tiêu đề mang ID cũ: A7 cho A5, A5 cho E1, A6 cho E2.
- **E2:** test kiểm cờ hết hạn, việc gia hạn và ngày đến hạn của hóa đơn tạm ứng, không kiểm việc khách thanh toán sau khi gia hạn.

## Acceptance criteria của luồng

Các kiểm tra dữ liệu sai, quyền và không cho sửa thuộc về acceptance criteria của tính năng, theo Business flows, nên chúng nằm trong nhóm `WF-01 feature acceptance criteria` của spec, mang ID test case của [danh sách tính năng](../feature-list/readme.md).

| Tiêu chí | Browser test | Kết luận |
| --- | --- | --- |
| Cách thử mặc định không dùng được thì không bao giờ bị thay thế ngầm. | không có; TC-WF01-M chỉ kiểm cách thử mặc định được điền sẵn | Missing |
| Báo giá vượt ngưỡng duyệt không gửi được trước khi Trưởng phòng kinh doanh duyệt, trừ khi chính Trưởng phòng kinh doanh soạn. | không có | Missing |
| Giỏ hàng gửi không có địa chỉ email bị từ chối. | TC-F04-03 | Covered |
| Nội dung đơn đã xác nhận chỉ đổi qua báo giá sửa đổi mà khách chấp nhận. | TC-WF01-M từ chối đổi ngày hiệu lực; TC-F06-02 từ chối sửa một dòng của báo giá đã gửi | Partial |
| Phiên bản cũ của báo giá đã sửa không gửi hay xác nhận được. | TC-F06-02 từ chối gửi và sửa; chưa thử xác nhận | Partial |
| Đơn chưa xác minh đủ tạm ứng không xác nhận được; xác nhận đơn thì yêu cầu thử nghiệm được xác nhận, Paid hoặc On credit. | TC-F10-02 kiểm phần xác nhận; không test nào kiểm nút Start sample collection | Partial |
| Không ai xác nhận yêu cầu thử nghiệm bằng tay. | không có | Missing |
| Báo giá không kèm tạm ứng chỉ gửi được cho khách được mua nợ. | không có | Missing |
| Khách hàng khác mở báo giá, hóa đơn hay kết quả bị từ chối. | TC-F03-03 | Covered |

Spec còn kiểm một rule của Quotation trong [Sales](../../functional/ecommerce_module/features/sales.md): báo giá có dòng chưa gắn mẫu không gửi được, bằng TC-F06-03.

## ID test case của BM04

BM04 giao cho WF-01 các tính năng F-04, F-05, F-06, F-09 và F-10, tổng cộng 15 ID test case. Tiêu đề trong spec mang 10 ID. Một ID test case trong [danh sách tính năng](../feature-list/readme.md) có thể gồm nhiều ý, nên có ID được kiểm bằng hai test: TC-F06-01, TC-F06-02, TC-F06-03 và TC-F10-02. Các ID còn lại:

| ID | Test case trong BM04 | Được kiểm bởi |
| --- | --- | --- |
| TC-F04-01 | Khách chưa đăng nhập gửi giỏ hàng kèm thông tin. | TC-WF01-A2 |
| TC-F05-01 | Nhân viên kinh doanh nhận một đơn đã gửi hoặc tạo đơn cho khách gọi điện. | TC-WF01-M và TC-WF01-A1 |
| TC-F09-01 | Gửi báo giá kèm tạm ứng tạo đúng một hóa đơn tạm ứng đã ghi sổ. | TC-WF01-M kiểm có một hóa đơn, không kiểm hóa đơn đã ghi sổ |
| TC-F09-03 | Thông báo PayOS gửi lặp lại không tạo khoản thanh toán thứ hai. | không có trong spec này |
| TC-F10-03 | Người xin duyệt không tự duyệt được; báo giá bị từ chối quay về kèm lý do; báo giá đang chờ duyệt không sửa được. | không có |

Theo cột Workflow của danh sách tính năng, WF-01 sở hữu F-04, F-05, F-06, F-07, F-09 và F-10; F-07 không thuộc nhóm bắt buộc của BM04. Spec còn chứa test của F-01 và F-02, do SF-08 Laboratory setup sở hữu, và của F-03, do SF-09 Customer support and feedback sở hữu. Các test này không tính vào WF-01 và sẽ chuyển về flow sở hữu.

## Phát hiện

Sẽ review cùng product owner sau lượt chạy tay; khi đó mỗi phát hiện được xếp loại và thành issue, câu hỏi hoặc quyết định.

1. Ngưỡng duyệt báo giá và chốt chặn khi gửi chưa được xây: `sol_commerce` không có code nào cho phần này, còn [#414](https://github.com/SoltuneMontepre/medilab/issues/414) vẫn mở và đang chờ hai câu hỏi trong `questions/ecommerce.md`. Điều này làm thiếu bước duyệt của main path, E3, một acceptance criterion của luồng, BM04 DS-01a và DS-01d, exception của F-06 và F-10. Quyết định của product owner ngày 18-11-2026: Trưởng phòng kinh doanh là cấp cao nhất của kinh doanh, nên báo giá do chính họ soạn không cần ai duyệt; câu hỏi về cách tính ngưỡng vẫn chờ quyết định. Đã ghi vào rule Quotation approval của [Sales](../../functional/ecommerce_module/features/sales.md#2-quotation-us-s05-to-us-s10-us-s21-us-s22) và gỡ câu hỏi khỏi `questions/ecommerce.md`; việc code nằm trong [WF-01 Việc code theo quyết định](wf-01-code-changes.md).
2. Không tìm thấy thao tác nào để nhân viên kinh doanh ghi nhận khoản thanh toán tiền mặt hay chuyển khoản trên đơn; cách duy nhất là khách tự khai trên hóa đơn ở portal. Điều này ảnh hưởng A4 và BM04 DS-01e. Main path kiểm lại điều này bằng tay.
3. Tài liệu mâu thuẫn về thời điểm được bắt đầu giao nhận mẫu. Rule Credit gate trong [Sales](../../functional/ecommerce_module/features/sales.md#4-confirmation-us-s12-us-s15) nói phải trả xong phần còn lại; acceptance criterion của chính mục đó và TC-F10-02 nói ngay khi đơn được xác nhận; BM04 F-10 nói khách trả phần còn lại trước khi thử nghiệm.

   Quyết định của product owner ngày 18-11-2026: khách được đưa mẫu khi đã trả tạm ứng hoặc được mua nợ; phần còn lại thu ở SF-01 Invoicing and payment collection và không chặn việc giao nhận mẫu hay thử nghiệm. Đã sửa Business flows (WF-01, SF-01), Sales, Accountant, Laboratory overview và các spec Invoices, Payments, Payment requests; TC-F10-02 được ghi vào [Thay đổi cho BM04](readme.md#thay-đổi-cho-bm04).
4. Ba tiêu đề browser test dùng cách đánh số path cũ: A7 cho A5, A5 cho E1, A6 cho E2. Checklist của [#152](https://github.com/SoltuneMontepre/medilab/issues/152) cũng còn đánh số cũ.
5. Test main path không đi trọn chính đơn của nó từ lúc thanh toán tới lúc xác nhận.
6. Business flows chưa có bước xác nhận yêu cầu thử nghiệm. Theo [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md), nhân viên giao nhận mẫu xác nhận yêu cầu sau khi tạm ứng được trả đủ hoặc khách được mua nợ, và code giữ yêu cầu ở trạng thái Draft cho tới bước đó. Nhưng kết quả của WF-01 đã là "yêu cầu thử nghiệm đã thanh toán", actor của WF-01 không có nhân viên giao nhận mẫu, còn WF-02 bắt đầu từ một yêu cầu đã thanh toán. Nhánh `fix/wf01-manual-findings` ([#613](https://github.com/SoltuneMontepre/medilab/pull/613)) xác nhận yêu cầu ngay khi đơn được xác nhận, trừ khi khách chưa trả mà không được mua nợ, và sửa rule Test request trong Sales theo đó; [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md) vẫn ghi nhân viên giao nhận mẫu xác nhận yêu cầu. Main path kiểm hành vi mới ở bước 11 và 12.

   Quyết định của product owner ngày 18-11-2026: WF-01 không có nhân viên giao nhận mẫu, và mọi nghiệp vụ về tiền nằm trong WF-01. Khi khách đã trả tạm ứng trong WF-01, hoặc được mua nợ, hệ thống xác nhận yêu cầu thử nghiệm sang Paid; khi đó khách mới được đưa mẫu cho nhân viên giao nhận mẫu kiểm tra, và từ đó bắt đầu WF-02. Đã sửa [Business flows](../../functional/business-flows.md#wf-01-order-to-confirmed-test-request), sơ đồ WF-01 trong `.drawio` và mermaid, [Sales](../../functional/ecommerce_module/features/sales.md#4-confirmation-us-s12-us-s15), [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md#2-receiving-samples-us-sd07-to-us-sd12) và [Laboratory overview](../../functional/laboratory_module/overview.md#test-request). Việc code nằm trong [WF-01 Việc code theo quyết định](wf-01-code-changes.md).
7. Khi đã cài E-commerce, nhân viên giao nhận mẫu, Sales và Head of Sales vẫn tạo được yêu cầu thử nghiệm bằng nút New, vì vai trò demo của họ có quyền tạo. [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md) ghi rằng khi có E-commerce, mọi yêu cầu đều đến từ một đơn sales đã xác nhận; việc tạo tay chỉ dành cho khi không cài E-commerce, như [Laboratory overview](../../functional/laboratory_module/overview.md) và F-15 mô tả. Yêu cầu tạo tay không có đơn, nên bước kiểm tiền cho qua và yêu cầu sang Paid mà không cần tạm ứng, vượt qua phần tiền mà quyết định ở phát hiện 6 đặt trong WF-01.

   Quyết định của product owner ngày 18-11-2026: khi đã cài E-commerce, danh sách yêu cầu thử nghiệm không có nút New và việc tạo yêu cầu không gắn với đơn bị từ chối với mọi vai trò; khách mang mẫu tới thì đi qua sales trước, theo WF-01-A1. Khi không cài E-commerce, nhân viên giao nhận mẫu vẫn tạo và xác nhận yêu cầu trực tiếp như F-15. Đã sửa Business flows (WF-02), [Sample delivery staff](../../functional/laboratory_module/features/sample-delivery-staff.md#2-receiving-samples-us-sd07-to-us-sd12), [Laboratory overview](../../functional/laboratory_module/overview.md#test-request) và câu hỏi "Test requests without E-commerce" trong `questions/laboratory.md`; TC-F15-01 được ghi vào [Thay đổi cho BM04](readme.md#thay-đổi-cho-bm04). Việc code nằm trong [WF-01 Việc code theo quyết định](wf-01-code-changes.md).
8. Trưởng phòng kinh doanh gửi được báo giá không kèm tạm ứng cho bất kỳ khách nào; code chỉ kiểm người gửi, không kiểm khách có được mua nợ không. Với khách không được mua nợ, đơn như vậy không có tạm ứng nào để chờ, nên theo quyết định ở phát hiện 3, yêu cầu thử nghiệm sẽ sang Paid và mẫu được thử khi khách chưa trả đồng nào.

   Quyết định của product owner ngày 19-11-2026: báo giá không kèm tạm ứng chỉ gửi được cho khách được mua nợ, kể cả khi Trưởng phòng kinh doanh gửi; muốn cho khách trả sau thì bật cờ mua nợ cho khách. Đã sửa rule Manager shortcut và Confirm trong [Sales](../../functional/ecommerce_module/features/sales.md), acceptance criteria của WF-01 trong Business flows, và các spec Payments, Payment requests. Việc code nằm trong [WF-01 Việc code theo quyết định](wf-01-code-changes.md).

## Chạy tay

Đăng nhập vào địa chỉ của bản demo local bằng mật khẩu demo. Mỗi tài khoản dùng một browser profile hoặc cửa sổ ẩn danh riêng:

| Tài khoản | Vai trò |
| --- | --- |
| `demo.customer` | Khách hàng của Công ty TNHH Nước Uống Sạch, trên portal |
| `demo.sales` | Nhân viên kinh doanh Nguyen Thi Thu; giao diện tiếng Việt |
| `demo.accountant` | Kế toán |
| `demo.head_of_sales` | Trưởng phòng kinh doanh |
| `demo.sample_delivery_staff` | Nhân viên giao nhận mẫu; chỉ xem yêu cầu thử nghiệm, không tạo hay xác nhận |
| `demo.administrator` | Quản trị viên, chạy tác vụ định kỳ ở E2 |

Ghi Đạt, Không đạt hoặc Bị chặn vào cột Kết quả; ghi vào cột Ghi chú điểm khác biệt và tên các bản ghi. Khi một bước kiểm tiêu chí của một tính năng, đối chiếu với text tiêu chí trong [danh sách tính năng](../feature-list/readme.md), là text của BM04 v1.1, không đối chiếu với checklist của issue [#152](https://github.com/SoltuneMontepre/medilab/issues/152).

### Main path

Đơn hàng dùng cho cả đợt kiểm chứng có hai mẫu: nước đóng chai để thử Lead (Pb), do phòng thí nghiệm tự thử, và bắp cải để thử Chlorpyrifos. Chlorpyrifos có một cách thử tại chỗ và một cách thử gửi thầu phụ cùng phương pháp thử, nên WF-05 có thể gửi thầu phụ mẫu này. Đơn được thanh toán bằng chuyển khoản như mục [Môi trường](readme.md#môi-trường) đã nêu, nên các bước 8 đến 10 cũng chạy luôn A4.

| Bước | Tài khoản | Thao tác | Kết quả mong đợi | Kết quả | Ghi chú |
| ---: | --- | --- | --- | --- | --- |
| 1 | demo.customer | Mở `/catalog`; nếu giỏ còn dòng cũ thì xóa trước. Thêm Lead (Pb) và Chlorpyrifos vào giỏ, rồi trong giỏ chọn Bottled water cho Lead (Pb) và Cabbage cho Chlorpyrifos. | Mỗi dòng tự điền cách thử mặc định, hiện bằng tên phương pháp thử; không nêu tên thầu phụ nào. Cách thử mặc định của cả hai là cách thử tại chỗ. | | |
| 2 | demo.customer | Gửi giỏ hàng. | Hiện "Order submitted" kèm số đơn, đơn nằm trong hàng đợi của kinh doanh. | | Đơn: |
| 3 | demo.sales | Mở `/odoo/unclaimed-orders`, tìm đơn và nhận đơn. | Đơn rời hàng đợi; Nguyen Thi Thu là người nhận đơn. | | |
| 4 | demo.sales | Mở đơn, không thêm mẫu bằng tay. Xem các dòng đơn và tab nhu cầu lấy mẫu dự kiến. | Mỗi dòng mang loại mẫu khách đã chọn; tab nhu cầu lấy mẫu dự kiến hiện số mẫu, chai/lọ và lượng mẫu mà các phương pháp thử cần. | | |
| 5 | demo.sales | Cho dòng Lead (Pb) chiết khấu 5%. | Dòng hiện 5%; không có chiết khấu theo số tiền cố định. | | |
| 6 | demo.sales | Ở tab thanh toán chọn chuyển khoản và toàn bộ số tiền, rồi gửi báo giá. | Mỗi dòng chưa có mẫu được gắn một mẫu đúng loại mẫu của nó: một mẫu Bottled water, một mẫu Cabbage; trạng thái mẫu vật lý để trống. Báo giá đã gửi; có đúng một hóa đơn tạm ứng; có thể tạo phiên bản sửa đổi; email báo cho khách nằm trong hàng đợi email. | | Mẫu, hóa đơn: |
| 7 | demo.customer | Mở đơn và báo giá trên portal. | Hiện các dòng, chiết khấu, VAT, nhu cầu lấy mẫu dự kiến, ngày khách yêu cầu và ngày hẹn trả kết quả; không có tên thầu phụ và không có hạn nội bộ. | | |
| 8 | demo.customer | Mở hóa đơn tạm ứng, chọn Bank transfer và toàn bộ số tiền. | Trang hiện tài khoản ngân hàng của phòng thí nghiệm và nội dung chuyển khoản là số hóa đơn; khoản chuyển khoản ở trạng thái chờ xác nhận; hóa đơn chưa được tính là đã thanh toán. Không còn hộp thoại Pay Now của Odoo. | | |
| 9 | demo.sales | Mở đơn và tìm cách ghi nhận một khoản chuyển khoản, có số tiền, ngày và hình thức. Không ghi nhận khoản thứ hai. | Đơn hiện số tiền đang chờ xác nhận. Theo A4: nhân viên kinh doanh ghi nhận được khoản tiền mặt hoặc chuyển khoản, khoản đó ở trạng thái chờ. | | |
| 10 | demo.accountant | Mở nhiệm vụ Payment confirmation của khoản đó trong hàng đợi của kế toán, mở khoản thanh toán và bấm Confirm. | Hóa đơn đã thanh toán; báo giá được chấp nhận; đơn hiện đã thanh toán; nhiệm vụ Payment confirmation xong. | | |
| 11 | demo.sales | Mở đơn và bấm Confirm order. | Đơn được xác nhận; yêu cầu thử nghiệm được tạo với hai mẫu, các chỉ tiêu của mẫu và nhu cầu lấy mẫu dự kiến của báo giá, và được xác nhận ngay vì tạm ứng đã trả đủ. | | Yêu cầu thử nghiệm: |
| 12 | demo.sample_delivery_staff | Mở `/odoo/test-requests` và mở yêu cầu thử nghiệm của đơn. | Danh sách không có nút New. Yêu cầu đã ở trạng thái Paid và form không có nút Confirm. | | |
| 13 | demo.sales | Sửa giá của một dòng của đơn rồi lưu. | Bị từ chối: nội dung chỉ đổi qua báo giá sửa đổi. | | |
| 14 | demo.sales | Xem các nút của đơn; không bấm. | Có nút Start sample collection. Bấm nút sẽ mở hộp thoại hẹn ngày giờ và địa điểm; việc đó để WF-02 làm tiếp. | | |

### E1 Báo giá bị từ chối

Bắt đầu bằng một đơn mới cho Công ty TNHH Nước Uống Sạch, Lead (Pb) trên nước đóng chai, do demo.sales gửi báo giá kèm tạm ứng chuyển khoản như bước 1 đến 6 của main path.

| Bước | Tài khoản | Thao tác | Kết quả mong đợi | Kết quả | Ghi chú |
| ---: | --- | --- | --- | --- | --- |
| 1 | demo.customer | Mở báo giá và từ chối kèm lý do. | Báo giá hiện đã bị từ chối, kèm lý do; hóa đơn tạm ứng chưa thanh toán của nó bị hủy. | | Đơn: |
| 2 | demo.sales | Mở đơn. | Nhân viên kinh doanh được báo việc từ chối và thấy lý do. | | |
| 3 | demo.sales | Tạo phiên bản sửa đổi, đổi chiết khấu và gửi phiên bản mới. | Phiên bản 2 được gửi; phiên bản 1 bị thay thế và chỉ đọc. | | |
| 4 | demo.sales | Thử gửi phiên bản 1 từ tab các phiên bản. | Bị từ chối. | | |
| 5 | demo.customer | Mở báo giá. | Khách thấy danh sách phiên bản và phiên bản 2. | | |
| 6 | demo.customer, demo.accountant | Khách trả tạm ứng của phiên bản 2 bằng chuyển khoản; kế toán xác nhận. | Phiên bản 2 được chấp nhận; phiên bản 1 vẫn ở trạng thái bị thay thế. | | |

### E2 Báo giá quá hạn

Bắt đầu bằng một đơn mới như E1, báo giá đã được gửi.

| Bước | Tài khoản | Thao tác | Kết quả mong đợi | Kết quả | Ghi chú |
| ---: | --- | --- | --- | --- | --- |
| 1 | demo.sales | Đặt hạn thanh toán là hôm qua rồi lưu. | Lưu được; nếu không cho chọn ngày trong quá khứ thì ghi lại và chờ một hạn thật sự trôi qua. | | Đơn: |
| 2 | demo.administrator, bật developer mode | Vào Settings, Technical, Scheduled Actions, mở tác vụ Flag expired quotations và bấm Run Manually. | Báo giá của đơn bị đánh dấu hết hạn; đơn không bị hủy. | | |
| 3 | demo.sales | Đặt hạn thanh toán vào tháng sau rồi lưu. | Cờ hết hạn được gỡ; hóa đơn tạm ứng đến hạn vào ngày hạn mới. | | |
| 4 | demo.customer, demo.accountant | Khách trả tạm ứng bằng chuyển khoản; kế toán xác nhận. | Báo giá được chấp nhận trong hạn đã gia hạn. | | |

### E3 Báo giá bị Trưởng phòng kinh doanh từ chối

Bị chặn: ngưỡng duyệt báo giá và chốt chặn khi gửi chưa được xây (phát hiện 1). Lượt chạy chờ [#414](https://github.com/SoltuneMontepre/medilab/issues/414).

## Tài liệu liên quan

- [Kiểm chứng luồng chính](readme.md)
- [Business flows](../../functional/business-flows.md#wf-01-order-to-confirmed-test-request)
- [Sales](../../functional/ecommerce_module/features/sales.md)
- [Customer](../../functional/ecommerce_module/features/customer.md)
- [Accountant](../../functional/ecommerce_module/features/accountant.md)
