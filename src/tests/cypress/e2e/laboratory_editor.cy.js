import { call, signIn } from "../support/odoo";

// This suite verifies the browser adapter with a DocsAPI test double. It does not establish a Document Server save.
const FILE = "2026/HPLC-ket-qua-thang-10.xlsx";
const adapter = `
window.DocsAPI = { DocEditor: function(id, config) {
    window.editorFixture = { config, creations: 1 };
    const frame = document.createElement("iframe");
    frame.title = "Editor adapter fixture";
    document.getElementById(id).replaceWith(frame);
    setTimeout(() => config.events.onAppReady(), 0);
}};
`;

function signInForEditor() {
  signIn("demo.tester");
  // Leave the back office before changing cookies or user settings, which can invalidate its active RPCs.
  cy.visit("/medilab/laboratory-files/0/edit", { failOnStatusCode: false });
}

describe("Laboratory browser editor adapter", () => {
  let user;
  let path;

  beforeEach(function () {
    signInForEditor();
    call("res.users", "search_read", [[["login", "=", "demo.tester"]], ["name", "lang"]]).then(([person]) => {
      user = person;
      call("res.users", "write", [[person.id], { lang: "en_US" }]);
    });
    cy.clearCookies();
    signInForEditor();
    call("medilab.laboratory.file", "search_read", [[["path", "=", FILE]], ["id"]]).then(([file]) => {
      expect(file, "demo results spreadsheet").to.exist;
      path = `/medilab/laboratory-files/${file.id}/edit`;
      cy.request({ url: path, failOnStatusCode: false, log: false }).then((response) => {
        // CI without configured service origins/health still runs the HTTP suite; this adapter suite is visibly pending.
        if (response.status === 503) this.skip();
        expect(response.status).to.eq(200);
      });
    });
    cy.intercept("GET", "**/web-apps/apps/api/documents/api.js", {
      headers: { "content-type": "application/javascript" },
      body: adapter,
    });
  });

  afterEach(() => {
    if (user) call("res.users", "write", [[user.id], { name: user.name, lang: user.lang }]);
  });

  for (const [language, loading, ready] of [
    ["en_US", "Connecting to the editor...", "Editor ready."],
    ["vi_VN", "Đang kết nối đến trình chỉnh sửa...", "Trình chỉnh sửa đã sẵn sàng."],
  ]) {
    for (const [width, height] of [[390, 844], [1440, 1000]]) {
      it(`shows accessible progress in ${language} at ${width}px without claiming a save`, () => {
        call("res.users", "write", [[user.id], { lang: language }]);
        cy.clearCookies();
        signInForEditor();
        cy.viewport(width, height);
        cy.visit(path);
        cy.get("#editor-status[role=status][aria-live=polite]").should("contain", loading);
        cy.window({ log: false }).then((win) => win.editorFixture.config.events.onDocumentReady());
        cy.get("#editor-status").should("contain", ready);
        cy.get("iframe[title='Editor adapter fixture']").should("be.visible");
        cy.get("#editor-retry").should("not.be.visible");
        cy.get("#editor-messages").should("not.be.visible");
        cy.window({ log: false }).then((win) => {
          expect(win.document.documentElement.scrollWidth).to.be.at.most(width);
          expect(win.editorFixture.config.editorConfig.customization.forcesave).to.eq(false);
          const editor = win.document.getElementById("laboratory-editor");
          editor.hidden = true;
          expect(win.getComputedStyle(editor).display).to.eq("none");
          editor.hidden = false;
          expect(win.getComputedStyle(editor).display).to.eq("flex");
        });
      });
    }
  }

  it("keeps hostile usernames as data and ignores upstream error descriptions", () => {
    const name = '</script><img src=x onerror="window.editorXss=1">&\u2028\u2029';
    call("res.users", "write", [[user.id], { name }]);
    cy.visit(path);
    cy.get("#editor-status").should("contain", "Connecting");
    cy.window({ log: false }).then((win) => {
      expect(win.editorFixture.config.editorConfig.user.name).to.eq(name);
      expect(win.editorXss).to.eq(undefined);
      win.editorFixture.config.events.onError({ data: { errorDescription: name } });
    });
    cy.get("#laboratory-editor img[src=x], #laboratory-editor [onerror]").should("not.exist");
    cy.get("#editor-status").should("contain", "save is not confirmed");
    cy.get("#editor-retry").should("be.visible").and("have.attr", "href", path);
  });

  it("shows timeout and stale configuration without automatically replacing a live editor", () => {
    cy.clock();
    cy.visit(path);
    cy.get("iframe").should("exist");
    cy.tick(30001);
    cy.get("#editor-status").should("contain", "taking longer");
    cy.get("#editor-retry").should("be.visible");
    cy.window({ log: false }).then((win) => win.editorFixture.config.events.onRequestRefreshFile());
    cy.get("#editor-status").should("contain", "fresh configuration");
    cy.window({ log: false }).then((win) => expect(win.editorFixture.creations).to.eq(1));
  });

  it("returns through native login to the same page and ignores an external redirect", () => {
    cy.clearCookies();
    cy.visit(`${path}?redirect=https://evil.example`);
    cy.location("pathname").should("eq", "/web/login");
    cy.location("search").then((query) => expect(new URLSearchParams(query).get("redirect")).to.eq(path));
    cy.get("input[name=login]").type("demo.tester");
    cy.get("input[name=password]").type("demo{enter}");
    cy.location("pathname").should("eq", path);
    cy.get("#editor-status").should("contain", "Connecting");
  });

  it("warns before leaving dirty documents and clears the warning after handoff", () => {
    cy.visit(path);
    cy.get("#editor-status").should("contain", "Connecting");
    cy.window({ log: false }).then((win) => {
      function unloadState() {
        const event = new win.Event("beforeunload", { cancelable: true });
        let legacyValue = "untouched";
        Object.defineProperty(event, "returnValue", {
          get() { return legacyValue; },
          set(value) { legacyValue = value; },
        });
        win.dispatchEvent(event);
        return { prevented: event.defaultPrevented, legacyValue };
      }
      expect(unloadState()).to.deep.eq({ prevented: false, legacyValue: "untouched" });
      win.editorFixture.config.events.onDocumentStateChange({ data: true });
      expect(unloadState()).to.deep.eq({ prevented: true, legacyValue: "" });
      win.editorFixture.config.events.onDocumentStateChange({ data: false });
      expect(unloadState()).to.deep.eq({ prevented: false, legacyValue: "untouched" });
    });
  });
});
