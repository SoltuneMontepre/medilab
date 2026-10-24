import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { clamp } from "@web/core/utils/numbers";
import { useRecordObserver } from "@web/model/relational_model/utils";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

const LOCATION_MODEL = "medilab.location";
const DIGITS = 4;

// A location's picture with the locations inside it at their points. On a child's form it shows the parent's
// picture with the child marked, and clicking the picture places the child.
export class LocationMap extends Component {
  static template = "sol_laboratory.LocationMap";
  props = useProps({ ...standardWidgetProps, ofParent: t.boolean().optional(false) });

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.state = proxy({ map: null });
    useRecordObserver(async (record) => {
      // Reading only these makes the map reload when the parent or the location's own picture changes.
      const mapId = this.props.ofParent ? record.data.parent_id?.id : record.data.image_attachment_id && record.resId;
      this.state.map = mapId ? await this.orm.call(LOCATION_MODEL, "get_map", [[mapId]]) : null;
    });
  }

  get record() {
    return this.props.record;
  }

  get imageUrl() {
    return `/web/content/${this.state.map.image_id}`;
  }

  get placeHint() {
    return _t("Click the map of %s where this location is.", this.state.map.name);
  }

  get noMapHint() {
    return _t("%s has no map. Add its picture to place the locations inside it.", this.state.map.name);
  }

  get canPlace() {
    return this.props.ofParent && !this.props.readonly;
  }

  get current() {
    const { map_x: x, map_y: y } = this.record.data;
    if (!x && !y) {
      return null;
    }
    const { code, display_name: name } = this.record.data;
    return { id: this.record.resId, code, name, x, y, current: true };
  }

  get points() {
    if (!this.props.ofParent) {
      return this.state.map.points;
    }
    const others = this.state.map.points.filter((point) => point.id !== this.record.resId);
    return this.current ? [...others, this.current] : others;
  }

  pointStyle(point) {
    return `left: ${point.x * 100}%; top: ${point.y * 100}%;`;
  }

  place(event) {
    if (!this.canPlace) {
      return;
    }
    const box = event.currentTarget.getBoundingClientRect();
    const share = (offset, size) => Number(clamp(offset / size, 0, 1).toFixed(DIGITS));
    this.record.update({
      map_x: share(event.clientX - box.left, box.width),
      map_y: share(event.clientY - box.top, box.height),
    });
  }

  removeFromMap() {
    this.record.update({ map_x: false, map_y: false });
  }

  openLocation(point) {
    if (point.current) {
      return;
    }
    this.action.doAction({
      type: "ir.actions.act_window",
      res_model: LOCATION_MODEL,
      res_id: point.id,
      views: [[false, "form"]],
    });
  }
}

registry.category("view_widgets").add("location_map", {
  component: LocationMap,
  extractProps: ({ attrs }) => ({ ofParent: Boolean(attrs.of_parent) }),
  fieldDependencies: [
    { name: "code", type: "char" },
    { name: "parent_id", type: "many2one", relation: LOCATION_MODEL },
    { name: "image_attachment_id", type: "many2one", relation: "ir.attachment" },
    { name: "map_x", type: "float", readonly: false },
    { name: "map_y", type: "float", readonly: false },
  ],
});
