import { visitXML } from "@web/core/utils/xml";

export const SCALES = ["day", "week", "month"];

export class TimelineArchParser {
  parse(arch) {
    const archInfo = {
      dateStart: null,
      dateStop: null,
      dateDeadline: null,
      statusField: null,
      rowField: null,
      scale: "week",
      openAction: null,
    };
    visitXML(arch, (node) => {
      if (node.tagName !== "timeline") {
        return;
      }
      archInfo.dateStart = node.getAttribute("date_start");
      archInfo.dateStop = node.getAttribute("date_stop");
      archInfo.dateDeadline = node.getAttribute("date_deadline");
      archInfo.statusField = node.getAttribute("status_field");
      archInfo.rowField = node.getAttribute("row_field");
      archInfo.openAction = node.getAttribute("open_action");
      const scale = node.getAttribute("scale");
      if (SCALES.includes(scale)) {
        archInfo.scale = scale;
      }
    });
    return archInfo;
  }
}
