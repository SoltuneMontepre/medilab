import { useState } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { ViewButton } from "@web/views/view_button/view_button";

// Show an inline spinner inside ViewButtons while their server action is executing.
patch(ViewButton.prototype, {
  setup() {
    super.setup();
    this.medilabLoading = useState({ active: false });
    const baseHandler = this.handleViewButton;
    this.handleViewButton = (params) => {
      this.medilabLoading.active = true;
      const done = () => {
        this.medilabLoading.active = false;
      };
      const result = baseHandler({
        ...params,
        afterExecute: () => {
          params.afterExecute?.();
          done();
        },
      });
      if (result && typeof result.finally === "function") {
        result.finally(done);
      }
      return result;
    };
  },
});
