import { registry } from "@web/core/registry";
import { TimelineArchParser } from "./timeline_arch_parser";
import { TimelineController } from "./timeline_controller";
import { TimelineModel } from "./timeline_model";
import { TimelineRenderer } from "./timeline_renderer";

export const timelineView = {
  type: "timeline",
  Controller: TimelineController,
  Renderer: TimelineRenderer,
  Model: TimelineModel,
  ArchParser: TimelineArchParser,
  searchMenuTypes: ["filter", "groupBy", "favorite"],

  props: (genericProps, view) => {
    const { arch, fields, resModel } = genericProps;
    const archInfo = new view.ArchParser().parse(arch);
    return {
      ...genericProps,
      modelParams: { ...archInfo, fields, resModel },
      Model: view.Model,
      Renderer: view.Renderer,
    };
  },
};

registry.category("views").add("timeline", timelineView);
