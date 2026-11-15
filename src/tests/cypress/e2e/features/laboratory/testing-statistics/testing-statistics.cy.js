import { callAs } from "../../../../support/odoo";

const HEAD = "demo.head_of_department";
const LAB_HEAD = "demo.lab_head";
const MEASURES = ["completed:sum", "on_time:avg", "turnaround_days:avg", "overdue:sum", "retests:sum", "bookings:sum"];

// The first and last day of last month, which the demo data fills for Chemistry and Microbiology.
function lastMonth() {
  const now = new Date();
  const first = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, 1));
  const last = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 0));
  return [first, last].map((day) => day.toISOString().slice(0, 10));
}

// The measures of last month by department, as the login reads them, keyed by department name.
function statistics(login, domain = []) {
  const [from, to] = lastMonth();
  return callAs(login, "medilab.testing.statistic", "formatted_read_group", [domain, ["department_id"], MEASURES], {
    context: { testing_statistics_from: from, testing_statistics_to: to },
  }).then((groups) => Object.fromEntries(groups.map((group) => [group.department_id[1], group])));
}

// Opens the statistics of the current month, which the page shows without a chosen period.
function openStatistics() {
  cy.visit("/odoo/testing-statistics");
  cy.get(".o_pivot").should("be.visible");
}

describe("Testing statistics", () => {
  it("TC-F440-1 a head of department sees only the statistics of their department", () => {
    cy.signInAs("head_of_department");
    openStatistics();
    cy.get(".o_pivot").should("contain.text", "Chemistry").and("not.contain.text", "Microbiology");

    statistics(HEAD).then((byDepartment) => {
      expect(Object.keys(byDepartment), "departments the head reads").to.deep.equal(["Chemistry"]);
      expect(byDepartment.Chemistry["completed:sum"], "approved last month").to.be.at.least(1);
      expect(byDepartment.Chemistry["overdue:sum"], "overdue at the end of last month").to.be.at.least(1);
    });
    statistics(HEAD, [["department_id.name", "=", "Microbiology"]]).should("deep.equal", {});
  });

  it("TC-F440-2 the Lab Head compares departments, and a department filter gives what its head sees", () => {
    cy.signInAs("lab_head");
    openStatistics();
    cy.get(".o_pivot").should("contain.text", "Chemistry").and("contain.text", "Microbiology");

    statistics(LAB_HEAD).then((byDepartment) => {
      expect(byDepartment, "departments the Lab Head reads").to.include.keys("Chemistry", "Microbiology");
      expect(byDepartment.Microbiology["completed:sum"], "approved late last month").to.be.at.least(1);
      expect(byDepartment.Microbiology["on_time:avg"], "share approved on time").to.be.below(100);
    });
    statistics(LAB_HEAD, [["department_id.name", "=", "Chemistry"]]).then((filtered) => statistics(HEAD).should("deep.equal", filtered));
  });
});
