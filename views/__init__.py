"""视图蓝图的注册入口。"""
from views import auth, dashboard, data, events, members, teams

BLUEPRINTS = (
    auth.bp,
    dashboard.bp,
    members.bp,
    teams.bp,
    events.bp,
    data.bp,
)


def register(app) -> None:
    for bp in BLUEPRINTS:
        app.register_blueprint(bp)
