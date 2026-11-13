import type { Sample } from "../api";
import { task } from "./home";

// The Lead (Pb) testing task of Chemistry waiting on the sample.
export const LEAD = task({ id: 21, name: "PTN.2026.0042: Lead (Pb)", status: "open", assignee: "", action: "test" });

/** A sample as demo.tester sees it: handed over to Chemistry and not received, without its customer. */
export function sample(values: Partial<Sample> = {}): Sample {
  return {
    id: 42,
    code: "PTN.2026.0042",
    status: "Đã nhận",
    sample_type: "Nước uống đóng chai",
    physical_state: "Lỏng",
    form: "Chai nguyên",
    container: "Chai PET 500 mL",
    received_at: "2026-11-12T02:00:00+00:00",
    storage_location: "Tủ lạnh 1, ngăn A",
    sampling_location: "",
    note: "",
    customer: null,
    customer_sample_name: null,
    handover: { department: "Hoá", received_at: null, received_by: "", can_receive: true },
    tasks: [LEAD],
    ...values,
  };
}
