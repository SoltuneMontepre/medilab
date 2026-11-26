import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { untrack, useEffect } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

// A form's chatter opens with the Send message composer, once per record the person may post on. That composer does not
// take the focus, so the form keeps it and does not scroll to a chatter below it.
patch(Chatter.prototype, {
  setup() {
    super.setup();
    this.composerOpenedQuietly = false;
    let openedFor = null;
    useEffect(() => {
      const thread = this.state.thread;
      if (!this.webChatterProps?.record || !thread?.id || !thread.canPostMessage || openedFor === thread.id) {
        return;
      }
      openedFor = thread.id;
      untrack(() => {
        if (!this.state.composerType) {
          this.toggleComposer("message", { force: true, quiet: true });
        }
      });
    });
  },
  toggleComposer(mode = false, options = {}) {
    this.composerOpenedQuietly = Boolean(options.quiet);
    return super.toggleComposer(mode, options);
  },
});
