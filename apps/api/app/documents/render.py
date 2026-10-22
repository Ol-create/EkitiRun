"""HTML templates to PDF. Owner: Lead (E6).

Templates live in app/templates/pdf/ (designed by Backend, B4). Relative paths
in a template (images, CSS) are resolved from that folder, e.g.
`<img src="logo.png">` loads app/templates/pdf/logo.png.
"""

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from weasyprint import HTML

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "pdf"


def naira(kobo: int) -> str:
    """5_000_000_00 kobo -> '₦5,000,000.00'."""
    return f"₦{kobo / 100:,.2f}"


_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),  # sponsor names can't inject HTML
    undefined=StrictUndefined,  # a typo in a template fails loudly instead of printing nothing
)
_env.filters["naira"] = naira


def render_html(template_name: str, context: dict[str, Any]) -> str:
    return _env.get_template(template_name).render(**context)


def render_pdf(template_name: str, context: dict[str, Any]) -> bytes:
    html = render_html(template_name, context)
    pdf = HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()
    assert pdf is not None
    return pdf
