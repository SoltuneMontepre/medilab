import type { HandoverRecord } from "../api";

/** The demo draft handover record: one cabbage handed over short by Trần Văn Bình, which demo.sample_delivery_staff
 * have the customer sign. */
export function draftRecord(values: Partial<HandoverRecord> = {}): HandoverRecord {
  return {
    id: 12,
    code: "BBGN.2026.0004",
    request: "YC.2026.0007",
    handed_over_at: "2026-11-17T02:00:00+00:00",
    handed_over_by: "Trần Văn Bình",
    status: "draft",
    signed_at: null,
    received_by: "Lê Thị Lan",
    signed_device: "",
    samples: [
      {
        code: "PTN.2026.0051",
        sample_type: "Bắp cải",
        customer_sample_name: "Bắp cải lô A",
        expected_count: 1,
        actual_count: 1,
        quantity: "1 small head",
        excess_material: "",
        condition: "Không đủ",
        condition_note: "Below the minimum amount for the sample type.",
      },
    ],
    can_sign: true,
    ...values,
  };
}

/** The record once the customer signed it on the phone: it is only shown. */
export function signedRecord(values: Partial<HandoverRecord> = {}): HandoverRecord {
  return draftRecord({
    status: "signed",
    signed_at: "2026-11-17T02:10:00+00:00",
    signed_device: "Pixel 8",
    can_sign: false,
    ...values,
  });
}
