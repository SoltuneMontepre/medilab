import { Component, signal, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { useModel } from "@web/model/model";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { standardViewProps } from "@web/views/standard_view_props";

export class TimelineController extends Component {
  static template = "laboratory.TimelineView";
  static components = { Layout, SearchBar, CogMenu };
  props = useProps({
    ...standardViewProps,
    Model: t.function(),
    modelParams: t.object(),
    Renderer: t.function(),
  });
  rootRef = signal.ref();

  setup() {
    this.orm = useService("orm");
    this.action = useService("action");
    this.model = useModel(this.props.Model, this.props.modelParams);
    useSetupAction({ rootRef: this.rootRef });
    this.searchBarToggler = useSearchBarToggler();
  }

  async openRecord(resId) {
    const { openAction } = this.props.modelParams;
    if (openAction) {
      const action = await this.orm.call(this.props.resModel, openAction, [[resId]]);
      await this.action.doAction(action);
      return;
    }
    await this.action.switchView("form", { resId });
  }
}
