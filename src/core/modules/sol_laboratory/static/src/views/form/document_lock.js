import { onWillUnmount, usePlugin } from "@odoo/owl";
import { BusPlugin } from "@bus/services/bus_plugin";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

// Only forms of documents with the lock mixin carry this field.
const LOCK_FIELD = "lock_message";
const BUS_TYPE = "medilab.document_lock";
// While the user keeps editing, the lock's last activity is refreshed at most this often.
const TOUCH_INTERVAL_MS = 60000;

// Takes the document's lock when the user starts editing, keeps it while they edit, releases it when they cancel or
// leave, and reloads the form when another user takes or releases a lock on it.
patch(FormController.prototype, {
  setup() {
    super.setup(...arguments);
    if (!(LOCK_FIELD in this.props.fields)) {
      return;
    }
    this.documentLock = { held: false, taking: false, touchedAt: 0 };
    this.lockNotification = useService("notification");
    const unsubscribe = usePlugin(BusPlugin).subscribe(BUS_TYPE, (payload) => this.onDocumentLockChanged(payload));
    onWillUnmount(() => {
      unsubscribe();
      this.releaseDocumentLock("left");
    });
  },

  onRecordChanged() {
    super.onRecordChanged(...arguments);
    if (this.documentLock && this.model.root.resId) {
      // Not awaited: the change still holds the model's mutex, which discarding a refused change waits for.
      this.takeDocumentLock();
    }
  },

  async onRecordSaved() {
    await super.onRecordSaved(...arguments);
    // The server releases the lock with the save.
    if (this.documentLock) {
      this.documentLock.held = false;
    }
  },

  onWillLoadRoot() {
    super.onWillLoadRoot(...arguments);
    this.releaseDocumentLock("left");
  },

  async discard() {
    this.releaseDocumentLock("cancelled");
    await super.discard(...arguments);
  },

  async takeDocumentLock() {
    const now = Date.now();
    // A change made while the lock is being taken waits for that call instead of sending a second one.
    if (this.documentLock.taking || (this.documentLock.held && now - this.documentLock.touchedAt < TOUCH_INTERVAL_MS)) {
      return;
    }
    this.documentLock.touchedAt = now;
    this.documentLock.taking = true;
    const { resModel, resId } = this.model.root;
    let result;
    try {
      result = await this.orm.call(resModel, "lock_take", [[resId]]);
    } finally {
      this.documentLock.taking = false;
    }
    this.documentLock.held = result.taken;
    if (!result.taken) {
      this.lockNotification.add(result.message, { type: "warning" });
      await this.model.root.discard();
      await this.model.root.load();
    }
  },

  releaseDocumentLock(reason) {
    if (!this.documentLock?.held) {
      return;
    }
    this.documentLock.held = false;
    const { resModel, resId } = this.model.root;
    this.orm.silent.call(resModel, "lock_release", [[resId], reason]);
  },

  async onDocumentLockChanged({ model, id }) {
    const root = this.model.root;
    if (model !== root.resModel || id !== root.resId || this.documentLock.held || this.isUnderDialog() || (await root.isDirty())) {
      return;
    }
    await root.load();
  },

  // A dialog open over the form, such as one adding a line, edits records the form does not count as changes yet;
  // reloading the form drops them.
  isUnderDialog() {
    const formEl = this.rootRef();
    return Boolean(formEl && !this.ui.activeElement.contains(formEl));
  },
});
