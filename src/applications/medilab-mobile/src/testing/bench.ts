import type { Result, SampleTest } from "../api";

const NO_ACTIONS = { edit: false, sign: false, reject: false };

/** The lead result demo.tester entered, a draft they may change and send. */
export function result(values: Partial<Result> = {}): Result {
  return {
    id: 31,
    code: "PTN.2026.0042",
    parameter: "Chì (Pb)",
    value_display: "0,008 mg/L",
    unit: "mg/L",
    status: "none",
    entered_by: "Nguyễn Văn An",
    entered_at: "2026-11-13T03:00:00+00:00",
    warned: false,
    sample_test_id: 4,
    way: "Chì (Pb) – TCVN 7602:2007",
    value: 0.008,
    value_text: "",
    decimals: 3,
    value_suggestion: "",
    comparison_requested: true,
    conclusion: "pass",
    conclusion_label: "Đạt",
    limit: "≤ 0,010 mg/L",
    limit_missing: false,
    status_label: "Nháp",
    warnings: [],
    rejection_reason: "",
    actions: { ...NO_ACTIONS, edit: true, sign: true },
    ...values,
  };
}

/** The result once sent: it waits for the head of department, so its tester can only read it. */
export function sent(values: Partial<Result> = {}): Result {
  return result({ status: "requested", status_label: "Chờ duyệt", actions: NO_ACTIONS, ...values });
}

/** The lead test of the sample, in testing for demo.tester, compared with QCVN 6-1:2010/BYT. */
export function sampleTest(values: Partial<SampleTest> = {}): SampleTest {
  return {
    id: 4,
    code: "PTN.2026.0042",
    parameter: "Chì (Pb)",
    way: "Chì (Pb) – TCVN 7602:2007",
    due_date: "2026-11-20T10:00:00+00:00",
    status: "Đang thử nghiệm",
    unit: "mg/L",
    decimals: 3,
    regulation: "QCVN 6-1:2010/BYT",
    comparison_requested: true,
    can_enter_result: true,
    result: null,
    ...values,
  };
}
