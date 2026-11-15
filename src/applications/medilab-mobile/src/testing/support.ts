import type { SupportRequest, SupportRequestDetail } from "../api";

// The demo request demo.sales takes and answers: the customer's question, waiting for a salesperson.
export const QUESTION = "Chúng tôi gửi mẫu nước đóng chai từ thứ Hai. Khi nào chúng tôi nhận được kết quả?";

export function supportRequest(values: Partial<SupportRequest> = {}): SupportRequest {
  return {
    id: 5,
    code: "HT.0005",
    subject: "Khi nào có kết quả mẫu nước đóng chai?",
    status: "open",
    customer: "Công ty Nước Sạch",
    order: "",
    handled_by: "",
    opened_at: "2026-11-12T02:00:00+00:00",
    ...values,
  };
}

export function supportDetail(values: Partial<SupportRequestDetail> = {}): SupportRequestDetail {
  return {
    ...supportRequest(),
    messages: [
      { id: 31, author: "Phạm Thị Hoa", body: QUESTION, date: "2026-11-12T02:00:00+00:00", from_customer: true },
    ],
    actions: { take: true, answer: true },
    ...values,
  };
}
