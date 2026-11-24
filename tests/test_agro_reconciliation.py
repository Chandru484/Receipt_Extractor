import pypdfium2
from extraction.validation import validate_and_reconcile_receipt, format_receipt_display
from processing.tamil_processor import normalize_tamil_text
from schemas.receipt_schema import ReceiptData


def test_soundaryas_agro_foods_tamil_and_reconciliation():
    pdf_path = r"d:\Downloads\Continue On 07.01.2026.pdf"
    pdf = pypdfium2.PdfDocument(pdf_path)

    full_text = ""
    for page_num, page in enumerate(pdf, start=1):
        text_page = page.get_textpage()
        page_text = normalize_tamil_text(text_page.get_text_range().strip())
        full_text += f"--- Page {page_num} ---\n{page_text}\n\n"

    # Start with empty receipt to test table parsing reconciliation
    raw_receipt = ReceiptData(
        vendor_name="SOUNDARYAS AGRO FOODS",
        invoice_number="10788",
        invoice_date="08-11-2025",
        items=[]
    )

    validated, diagnostics = validate_and_reconcile_receipt(raw_receipt, ocr_text=full_text)

    # 1. Verify 34 items extracted
    assert len(validated.items) == 34, f"Expected 34 items, got {len(validated.items)}"

    # 2. Verify Tamil item names and UOM
    assert "திணை அரிசி(UNBRANDED)" in validated.items[0].item_name
    assert validated.items[0].uom == "கிலோ"
    assert validated.items[0].quantity == 5.0

    assert "கம்பு(UNBRANDED)" in validated.items[1].item_name
    assert validated.items[1].uom == "கிலோ"
    assert validated.items[1].quantity == 30.0

    # Item 19 with continuation line
    item_19 = [it for it in validated.items if it.sl_no == "19"][0]
    assert "சிகாப்பு" in item_19.item_name
    assert "அரிசி(கேராள)(UNBRANDED" in item_19.item_name
    assert item_19.quantity == 10.0

    # Item 32 with continuation line
    item_32 = [it for it in validated.items if it.sl_no == "32"][0]
    assert "500g கம்பு" in item_32.item_name
    assert "குருணை(UNBRANDED)" in item_32.item_name
    assert item_32.uom == "பாக் கெட்"
    assert item_32.quantity == 5.0

    # 3. Verify total quantity reconciles to 307
    total_qty = sum(it.quantity for it in validated.items if it.quantity)
    assert total_qty == 307.0, f"Expected 307.0 total quantity, got {total_qty}"

    # 4. Verify formatted display contains Tamil Unicode
    display = format_receipt_display(validated)
    assert "திணை அரிசி" in display
    assert "கம்பு" in display
    assert "Total Qty : 307.0" in display
