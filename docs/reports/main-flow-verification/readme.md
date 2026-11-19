# Kiểm chứng luồng chính

Kiểm chứng các luồng chính từ WF-01 Order to confirmed test request đến WF-06 Report signing, release and delivery, bằng chạy tay và bằng browser test, so với điều tài liệu yêu cầu và độ phủ tài liệu đang công bố.

## Phạm vi

- Luồng: WF-01 đến WF-06 trong [Business flows](../../functional/business-flows.md). Các luồng phụ SF-01 đến SF-11 không thuộc đợt kiểm chứng này.
- Chạy tay: main path và mọi exception của từng luồng, tổng cộng 30 lượt.
- Đối chiếu: mọi path của sáu luồng, tổng cộng 59 path, với browser test và [BM04 v1.1](../BM04_hoang/SWP490_GFA26SE153_R2_Commitment_v1.1.pdf).
- Tính năng: những tính năng mà cột Workflow của [danh sách tính năng](../feature-list/readme.md) giao cho WF-01 đến WF-06. Mỗi tính năng thuộc đúng một flow sở hữu nó.
- Medilab Mobile, Medilab Sync và chỉnh sửa trực tuyến bằng ONLYOFFICE không chạy tay; chỉ đối chiếu các browser spec của chúng.

## Nguồn chuẩn

Khi hai nguồn mâu thuẫn, nguồn đứng trên là chuẩn. Mâu thuẫn có dính tới các mức 1 đến 4 được đưa cho product owner quyết và ghi ở mục [Quyết định](#quyết-định).

1. Quyết định của product owner.
2. [Proposal capstone](../proposal/FA26SE294_DESIGN_AND_DEVELOPMENT_OF_A_LABORATORY_I_hoangnt2.docx).
3. Hành vi nghiệp vụ: [Business flows](../../functional/business-flows.md), tài liệu tính năng theo actor của từng phân hệ trong [Functional](../../functional/index.md) và [Business rules](../../business/readme.md). Luồng và tính năng mâu thuẫn nhau thì đưa product owner quyết.
4. BM04 v1.1 và [danh sách tính năng](../feature-list/readme.md), nơi định nghĩa F-xx và ID test case `TC-Fnn-01` đến `-03`. Chúng chỉ làm chuẩn cho phạm vi cam kết, flow sở hữu tính năng và tiêu chí đạt, không làm chuẩn cho hành vi.
5. [Specs](../../specs/readme.md).
6. Tài liệu phái sinh: [activity diagram](../activity-diagram/readme.md), [use case diagram](../use-case-diagram/readme.md) và [WF-03 test plan](../wf-03-test-plan.md). Chúng phải khớp với mức 3.
7. [Bố cục browser test](../../../src/tests/cypress/e2e/README.md), tiêu đề test và spec. Đây là thứ được kiểm, không bao giờ là chuẩn.

## Phương pháp

Mỗi luồng có một file, mỗi path trong tài liệu là một dòng:

| Cột        | Nội dung                                                                    |
| ---------- | --------------------------------------------------------------------------- |
| Path       | ID path và tóm tắt lấy từ Business flows                                    |
| Tài liệu   | Điều path yêu cầu, kèm acceptance criteria                                  |
| BM04       | Demo scenario (`DS-…`) và ID test case (`TC-F…`) của path                   |
| Browser test | Tiêu đề test, spec và kết quả                                             |
| Kết luận   | Browser test có kiểm đúng điều tài liệu yêu cầu không                       |
| Chạy tay   | Kết quả chạy tay, cho main path và các exception                            |

| Kết luận | Nghĩa                                                                                     |
| -------- | ----------------------------------------------------------------------------------------- |
| Covered  | Test kiểm đúng hành vi đã duyệt của path.                                                 |
| Partial  | Test kiểm một phần; ghi chú nêu phần còn thiếu.                                           |
| Missing  | Không test nào kiểm path.                                                                 |
| Drift    | Test mang một ID path mà tài liệu không định nghĩa, hoặc ID đó nay chỉ một path khác.     |
| Wrong    | Test khẳng định một hành vi mà tài liệu không yêu cầu.                                    |

Main path chạy bằng một đơn hàng có hai mẫu, đi liền từ WF-01 đến WF-06. Một mẫu được phòng thí nghiệm tự thử qua WF-03 và WF-04, mẫu còn lại gửi thầu phụ qua WF-05, và cả hai cùng vào phiếu kết quả của WF-06. Mỗi luồng tiếp tục đơn đó từ chỗ luồng trước dừng lại. Một exception bắt đầu từ trạng thái luồng của nó nêu và chạy trên dữ liệu riêng.

Mỗi luồng đi qua ba bước:

1. Viết file của luồng: các dòng path, bước chạy tay cho main path và các exception, kết quả browser test và kết luận. Browser test chạy bằng `task test:e2e GREP=TC-WF0<n>`, hoặc trong Cypress App khi cần xem kỹ một path.
2. Product owner chạy tay và ghi kết quả từng bước.
3. Review lỗi và quyết định của luồng, theo hai mục bên dưới.

## Môi trường

- Bản demo local của repository, ở địa chỉ theo `MEDILAB_ODOO_PORT`, đã cài mọi phân hệ cùng demo data và đã nâng cấp theo code đang checkout. Lượt chạy tay tạo đơn hàng riêng, không dùng lại bản ghi do browser test tạo.
- Mỗi vai trò đăng nhập bằng `demo.<role>` với mật khẩu demo, trong một browser profile hoặc cửa sổ ẩn danh riêng; khách hàng đăng nhập vào portal.
- PayOS: ở local Odoo không bao giờ gọi PayOS, và bản fresh demo không truyền `PAYOS_CHECKSUM_KEY`, nên khoản thanh toán qua PayOS luôn ở trạng thái chờ. Vì vậy main path thanh toán bằng chuyển khoản; nhân viên kinh doanh ghi nhận, kế toán xác nhận, như WF-01-A4.
- Viettel Sign: chữ ký số đang tắt, nên phiếu kết quả được phát hành không có chữ ký số. Việc ký qua Viettel Sign vẫn chưa được kiểm chứng, như [Digital signing](../../specs/digital-signing.md#sandbox) đã nêu.
- Email: không có mail server gửi đi; email đã gửi được đọc trong hàng đợi email của Odoo, ở Settings, Technical, Emails khi bật developer mode.
- Production: khi sáu luồng đều đạt ở local, main path chạy thêm một lượt trên production bằng một đơn hàng mới, không reset dữ liệu. Trước lượt đó, cấu hình PayOS và Viettel Sign của production được kiểm theo tên secret; nếu không phải credential sandbox thì đơn được thanh toán bằng chuyển khoản và chữ ký số vẫn tắt.

## Tiêu chí đạt

Một luồng đạt khi:

- main path chạy tay đạt;
- mọi exception chạy tay đạt, hoặc ít nhất 80% đạt và product owner đã chấp nhận một issue cho từng exception còn lại;
- ít nhất 95% browser test của luồng đạt;
- không còn lỗi Critical hay High nào của luồng đang mở.

Kết luận Missing hay Drift không ngăn luồng đạt, nhưng path nào cũng phải có kết luận. Lỗi đã sửa được kiểm lại bằng cách chạy lại path đó bằng tay và bằng browser test.

Đợt kiểm chứng hoàn tất khi sáu luồng đạt, main path đạt trên production và product owner đã nhận danh sách [thay đổi cho BM04](#thay-đổi-cho-bm04).

## Lỗi

| Loại                                                                                         | Ghi nhận thành                                               |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Lỗi sản phẩm                                                                                 | GitHub bug issue, kèm mức độ ([Reporting a bug](../../workflows/reporting-bug.md)) |
| Lỗi test: test fail ở chỗ lẽ ra phải đạt, hoặc đạt mà không kiểm đúng điều tài liệu yêu cầu | GitHub issue riêng                                           |
| Yêu cầu còn thiếu hoặc chưa rõ                                                               | Câu hỏi trong `questions/<topic>.md`                         |

Issue chỉ được tạo sau khi product owner đã review danh sách của luồng.

## Quyết định

Quyết định của product owner được gom theo luồng. Hết mỗi luồng, một pull request áp dụng chúng ở mọi nơi path hay rule bị đổi có xuất hiện:

1. Business flows: phần chữ và sơ đồ.
2. Tài liệu tính năng theo actor.
3. Danh sách tính năng, và workbook do `feature_list.py` sinh ra từ đó.
4. Các trang `.drawio` của activity diagram, cùng SVG, PDF, zip và website build từ đó.
5. Bố cục browser test, tiêu đề test và spec.
6. WF-03 test plan, cho WF-03 và SF-10.
7. Các câu hỏi đã được trả lời trong `questions/<topic>.md`.
8. Các GitHub issue có ID test case trong mô tả.
9. Báo cáo này.

BM04 không bị sửa; những gì BM04 cần đổi được ghi ở mục [Thay đổi cho BM04](#thay-đổi-cho-bm04). Pull request đầu tiên trong số đó cũng đưa vào [quy ước tài liệu](../../conventions/documentation.md#document-format) quy tắc ID path là cố định, giống ID story.

## Các luồng

| Luồng                                       | Path | Lượt chạy tay | Trạng thái  |
| ------------------------------------------- | ---: | ------------: | ----------- |
| [WF-01 Order to confirmed test request](wf-01-order-to-test-request.md) | 9 | 4 | Đã chạy browser test; chờ chạy tay; [việc code theo quyết định](wf-01-code-changes.md) |
| [WF-02 Sample reception and handover](wf-02-sample-reception.md) | 8 | 6 | Đã chạy browser test; chờ chạy tay |
| WF-03 Testing assignment and scheduling     |    6 |             3 | Chưa bắt đầu |
| WF-04 Result entry and approval             |   17 |             7 | Chưa bắt đầu |
| WF-05 Outsourced testing                    |    8 |             5 | Chưa bắt đầu |
| WF-06 Report signing, release and delivery  |   11 |             5 | Chưa bắt đầu |
| Tổng                                        |   59 |            30 |             |

## ID path trong tiêu đề test

So sánh ID path của Business flows với ID trong tiêu đề browser test, ngày 16-11-2026. ID khớp không có nghĩa là test kiểm đúng path đó; file của từng luồng mới kết luận điều này.

| Luồng | Path trong tài liệu chưa có test | ID trong test mà Business flows không định nghĩa |
| ----- | -------------------------------- | ------------------------------------------------ |
| WF-01 | A4, E1, E2, E3                   | A6, A7                                           |
| WF-02 | không có                         | A4, A5, E6, E7                                   |
| WF-03 | A3                               | không có                                         |
| WF-04 | A3, A5, A8, E2                   | không có                                         |
| WF-05 | không có                         | A4, A5, A6                                       |
| WF-06 | A4, A6, E3                       | M2, T                                            |

Các test của WF-03 được đánh dấu `partial`; bố cục browser test ghi rõ mỗi test kiểm phần nào của path.

## ID test case của BM04 trong tiêu đề test

BM04 v1.1 cam kết ba test case cho mỗi tính năng, từ `TC-F<tính năng>-01` đến `-03`; nội dung của chúng nằm trong [danh sách tính năng](../feature-list/readme.md). Bảng chỉ đếm các tính năng bắt buộc theo flow sở hữu. Tiêu đề browser test mang các ID dưới đây; Odoo module test không mang ID nào. Test của một tính năng có thể nằm trong một test của path mà không mang ID, như bố cục browser test cho phép, nên file của từng luồng tìm các ID còn thiếu theo nội dung test kiểm.

| Luồng | ID có trong tiêu đề | Không có trong tiêu đề nào                                                                                                               |
| ----- | ------------------: | ---------------------------------------------------------------------------------------------------------------------------------------- |
| WF-01 |           10 trên 15 | TC-F04-01, TC-F05-01, TC-F09-01, TC-F09-03, TC-F10-03                                                                                    |
| WF-02 |            5 trên 12 | TC-F15-01, TC-F16-03, TC-F17-01, TC-F17-03, TC-F18-01, TC-F18-02, TC-F18-03                                                              |
| WF-03 |             5 trên 9 | TC-F23-01, TC-F23-02, TC-F24-01, TC-F25-01                                                                                               |
| WF-04 |            9 trên 24 | TC-F32-01, TC-F34-01, TC-F34-03, TC-F35-01, TC-F35-02, TC-F35-03, TC-F36-01, TC-F36-02, TC-F53-01, TC-F53-02, TC-F54-01, TC-F54-02, TC-F57-01, TC-F57-02, TC-F57-03 |
| WF-05 |             0 trên 6 | TC-F38-01, TC-F38-02, TC-F38-03, TC-F40-01, TC-F40-02, TC-F40-03                                                                         |
| WF-06 |             3 trên 9 | TC-F43-01, TC-F45-01, TC-F45-02, TC-F47-01, TC-F47-02, TC-F47-03                                                                         |

## Thay đổi cho BM04

- Bảy exception trong tài liệu chưa có demo scenario nào: WF-02-E3, WF-02-E4, WF-02-E5, WF-05-E3, WF-05-E4, WF-06-E3 và WF-06-E4.
- TC-F10-01: báo giá do Trưởng phòng kinh doanh soạn không cần duyệt, kể cả khi vượt ngưỡng.
- TC-F10-02: phần còn lại sau tạm ứng không còn phải trả trước khi thử nghiệm; nó được thu ở SF-01 và không chặn bước nào của yêu cầu thử nghiệm.
- TC-F15-01: nhân viên tạo yêu cầu thử nghiệm trực tiếp chỉ khi không cài E-commerce; khi có E-commerce, mọi yêu cầu đến từ đơn hàng.

## Tài liệu liên quan

- [Business flows](../../functional/business-flows.md)
- [Testing](../../conventions/testing.md)
- [Bố cục browser test](../../../src/tests/cypress/e2e/README.md)
- [WF-03 test plan](../wf-03-test-plan.md)
- [Review 2 commitment (BM04)](../BM04_hoang/SWP490_GFA26SE153_R2_Commitment_v1.1.pdf)
- [Danh sách tính năng](../feature-list/readme.md)
- [Reports](../readme.md)
