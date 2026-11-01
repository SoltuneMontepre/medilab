import { callAs, refAs } from "../../../support/odoo";

const RECEPTION = "demo.sample_delivery_staff";
export const HEAD = "demo.head_of_department";
export const TESTER = "demo.tester";

// The day two weeks from now in the laboratory, as Odoo stores a date.
function inTwoWeeks() {
  return new Date(Date.now() + 14 * 86400000).toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
}

// A new request whose bottled water sample is tested for lead, which Chemistry tests; its due date comes from the
// safety margin.
export function leadTest() {
  const ids = {};
  refAs(RECEPTION, "sol_demo.demo_customer_an_phu").then(({ id }) => (ids.customer = id));
  refAs(RECEPTION, "sol_demo.demo_sample_type_bottled_water").then(({ id }) => (ids.sampleType = id));
  refAs(RECEPTION, "sol_demo.demo_test_parameter_lead").then(({ id }) => (ids.parameter = id));
  return cy
    .then(() =>
      callAs(RECEPTION, "medilab.test.request", "create", [
        {
          customer_id: ids.customer,
          expected_date: inTwoWeeks(),
          sample_ids: [
            [
              0,
              0,
              {
                customer_sample_name: `Nước khoáng đổi hạn ${Date.now()}`,
                sample_type_id: ids.sampleType,
                physical_state: "liquid",
                test_ids: [[0, 0, { parameter_id: ids.parameter }]],
              },
            ],
          ],
        },
      ]),
    )
    .then((requestId) => callAs(RECEPTION, "medilab.sample.test", "search", [[["sample_id.request_id", "=", requestId]]]))
    .then(([id]) => ({ model: "medilab.sample.test", id }));
}

// Shows the users' screens in English while each test runs, so dates are typed in its format, then gives back their
// languages.
export function inEnglish(...logins) {
  const languages = [];
  beforeEach(() => {
    logins.forEach((login) =>
      callAs(login, "res.users", "search_read", [[["login", "=", login]]], { fields: ["lang"] }).then(([user]) => {
        languages.push({ login, id: user.id, lang: user.lang });
        callAs(login, "res.users", "write", [[user.id], { lang: "en_US" }]);
      }),
    );
  });
  afterEach(() => {
    languages.splice(0).forEach(({ login, id, lang }) => callAs(login, "res.users", "write", [[id], { lang }]));
  });
}
