"""Invoice PDF generation service using WeasyPrint."""
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
import structlog

from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from billing.models.invoice import Invoice
    from billing.models.account import Account

logger = structlog.get_logger(__name__)


class InvoicePDFService:
    """Service for generating PDF invoices with branding."""

    def __init__(self):
        """Initialize PDF service with Jinja2 template environment."""
        # Setup Jinja2 template environment
        templates_dir = Path(__file__).parent.parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=True,
        )

        # Add custom filters
        self.env.filters["format_currency"] = self._format_currency

    def _format_currency(self, amount_cents: int, currency: str) -> str:
        """
        Format amount in cents to currency string.

        Args:
            amount_cents: Amount in cents
            currency: ISO 4217 currency code

        Returns:
            Formatted currency string (e.g., "$50.00", "€75.00", "¥5000")
        """
        # Zero-decimal currencies (JPY, KRW, etc.)
        zero_decimal_currencies = {
            "BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW",
            "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF",
            "XOF", "XPF",
        }

        if currency.upper() in zero_decimal_currencies:
            amount = amount_cents
            decimal_places = 0
        else:
            amount = Decimal(amount_cents) / 100
            decimal_places = 2

        # Currency symbols
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "JPY": "¥",
            "CAD": "CA$",
            "AUD": "A$",
            "CHF": "CHF ",
            "CNY": "¥",
            "INR": "₹",
        }

        symbol = currency_symbols.get(currency.upper(), currency.upper() + " ")

        if decimal_places == 0:
            return f"{symbol}{amount:,.0f}"
        else:
            return f"{symbol}{amount:,.2f}"

    async def generate_pdf(
        self,
        invoice: "Invoice",
        account: "Account",
        custom_footer: str | None = None,
    ) -> bytes:
        """
        Generate PDF for an invoice with branding.

        Args:
            invoice: Invoice to generate PDF for
            account: Account associated with the invoice
            custom_footer: Optional custom footer text

        Returns:
            PDF bytes

        Raises:
            Exception: If PDF generation fails
        """
        try:
            # Import WeasyPrint (heavy dependency, imported only when needed)
            from weasyprint import HTML, CSS

            from billing.config import settings

            # Load invoice template
            template = self.env.get_template("invoice.html")

            # Render HTML with invoice data
            html_content = template.render(
                invoice=invoice,
                account=account,
                company_name=settings.company_name,
                logo_url=settings.logo_url,
                brand_primary_color=settings.brand_primary_color,
                brand_secondary_color=settings.brand_secondary_color,
                custom_footer=custom_footer,
                format_currency=self._format_currency,
            )

            # Generate PDF from HTML
            pdf_bytes = HTML(string=html_content).write_pdf()

            logger.info(
                "invoice_pdf_generated",
                invoice_id=str(invoice.id),
                invoice_number=invoice.number,
                pdf_size_bytes=len(pdf_bytes),
            )

            return pdf_bytes

        except ImportError as e:
            logger.error(
                "weasyprint_not_installed",
                error=str(e),
            )
            raise Exception(
                "PDF generation library not installed. Install weasyprint: pip install weasyprint"
            ) from e

        except Exception as e:
            logger.exception(
                "pdf_generation_failed",
                invoice_id=str(invoice.id),
                error=str(e),
                exc_info=e,
            )
            raise

    async def generate_pdf_with_customization(
        self,
        invoice: "Invoice",
        account: "Account",
        branding: dict | None = None,
    ) -> bytes:
        """
        Generate PDF with custom branding overrides.

        Args:
            invoice: Invoice to generate PDF for
            account: Account associated with the invoice
            branding: Optional branding overrides (logo_url, primary_color, etc.)

        Returns:
            PDF bytes
        """
        try:
            from weasyprint import HTML
            from billing.config import settings

            # Use custom branding or fall back to settings
            branding = branding or {}

            template = self.env.get_template("invoice.html")

            html_content = template.render(
                invoice=invoice,
                account=account,
                company_name=branding.get("company_name", settings.company_name),
                logo_url=branding.get("logo_url", settings.logo_url),
                brand_primary_color=branding.get("primary_color", settings.brand_primary_color),
                brand_secondary_color=branding.get("secondary_color", settings.brand_secondary_color),
                custom_footer=branding.get("footer"),
                format_currency=self._format_currency,
            )

            pdf_bytes = HTML(string=html_content).write_pdf()

            logger.info(
                "custom_invoice_pdf_generated",
                invoice_id=str(invoice.id),
                custom_branding=bool(branding),
            )

            return pdf_bytes

        except Exception as e:
            logger.exception(
                "custom_pdf_generation_failed",
                invoice_id=str(invoice.id),
                error=str(e),
                exc_info=e,
            )
            raise
