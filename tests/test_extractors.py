"""Tests for HTML extraction and transforms."""

import pytest

from webtracker.config import ExtractConfig
from webtracker.extract.css import extract_fields
from webtracker.extract.transforms import apply_transforms


class TestTransforms:
    def test_strip(self):
        assert apply_transforms("  hello  ", ["strip"]) == "hello"

    def test_lowercase(self):
        assert apply_transforms("HELLO", ["lowercase"]) == "hello"

    def test_to_number(self):
        assert apply_transforms("$1,299.99", ["to_number"]) == "1299.99"
        assert apply_transforms("€42.00", ["to_number"]) == "42.00"

    def test_hash_md5(self):
        result = apply_transforms("hello", ["hash_md5"])
        assert result is not None
        assert len(result) == 32

    def test_collapse_whitespace(self):
        assert apply_transforms("  hello   world  ", ["collapse_whitespace"]) == "hello world"

    def test_chain(self):
        assert apply_transforms("  $1,299.99  ", ["strip", "to_number"]) == "1299.99"

    def test_none_input(self):
        assert apply_transforms(None, ["strip"]) is None

    def test_regex_extract(self):
        result = apply_transforms("Price: $42.99 USD", ["regex_extract('\\$(\\d+\\.\\d+)')"])
        assert result == "42.99"

    def test_truncate(self):
        result = apply_transforms("Hello World", ["truncate(5)"])
        assert result == "Hello"


class TestCSSExtractor:
    SAMPLE_HTML = """
    <html>
    <body>
        <h1 id="title">  Product Name  </h1>
        <span class="price">$129.99</span>
        <button class="add-to-cart">Add to Cart</button>
        <div class="stock-status">In Stock</div>
        <a href="/details" class="link">Details</a>
    </body>
    </html>
    """

    def test_extract_text(self):
        extracts = [ExtractConfig(name="title", selector="#title", attribute="text")]
        result = extract_fields(self.SAMPLE_HTML, extracts)
        assert result["title"].strip() == "Product Name"

    def test_extract_with_transform(self):
        extracts = [
            ExtractConfig(
                name="price",
                selector=".price",
                attribute="text",
                transform=["strip", "to_number"],
            )
        ]
        result = extract_fields(self.SAMPLE_HTML, extracts)
        assert result["price"] == "129.99"

    def test_extract_attribute(self):
        extracts = [ExtractConfig(name="url", selector=".link", attribute="href")]
        result = extract_fields(self.SAMPLE_HTML, extracts)
        assert result["url"] == "/details"

    def test_extract_missing_element(self):
        extracts = [ExtractConfig(name="missing", selector=".nonexistent", attribute="text")]
        result = extract_fields(self.SAMPLE_HTML, extracts)
        assert result["missing"] is None

    def test_extract_multiple_fields(self):
        extracts = [
            ExtractConfig(name="title", selector="#title", attribute="text", transform=["strip"]),
            ExtractConfig(name="price", selector=".price", attribute="text", transform=["strip", "to_number"]),
            ExtractConfig(name="button", selector=".add-to-cart", attribute="text", transform=["strip", "lowercase"]),
        ]
        result = extract_fields(self.SAMPLE_HTML, extracts)
        assert result["title"] == "Product Name"
        assert result["price"] == "129.99"
        assert result["button"] == "add to cart"
