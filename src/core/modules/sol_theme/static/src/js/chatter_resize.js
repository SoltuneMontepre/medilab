import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { ResizablePanel } from "@web/core/resizable_panel/resizable_panel";
import { SIZES } from "@web/core/ui/ui_utils";
import { patch } from "@web/core/utils/patch";
import { createElement } from "@web/core/utils/xml";
import { useSubEnv } from "@web/owl2/utils";
import { FormCompiler } from "@web/views/form/form_compiler";
import { FormRenderer } from "@web/views/form/form_renderer";

const STORAGE_KEY = "sol_theme.chatter";
const DEFAULT_WIDTH = 560;
const MIN_WIDTH = 380;
// The layouts in which mail puts the chatter beside the form (its o-aside class).
const ASIDE_LAYOUTS = '["SIDE_CHATTER", "EXTERNAL_COMBO_XXL"]';

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

// The width and the collapsed state of the chatter or audit log beside a form.
patch(FormRenderer.prototype, {
  setup() {
    super.setup();
    this.mailComponents.ResizablePanel = ResizablePanel;
    const { width, collapsed } = readStoredChatter();
    this.chatterWidth = width;
    this.state.chatterCollapsed = collapsed;
    this.onChatterResize = (newWidth) => {
      // The stylesheet caps the panel's width, so the width kept is the one shown.
      const panel = this.rootRef()?.querySelector(".o-mail-ChatterPanel");
      const cap = panel ? Number.parseFloat(getComputedStyle(panel).maxWidth) : Infinity;
      const width = Math.min(cap, newWidth);
      if (width !== this.chatterWidth) {
        this.chatterWidth = width;
        storeChatter(width, this.state.chatterCollapsed);
      }
    };
    this.toggleChatter = () => {
      this.state.chatterCollapsed = !this.state.chatterCollapsed;
      storeChatter(this.chatterWidth, this.state.chatterCollapsed);
    };
    // The chatter's top bar holds the button that collapses it.
    useSubEnv({ collapseChatter: { run: this.toggleChatter, label: _t("Collapse the chatter") } });
  },
  get expandChatterLabel() {
    return _t("Expand the chatter");
  },
  get collapseAuditLogLabel() {
    return _t("Collapse the audit log");
  },
  get expandAuditLogLabel() {
    return _t("Expand the audit log");
  },
});

// Odoo's resizable panel around a feed beside a form. Collapsed, the panel is a narrow strip that expands it again.
function resizablePanel(feed, icon, expandLabel) {
  const dock = createElement(
    "button",
    {
      type: "button",
      class: "o-mail-ChatterDock d-print-none",
      "t-if": "__comp__.state.chatterCollapsed",
      "t-on-click": "__comp__.toggleChatter",
      "t-att-aria-label": expandLabel,
      "t-att-title": expandLabel,
      "aria-expanded": "false",
    },
    [
      createElement("i", { class: "oi oi-fw", "data-icon": "keyboard_double_arrow_left" }),
      createElement("i", { class: "oi oi-fw", "data-icon": icon }),
    ],
  );
  return createElement(
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
          dock,
          createElement("div", { class: "o-mail-ChatterBody flex-grow-1", "t-att-class": "{ 'd-none': __comp__.state.chatterCollapsed }" }, [
            feed,
          ]),
        ]),
      ]),
    ],
  );
}

// Shows the panel while the condition holds, and the feed as it is otherwise.
function wrapFeed(feed, condition, panel) {
  const aside = createElement("t", { "t-if": condition }, [panel]);
  const other = createElement("t", { "t-else": "" }, [feed.cloneNode(true)]);
  feed.replaceWith(aside, other);
}

patch(FormCompiler.prototype, {
  compile(node, params) {
    const res = super.compile(node, params);
    const container = res.querySelector(".o-mail-Form-chatter:not(.o-isInFormSheetBg)");
    // Only a chatter that can sit beside the form has the class expression.
    if (container?.hasAttribute("t-attf-class")) {
      const chatter = container.querySelector("t[t-component='__comp__.mailComponents.Chatter']");
      const hasPreview = Boolean(res.querySelector(".o_attachment_preview"));
      wrapFeed(
        chatter,
        `${ASIDE_LAYOUTS}.includes(__comp__.mailLayout(${hasPreview}))`,
        resizablePanel(chatter.cloneNode(true), "forum", "__comp__.expandChatterLabel"),
      );
    }
    // A document's audit log sits beside the sheet where the form puts its parts in a row, and collapses from its heading.
    const auditLog = res.querySelector(".o_form_renderer > .o_audit_aside");
    if (auditLog) {
      const besideSheet = auditLog.cloneNode(true);
      besideSheet.querySelector("h3")?.append(
        createElement(
          "button",
          {
            type: "button",
            class: "o-mail-ChatterCollapse btn btn-link text-muted ms-auto px-1 py-0 d-print-none",
            "aria-expanded": "true",
            "t-att-aria-label": "__comp__.collapseAuditLogLabel",
            "t-att-title": "__comp__.collapseAuditLogLabel",
            "t-on-click": "__comp__.toggleChatter",
          },
          [createElement("i", { class: "oi oi-fw", "data-icon": "keyboard_double_arrow_right", role: "img" })],
        ),
      );
      wrapFeed(
        auditLog,
        `__comp__.uiService.size >= ${SIZES.XXL}`,
        resizablePanel(besideSheet, "fact_check", "__comp__.expandAuditLogLabel"),
      );
    }
    return res;
  },
});
