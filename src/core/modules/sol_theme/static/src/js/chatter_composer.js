import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { untrack, useEffect } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

// A form's chatter opens with the Send message composer, once per record the person may post on.
patch(Chatter.prototype, {
  setup() {
    super.setup();
    let openedFor = null;
    useEffect(() => {
      const thread = this.state.thread;
      if (!this.webChatterProps?.record || !thread?.id || !thread.canPostMessage || openedFor === thread.id) {
        return;
      }
      openedFor = thread.id;
      untrack(() => {
        if (!this.state.composerType) {
          this.toggleComposer("message", { force: true });
        }
      });
    });
  },
});
