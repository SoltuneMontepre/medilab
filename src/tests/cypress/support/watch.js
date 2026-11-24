import { currentStep } from "./steps";

// The watch mode: in the Cypress App, every click and choice first frames its element on the page, names it with the
// current step and waits a moment, so a person can follow the test as a user would work; an entry is framed for a
// moment once typed, as Odoo redraws a field it waits on and the entry would land in the old one. A headless run acts
// at once. MEDILAB_E2E_WATCH=0 turns it off in the Cypress App, =1 turns it on in a headless run too, and
// MEDILAB_E2E_WATCH_DELAY sets the wait in milliseconds.
const BEFORE = ["click", "dblclick", "select", "check", "uncheck"];
const AFTER = ["type", "clear"];
const COLOR = "#f08c00";
const setting = Cypress.expose("watch");
const watching = setting === "1" || (setting !== "0" && Cypress.config("isInteractive"));

// A short name of the element: its text, label, field name or tag.
function elementName(element) {
  const text = (element.innerText || element.value || "").trim().replace(/\s+/g, " ");
  const name = text || element.getAttribute("aria-label") || element.getAttribute("title") || element.getAttribute("name");
  const short = (name || element.tagName.toLowerCase()).slice(0, 40);
  return element.type === "password" ? "password" : short;
}

// Adds a fixed, non-clickable mark to the page with the given style.
function mark(document, style, text = "") {
  const element = document.createElement("div");
  element.textContent = text;
  Object.assign(element.style, { position: "fixed", zIndex: "2147483647", pointerEvents: "none", ...style });
  document.body.append(element);
  return element;
}

// Frames the element about to be used, with a label of the step and the action and a dot where it is used; yields a
// function that removes the marks.
function frame($subject, action) {
  const element = $subject?.[0];
  if (!element?.isConnected || !element.ownerDocument?.body) return () => {};
  const document = element.ownerDocument;
  const view = document.defaultView;
  // Only an element out of sight is scrolled to: Odoo closes its suggestions on any scroll of the page.
  const seen = element.getBoundingClientRect();
  if (seen.top < 0 || seen.bottom > view.innerHeight || seen.left < 0 || seen.right > view.innerWidth) {
    element.scrollIntoView({ block: "center", inline: "nearest" });
  }
  const box = element.getBoundingClientRect();
  const step = currentStep();
  const label = step ? `${step} › ${action}` : action;
  const marks = [
    mark(document, {
      left: `${box.left - 4}px`,
      top: `${box.top - 4}px`,
      width: `${box.width + 8}px`,
      height: `${box.height + 8}px`,
      border: `3px solid ${COLOR}`,
      borderRadius: "6px",
      boxShadow: "0 0 0 4px rgba(240, 140, 0, 0.25)",
    }),
    mark(
      document,
      {
        left: `${Math.max(box.left - 4, 4)}px`,
        top: `${Math.max(box.top - 30, 4)}px`,
        padding: "2px 8px",
        background: COLOR,
        color: "#fff",
        font: "600 12px/20px sans-serif",
        borderRadius: "4px",
        whiteSpace: "nowrap",
      },
      `${label} ${elementName(element)}`,
    ),
    mark(document, {
      left: `${box.left + box.width / 2 - 7}px`,
      top: `${box.top + box.height / 2 - 7}px`,
      width: "14px",
      height: "14px",
      borderRadius: "50%",
      background: "rgba(240, 140, 0, 0.8)",
      border: "2px solid #fff",
    }),
  ];
  return () => marks.forEach((element) => element.remove());
}

if (watching) {
  const delay = Number(Cypress.expose("watchDelay")) || 700;
  const pause = () => new Cypress.Promise((resolve) => setTimeout(resolve, delay));
  for (const action of BEFORE) {
    Cypress.Commands.overwrite(action, (original, subject, ...args) => {
      const unframe = frame(subject, action);
      return pause().then(() => {
        unframe();
        return original(subject, ...args);
      });
    });
  }
  for (const action of AFTER) {
    Cypress.Commands.overwrite(action, (original, subject, ...args) =>
      Cypress.Promise.resolve(original(subject, ...args)).then((result) => {
        const unframe = frame(subject, action);
        return pause().then(() => {
          unframe();
          return result;
        });
      }),
    );
  }
}
