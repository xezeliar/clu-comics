"""Template helpers for cosmetic touches (publisher dots)."""
from flask import Blueprint

from core.publishers import publisher_color

cosmetics_bp = Blueprint("cosmetics", __name__)

cosmetics_bp.add_app_template_global(publisher_color, "publisher_color")
