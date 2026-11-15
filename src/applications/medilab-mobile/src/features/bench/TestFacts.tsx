import type { SampleTest } from "../../api";
import { useSession } from "../../session";
import { Facts } from "../shared/Facts";
import { formatMoment } from "../tasks/taskText";

/** A sample test at the bench: its lab code, parameter, way of testing, due date, unit and regulation. */
export function TestFacts({ test }: Readonly<{ test: SampleTest }>) {
  const { language } = useSession();
  return (
    <Facts
      facts={[
        ["test.code", test.code],
        ["test.parameter", test.parameter],
        ["test.way", test.way],
        ["test.dueDate", test.due_date ? formatMoment(test.due_date, language) : ""],
        ["test.status", test.status],
        ["test.unit", test.unit],
        ["test.regulation", test.regulation],
      ]}
    />
  );
}
