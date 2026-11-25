// The business steps of a test in the Command Log, and helpers that show as one line each.

import { beginQuiet, endQuiet, logged, resetQuiet } from "./odoo";

let number = 0;
let current = "";
const open = [];

beforeEach(() => {
  number = 0;
  current = "";
  resetQuiet();
  open.length = 0;
});

// A failure inside a quiet helper marks the helper's line as failed, as its own commands are not in the log. Cypress
// calls a test's own listeners, added with cy.on, after this one and stops at the first that throws, so with one of
// them the test's listener decides whether the failure stands.
Cypress.on("fail", (error) => {
  open.splice(0).forEach((log) => log.error(error));
  if (!cy.listeners("fail").length) throw error;
});

// The step the test is in, as the Command Log shows it.
export const currentStep = () => current;

// Marks the start of a business step of the test: a bold numbered line in the Command Log, whose snapshot shows the
// page as the step starts, and the same line in the terminal of a headless run.
export function step(name) {
  return cy.then(() => {
    number += 1;
    current = `Step ${number}: ${name}`;
    cy.log(`**${current}**`);
    return cy.task("logStep", current, { log: false });
  });
}

// A short message for a helper's arguments: strings as they are, records by model and ID, other values as JSON.
function summary(args) {
  const parts = args
    .filter((arg) => arg !== undefined)
    .map((arg) => {
      if (typeof arg === "string") return arg;
      if (arg?.model && arg?.id) return `${arg.model} ${arg.id}`;
      if (arg?.login) return arg.login;
      return JSON.stringify(arg);
    });
  const message = parts.join(", ");
  return message.length > 80 ? `${message.slice(0, 77)}...` : message;
}

// Runs a helper's commands inside its open line of the Command Log, then ends the line with the page after them.
function inLine(log, run) {
  beginQuiet();
  open.push(log);
  return cy.then(run).then((result) => {
    endQuiet();
    open.splice(open.indexOf(log), 1);
    log.snapshot("after").end();
    return result;
  });
}

// Runs a helper's commands as one line of the Command Log, with the page before and after it; the requests and checks
// inside it stay out of the log. Inside another quiet helper it adds no line of its own.
export function quietly(name, message, commands) {
  // A helper may give back a plain value after queuing commands; it is wrapped so the chain yields it.
  const run = () => {
    const result = commands();
    return result === undefined || Cypress.isCy(result) ? result : cy.wrap(result, { log: false });
  };
  return cy.then(() => {
    if (!logged()) return run();
    const log = Cypress.log({ name, message, autoEnd: false });
    log.snapshot("before");
    return inLine(log, run);
  });
}

// A helper that shows as one line, named after it, with its arguments as the message.
export function helper(name, fn) {
  return (...args) => quietly(name, summary(args), () => fn(...args));
}
