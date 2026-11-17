import { choose, save, search } from "../../../support/form";
import { callAs, callRefused } from "../../../support/odoo";
import { ADMIN, TESTER, approve, bookingsOf, inDays, machineFixture, notified, odooTime, release, testsOf, typed } from "./setup";

const NO_MACHINE = "No machine can finish";

// The administrator opens the machine's form.
function openMachine(machine) {
  cy.visit(`/odoo/machines/${machine}`);
  cy.get(".o_form_view .o_field_widget[name=code]").should("be.visible");
}

// The administrator picks a status in the machine's status bar; it stays unsaved until the form is saved.
function pickStatus(label) {
  cy.contains(".o_statusbar_status button", label).click();
  cy.get(".o_statusbar_status .o_arrow_button_current").should("contain", label);
}

// The administrator sets the machine's status from its form and saves it.
function setStatus(machine, label) {
  openMachine(machine);
  pickStatus(label);
  save();
}

// The administrator adds a line to the service history of the open machine and saves it.
function addService(kind, { date, due } = {}) {
  // Odoo opens the new line once it has filled in its defaults; a field chosen before that is lost.
  cy.intercept("POST", "/web/dataset/call_kw/medilab.machine.service/onchange").as("newLine");
  cy.get(".o_field_x2many_list_row_add button").click();
  cy.wait("@newLine");
  choose("kind", kind);
  if (date) cy.get(".o_selected_row .o_field_widget[name=service_date] input").type(typed(date)).blur();
  if (due) cy.get(".o_selected_row .o_field_widget[name=next_due_date] input").type(typed(due)).blur();
  save();
  cy.contains(".o_data_row", kind).should("be.visible");
}

// The administrator sets how many days pass between two maintenance visits of the open machine, and saves it.
function setMaintenanceInterval(days) {
  cy.get(".o_field_widget[name=maintenance_interval_days] input").clear().type(`${days}`);
  save();
}

// The booking's form, as the signed-in user sees it.
function openBooking(booking) {
  cy.visit(`/odoo/machine-schedule/${booking}`);
  cy.get(".o_form_view .o_field_widget[name=machine_id]").should("be.visible");
}

// The sample test's form, as the signed-in user sees it.
function openTest(test) {
  cy.visit(`/odoo/medilab.sample.test/${test}`);
  cy.get(".o_form_view .o_field_widget[name=status]").should("be.visible");
}

// The lines of a booking's machine warning.
function warningLines(booking) {
  return callAs(ADMIN, "medilab.machine.booking", "read", [[booking], ["machine_warning"]]).then(([read]) =>
    (read.machine_warning || "").split("\n").filter(Boolean),
  );
}

describe("SF-05 Machine calibration and unavailability", () => {
  let fixture;
  beforeEach(() => {
    fixture = undefined;
    cy.viewport(1440, 900);
  });
  afterEach(() => release(fixture));

  it("TC-SF05-M replans not-started work on another fit machine for its way when the administrator takes a machine out of use, and brings the machine back only after a calibration dated after its repair", () => {
    machineFixture({ tests: 3, book: 2, machines: 2 }, (created) => (fixture = created)).then(() => {
      const [machineA, machineB] = fixture.machines;
      bookingsOf(fixture).then((before) => {
        expect(before.map((booking) => booking.status)).to.deep.equal(["scheduled", "scheduled", "proposed"]);
        expect(before.slice(0, 2).map((booking) => booking.machine_id[0])).to.deep.equal([machineA, machineA]);
      });

      cy.signInAs("administrator");
      setStatus(machineA, "Under repair");
      bookingsOf(fixture).should((after) => {
        expect(after, "the bookings of the three tests").to.have.length(3);
        after.forEach((booking) => {
          expect(booking.status, "back in the plan").to.equal("proposed");
          expect(booking.machine_id[0], "on the other machine").to.equal(machineB);
          expect(booking.method_id[0], "by the same method").to.equal(fixture.method);
          expect(booking.starts_at, "with a slot").to.be.a("string");
        });
      });
      testsOf(fixture, ["parameter_method_id", "at_risk", "outsourcing_suggested"]).then((tests) => {
        tests.forEach((test) => {
          expect(test.outsourcing_suggested).to.equal(false);
          expect(test.at_risk).to.equal(false);
        });
        // The two booked tests keep their agreed way.
        tests.slice(0, 2).forEach((test) => expect(test.parameter_method_id[0], "the agreed way").to.equal(fixture.way));
      });

      bookingsOf(fixture).then(([replanned]) => {
        cy.signInAs("head_of_department");
        openBooking(replanned.id);
        cy.get(".o_statusbar_status .o_arrow_button_current").should("contain", "Proposed");
        cy.get(".o_field_widget[name=machine_id]").should("contain", "-B");
        cy.get('.o_statusbar_buttons button[name="action_approve"]').should("be.visible");
      });

      // The repair is recorded, and putting the machine back in use is refused until a calibration or maintenance
      // is recorded after it.
      cy.signInAs("administrator");
      openMachine(machineA);
      addService("Repair", { date: inDays(0) });
      cy.expectRefusal({
        read: () => cy.readRecord({ model: "medilab.machine", id: machineA }, ["status", "write_date"]),
        action: () => {
          pickStatus("In use");
          cy.get(".o_form_button_save").click();
        },
        message: "done after its repair",
      });
      cy.contains(".o_error_dialog .modal-footer button", "Close").click();
      cy.reload();
      cy.get(".o_statusbar_status .o_arrow_button_current").should("contain", "Under repair");
      addService("Calibration", { date: inDays(0), due: inDays(365) });
      pickStatus("In use");
      save();

      // The plan can use the machine again.
      bookingsOf(fixture).should((after) => {
        expect(after.map((booking) => booking.machine_id[0])).to.include(machineA);
      });
    });
  });

  it("TC-SF05-A1 gives a machine without valid calibration no booking until valid calibration is recorded, and returns a booking that would end after the calibration to the plan", () => {
    machineFixture({ tests: 1, book: 0, calibrated: false }, (created) => (fixture = created)).then(() => {
      const [test] = fixture.tests;
      cy.signInAs("head_of_department");
      openTest(test);
      cy.get(".o_form_view .alert.alert-warning").should("contain", NO_MACHINE);
      cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("not.exist");
      callRefused("medilab.sample.test", "action_approve_booking", [[test]]).should("contain", NO_MACHINE);
      bookingsOf(fixture).then(([booking]) => {
        expect(booking.status, "queued for the plan").to.equal("proposed");
        expect(booking.starts_at, "without a slot").to.equal(false);
      });

      // A calibration that has already ended does not make the machine fit either.
      cy.signInAs("administrator");
      openMachine(fixture.machine);
      addService("Calibration", { date: inDays(0), due: inDays(-1) });
      callAs(TESTER, "medilab.sample.test", "read", [[test], ["outsourcing_suggested", "recommended_start"]]).then(([read]) => {
        expect(read.outsourcing_suggested).to.equal(true);
        expect(read.recommended_start).to.equal(false);
      });

      addService("Calibration", { date: inDays(0), due: inDays(365) });
      cy.signInAs("head_of_department");
      openTest(test);
      cy.get(".o_form_view .alert.alert-warning").should("not.exist");
      cy.intercept("POST", "**/medilab.sample.test/action_approve_booking").as("scheduled");
      cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("be.visible").and("be.enabled").click();
      cy.wait("@scheduled").its("response.body.error").should("not.exist");
      bookingsOf(fixture).then(([booking]) => {
        expect(booking.status).to.equal("scheduled");
        expect(booking.machine_id[0]).to.equal(fixture.machine);
      });

      // A calibration that ends before the booking returns it to the plan, still without a slot.
      cy.signInAs("administrator");
      openMachine(fixture.machine);
      addService("Calibration", { date: inDays(0), due: inDays(-1) });
      bookingsOf(fixture).should(([booking]) => {
        expect(booking.status).to.equal("proposed");
        expect(booking.starts_at).to.equal(false);
      });
    });
  });

  it("TC-SF05-A2 warns within the calibration, maintenance and repair windows on their own and never lets a warning bypass a booking block", () => {
    machineFixture({ tests: 2, book: 1 }, (created) => (fixture = created)).then(() => {
      const [, waiting] = fixture.tests;
      const [booking] = fixture.bookings;
      cy.signInAs("tester");
      openBooking(booking);
      cy.get(".o_form_view .alert-warning").should("not.exist");

      // The calibration ends within the window after the booking.
      cy.signInAs("administrator");
      openMachine(fixture.machine);
      addService("Calibration", { date: inDays(0), due: inDays(5) });
      warningLines(booking).should((lines) => {
        expect(lines).to.have.length(1);
        expect(lines[0]).to.contain("calibration").and.contain("ends on");
      });

      // The maintenance falls due within its own window.
      setMaintenanceInterval(30);
      addService("Maintenance", { date: inDays(-27) });
      warningLines(booking).should((lines) => {
        expect(lines).to.have.length(2);
        expect(lines[1]).to.contain("maintenance").and.contain("is due on");
      });

      // The machine was repaired shortly before.
      addService("Repair", { date: inDays(-1) });
      warningLines(booking).should((lines) => {
        expect(lines).to.have.length(3);
        expect(lines[2]).to.contain("was repaired on");
      });
      cy.signInAs("tester");
      openBooking(booking);
      cy.get(".o_form_view .alert-warning").should("contain", "calibration").and("contain", "maintenance").and("contain", "was repaired on");

      // The maintenance becomes overdue: the warnings stay, and no new booking is made.
      cy.signInAs("administrator");
      openMachine(fixture.machine);
      setMaintenanceInterval(5);
      callRefused("medilab.sample.test", "action_approve_booking", [[waiting]]).should("contain", NO_MACHINE);
      warningLines(booking).should((lines) => {
        expect(lines.join("\n")).to.contain("calibration").and.contain("maintenance").and.contain("was repaired on");
      });
      bookingsOf(fixture).then((open) => {
        expect(open.filter((read) => read.status === "scheduled")).to.have.length(1);
      });
    });
  });

  it("TC-SF05-A3 reserves a planned maintenance's downtime and blocks new bookings while maintenance is overdue until its completion is recorded", () => {
    machineFixture({ tests: 3, book: 2 }, (created) => (fixture = created)).then(() => {
      bookingsOf(fixture).then((booked) => {
        const first = booked[0].starts_at;
        const last = booked[1].ends_at;
        const downtimeStart = odooTime(Date.parse(`${first}Z`) - 30 * 60000);
        const downtimeEnd = odooTime(Date.parse(`${last}Z`) + 30 * 60000);
        callAs(ADMIN, "medilab.machine.service", "create", [
          {
            machine_id: fixture.machine,
            kind: "maintenance",
            downtime_start: downtimeStart,
            downtime_end: downtimeEnd,
            note: "Quarterly maintenance.",
          },
        ]);
        cy.signInAs("administrator");
        openMachine(fixture.machine);
        cy.get(".o_data_row").should("contain", "Maintenance");

        // The bookings that overlapped the downtime are back in the plan, after it.
        bookingsOf(fixture).should((after) => {
          expect(after).to.have.length(3);
          after.forEach((booking) => {
            expect(booking.status).to.equal("proposed");
            expect(booking.starts_at >= downtimeEnd, `${booking.starts_at} is after the downtime`).to.equal(true);
          });
        });

        // The maintenance falls overdue: the plan's proposals cannot be accepted.
        setMaintenanceInterval(30);
        addService("Maintenance", { date: inDays(-100) });
        callRefused("medilab.sample.test", "action_approve_booking", [[fixture.tests[0]]]).should("contain", NO_MACHINE);
        bookingsOf(fixture).then((after) => {
          expect(after.filter((booking) => booking.status === "scheduled")).to.be.empty;
        });

        // Recording its completion lifts the block, and the booking keeps clear of the downtime.
        addService("Maintenance", { date: inDays(0) });
        approve(fixture, fixture.tests[0]).then((booking) =>
          callAs(ADMIN, "medilab.machine.booking", "read", [[booking], ["starts_at"]]).then(([read]) => {
            expect(read.starts_at >= downtimeEnd, `${read.starts_at} is after the downtime`).to.equal(true);
          }),
        );
      });
    });
  });

  it("TC-SF05-E1 keeps work queued without a slot when no other machine runs its way, tells the tester and head, and leaves the way unchanged", () => {
    machineFixture({ tests: 2, book: 2 }, (created) => (fixture = created)).then(() => {
      cy.signInAs("administrator");
      setStatus(fixture.machine, "Under repair");

      bookingsOf(fixture).should((after) => {
        expect(after, "the bookings stay in the plan").to.have.length(2);
        after.forEach((booking) => {
          expect(booking.status).to.equal("proposed");
          expect(booking.starts_at, "without a slot").to.equal(false);
        });
      });
      testsOf(fixture, ["status", "parameter_method_id", "outsourcing_suggested", "at_risk"]).then((tests) =>
        tests.forEach((test) => {
          expect(test.status, "still waiting for a slot").to.equal("assigned");
          expect(test.parameter_method_id[0], "the agreed way is not replaced").to.equal(fixture.way);
          expect(test.outsourcing_suggested).to.equal(true);
          expect(test.at_risk).to.equal(true);
        }),
      );
      notified("medilab.sample.test", fixture.tests, "sample_test.at_risk").should("deep.equal", ["demo.head_of_department", "demo.tester"]);

      ["tester", "head_of_department"].forEach((role) => {
        cy.signInAs(role);
        openTest(fixture.tests[0]);
        cy.get(".o_form_view .alert.alert-warning").should("contain", NO_MACHINE);
        cy.get(".o_form_view .alert.alert-danger").should("contain", "at risk");
        cy.get(".o_statusbar_buttons button[name=action_approve_booking]").should("not.exist");
      });
      callRefused("medilab.sample.test", "action_approve_booking", [[fixture.tests[0]]]).should("contain", NO_MACHINE);
    });
  });

  it("TC-SF05-E2 keeps the data of a run a machine failure interrupts, lets the head of department assess each attempt, and refuses the tester", () => {
    machineFixture({ tests: 3, book: 3, capacity: 3 }, (created) => (fixture = created)).then(() => {
      cy.signInAs("tester");
      fixture.bookings.forEach((booking) => {
        openBooking(booking);
        cy.get('.o_statusbar_buttons button[name="action_start"]').click();
        cy.get(".o_statusbar_status .o_arrow_button_current").should("contain", "In progress");
      });
      bookingsOf(fixture).then((running) => {
        expect(new Set(running.map((booking) => booking.starts_at)).size, "one shared run").to.equal(1);
        expect(running.map((booking) => booking.status)).to.deep.equal(["in_progress", "in_progress", "in_progress"]);
      });

      cy.signInAs("administrator");
      setStatus(fixture.machine, "Under repair");
      bookingsOf(fixture).then((ended) => {
        expect(
          ended.map((booking) => booking.status),
          "the failure ended every booking of the run",
        ).to.deep.equal(["done", "done", "done"]);
      });
      callAs(ADMIN, "medilab.test.result", "search_read", [[["sample_test_id", "in", fixture.tests]]], {
        fields: ["sample_test_id", "booking_id", "is_interrupted", "interruption_assessment"],
        order: "id",
      }).then((results) => {
        expect(results, "an interrupted result for each attempt").to.have.length(3);
        results.forEach((result) => {
          expect(result.is_interrupted).to.equal(true);
          expect(result.interruption_assessment).to.equal(false);
        });
        const bookings = results.map((result) => result.booking_id[0]);
        expect(bookings.sort(), "each linked to the booking the failure ended").to.deep.equal([...fixture.bookings].sort());
        notified(
          "medilab.test.result",
          results.map((result) => result.id),
          "test_result.interrupted",
        ).should("deep.equal", ["demo.head_of_department", "demo.tester"]);

        // The tester keeps the data measured so far, and cannot assess it.
        results.forEach((result) => callAs(TESTER, "medilab.test.result", "write", [[result.id], { value: 0.004 }]));
        cy.signInAs("tester");
        cy.visit(`/odoo/test-results/${results[0].id}`);
        cy.get(".o_form_view .alert-warning").should("contain", "The machine stopped during this measurement");
        cy.get(".o_statusbar_buttons button[name^=action_assess]").should("not.exist");
        callRefused("medilab.test.result", "action_assess_usable", [[results[0].id]]).should("contain", "Only the head of the department");

        // The head of department assesses the attempts one by one.
        cy.signInAs("head_of_department");
        [
          ["action_assess_usable", "usable", "Usable"],
          ["action_assess_retest", "retest", "Retest Needed"],
          ["action_assess_more_sample", "more_sample", "More Sample Needed"],
        ].forEach(([action, assessment, label], index) => {
          cy.visit(`/odoo/test-results/${results[index].id}`);
          cy.get(`.o_statusbar_buttons button[name="${action}"]`).click();
          cy.get(".o_form_view .alert-warning").should("contain", "The head of department assessed it").and("contain", label);
          callAs(ADMIN, "medilab.test.result", "read", [[results[index].id], ["interruption_assessment", "value"]]).then(([read]) => {
            expect(read.interruption_assessment).to.equal(assessment);
            expect(read.value, "the recorded data is kept").to.equal(0.004);
          });
        });
      });
    });
  });

  it("TC-F20-03 refuses to archive a machine with a scheduled, running or queued booking and lists them", () => {
    machineFixture({ tests: 2, book: 1 }, (created) => (fixture = created)).then(() => {
      cy.signInAs("administrator");
      const refuse = () => {
        cy.visit("/odoo/machines");
        search(fixture.tag);
        cy.contains(".o_data_row", fixture.tag).find(".o_list_record_selector input").check();
        cy.expectRefusal({
          read: () => cy.readRecord({ model: "medilab.machine", id: fixture.machine }, ["active", "write_date"]),
          action: () => {
            cy.contains(".o_control_panel button", "Actions").click();
            cy.contains(".o-dropdown-item", "Archive").click();
            cy.get(".modal:visible .modal-footer .btn-primary").click();
          },
          message: "This cannot be archived while these records use it:",
        });
        cy.get(".o_error_dialog").should("contain", "Machine Booking");
        cy.contains(".o_error_dialog .modal-footer button", "Close").click();
      };
      // One booking is scheduled and the other queued in the plan.
      bookingsOf(fixture).then((open) => {
        expect(open.map((booking) => booking.status).sort()).to.deep.equal(["proposed", "scheduled"]);
      });
      refuse();
      callAs(TESTER, "medilab.machine.booking", "action_start", [fixture.bookings]);
      refuse();
    });
  });
});
