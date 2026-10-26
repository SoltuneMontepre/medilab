import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { ResizablePanel } from "@web/core/resizable_panel/resizable_panel";
import { patch } from "@web/core/utils/patch";
import { createElement } from "@web/core/utils/xml";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormRenderer } from "@web/views/form/form_renderer";

const STORAGE_KEY = "sol_theme.chatter";
const DEFAULT_WIDTH = 560;
const MIN_WIDTH = 380;

function readStoredChatter() {
  try {
    const { width, collapsed } = JSON.parse(browser.localStorage.getItem(STORAGE_KEY) || "{}");
    return { width: width >= MIN_WIDTH ? width : DEFAULT_WIDTH, collapsed: collapsed === true };
  } catch {
    return { width: DEFAULT_WIDTH, collapsed: false };
  }
}

function storeChatter(width, collapsed) {
  try {
    browser.localStorage.setItem(STORAGE_KEY, JSON.stringify({ width, collapsed }));
  } catch {
    // Storage is unavailable or full: the chatter keeps its size until the page closes.
  }
}

// The width and the collapsed state of the chatter beside a form.
patch(FormRenderer.prototype, {
  setup() {
    super.setup();
    this.mailComponents.ResizablePanel = ResizablePanel;
    const { width, collapsed } = readStoredChatter();
    this.chatterWidth = width;
    this.state.chatterCollapsed = collapsed;
    this.onChatterResize = (newWidth) => {
      if (newWidth !== this.chatterWidth) {
        this.chatterWidth = newWidth;
        storeChatter(newWidth, this.state.chatterCollapsed);
      }
    };
    this.toggleChatter = () => {
      this.state.chatterCollapsed = !this.state.chatterCollapsed;
      storeChatter(this.chatterWidth, this.state.chatterCollapsed);
    };
  },
  get chatterToggleLabel() {
    return this.state.chatterCollapsed ? _t("Expand the chatter") : _t("Collapse the chatter");
  },
});

// Wraps the chatter beside a form in Odoo's resizable panel, with a button on the bar that collapses it.
patch(FormCompiler.prototype, {
  compile(node, params) {
    const res = super.compile(node, params);
    const container = res.querySelector(".o-mail-Form-chatter:not(.o-isInFormSheetBg)");
    // Only a chatter that can sit beside the form has the class expression.
    if (!container?.hasAttribute("t-attf-class")) {
      return res;
    }
    const chatter = container.querySelector("t[t-component='__comp__.mailComponents.Chatter']");
    const toggle = createElement(
      "button",
      {
        type: "button",
        class: "o-mail-ChatterToggle",
        "t-on-click": "__comp__.toggleChatter",
        "t-att-aria-label": "__comp__.chatterToggleLabel",
        "t-att-title": "__comp__.chatterToggleLabel",
        "t-att-aria-expanded": "__comp__.state.chatterCollapsed ? 'false' : 'true'",
      },
      [
        createElement("i", {
          class: "oi",
          "t-att-data-icon": "__comp__.state.chatterCollapsed ? 'chevron_backward' : 'chevron_forward'",
        }),
      ],
    );
    const panel = createElement(
      "t",
      {
        "t-component": "__comp__.mailComponents.ResizablePanel",
        class: "'o-mail-ChatterPanel' + (__comp__.state.chatterCollapsed ? ' o-isCollapsed' : '')",
        handleSide: "'start'",
        minWidth: String(MIN_WIDTH),
        initialWidth: "__comp__.chatterWidth",
        onResize: "__comp__.onChatterResize",
      },
      [
        createElement("t", { "t-set-slot": "default" }, [
          createElement("div", { class: "o-mail-ChatterPanelContent" }, [
            createElement("div", { class: "o-mail-ChatterBar flex-shrink-0 d-print-none" }, [toggle]),
            createElement("div", { class: "o-mail-ChatterBody flex-grow-1", "t-att-class": "{ 'd-none': __comp__.state.chatterCollapsed }" }, [
              chatter.cloneNode(true),
            ]),
          ]),
        ]),
      ],
    );
    const aside = createElement("t", { "t-if": chatter.getAttribute("isChatterAside") }, [panel]);
    const beside = createElement("t", { "t-else": "" }, [chatter.cloneNode(true)]);
    chatter.replaceWith(aside, beside);
    return res;
  },
});
