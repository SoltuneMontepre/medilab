def load_vietnam_chart(env):
    """Install the Vietnam chart when the company has none.

    The demo documents need its sales journal while the module is still loading, and l10n_vn is already
    installed. account warns about try_loading before the registry is loaded unless the install callback
    is set. That callback runs again once the registry is ready and finds the chart in place.
    """
    company = env.company
    if company.chart_template:
        return
    if not hasattr(env.registry, "_auto_install_template"):
        env.registry._auto_install_template = load_vietnam_chart
    env["account.chart.template"].try_loading("vn", company)
