from .summary import summary_bp
from .news import news_bp
from .search import search_bp
from .executives import executives_bp
from .forward import pe_bp
from .peg import peg_bp  # adjust path
from routes.macrotrends import router as macrotrends_router
from .interpret import router as interpret_router
from .eps import eps_router
from routes.metric import metric_router
from routes.compare_summary import compare_bp  # ✅ correct import
from .summary import summary_single_bp
def register_routes(app):
    app.register_blueprint(summary_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(executives_bp)
    app.register_blueprint(pe_bp)
    app.register_blueprint(macrotrends_router)
    app.register_blueprint(peg_bp)
    app.register_blueprint(interpret_router)
    app.register_blueprint(eps_router)
    app.register_blueprint(metric_router)
    app.register_blueprint(compare_bp)
    app.register_blueprint(summary_single_bp)
