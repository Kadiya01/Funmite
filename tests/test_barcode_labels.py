"""Barcode label rendering tests (Phase 03)."""

from __future__ import annotations

from decimal import Decimal

from app.barcode.labels import BarcodeLabel, LabelRenderer, SvgLabelRenderer
from tests.factories import make_category, make_product


def test_svg_renderer_returns_xml_bytes():
    label = BarcodeLabel(
        product_id=1,
        name="Ankara Dress",
        selling_price=Decimal("8500"),
        barcode="1000000000009",
    )
    svg = SvgLabelRenderer().render(label)
    assert isinstance(svg, bytes)
    assert svg.startswith(b"<?xml")
    assert b"</svg>" in svg


def test_svg_contains_barcode_and_readable_text():
    label = BarcodeLabel(
        product_id=1,
        name="Ankara Dress",
        selling_price=Decimal("8500"),
        barcode="1000000000009",
    )
    svg = SvgLabelRenderer().render(label)
    assert b"1000000000009" in svg
    assert b"Ankara Dress" in svg
    assert b"Price: &#8358;8500" in svg


def test_svg_escapes_product_name():
    label = BarcodeLabel(
        product_id=1,
        name="A & B <C>",
        selling_price=Decimal("100"),
        barcode="1000000000009",
    )
    svg = SvgLabelRenderer().render(label)
    assert b"A &amp; B &lt;C&gt;" in svg


def test_render_product_uses_product_record(session):
    category = make_category(session)
    product = make_product(session, category, name="Kaftan", selling_price=Decimal("6000"))
    product.barcode = "1000000000009"
    session.flush()
    svg = SvgLabelRenderer().render_product(product)
    assert b"Kaftan" in svg
    assert b"1000000000009" in svg


def test_label_from_product(session):
    category = make_category(session)
    product = make_product(session, category, selling_price=Decimal("2500"))
    label = BarcodeLabel.from_product(product)
    assert label.product_id == product.id
    assert label.name == product.name
    assert label.selling_price == Decimal("2500")
    assert label.barcode == product.barcode


def test_base_renderer_is_abstract():
    try:
        LabelRenderer().render(BarcodeLabel(1, "x", Decimal("1"), "123"))
    except NotImplementedError:
        pass
    else:
        raise AssertionError("LabelRenderer.render should not be implemented")
