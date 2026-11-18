from django.utils.html import conditional_escape

from core.admin_display import badge, thumbnail
from restaurants.models import Restaurant


def restaurant_with_logo(name: str = "restaurants/logos/a.png") -> Restaurant:
    return Restaurant(slug="cafe-a", logo=name)


class TestThumbnail:
    def test_an_image_is_a_small_picture_with_classes_only(self) -> None:
        html = str(thumbnail(restaurant_with_logo().logo))

        assert html.startswith("<img ")
        assert 'class="wasli-thumb"' in html
        assert 'src="/media/restaurants/logos/a.png"' in html
        assert 'loading="lazy"' in html
        assert "style=" not in html

    def test_the_large_form_has_its_own_class(self) -> None:
        assert "wasli-thumb--large" in str(
            thumbnail(restaurant_with_logo().logo, large=True)
        )

    def test_no_image_is_a_dash(self) -> None:
        for empty in (Restaurant(slug="x").logo, None):
            html = str(thumbnail(empty))
            assert 'class="wasli-empty"' in html and "—" in html and "<img" not in html

    def test_the_address_is_escaped(self) -> None:
        html = str(
            thumbnail(restaurant_with_logo('a"><script>alert(1)</script>.png').logo)
        )

        assert "<script>" not in html


class TestBadge:
    def test_a_label_has_its_kind_class(self) -> None:
        assert (
            str(badge("Placed", "warn"))
            == '<span class="wasli-badge wasli-badge--warn">Placed</span>'
        )

    def test_the_text_is_escaped(self) -> None:
        html = str(badge("<b>bad</b>", "bad"))

        assert "<b>" not in html and "&lt;b&gt;" in html
        assert (
            conditional_escape(html) == html
        )  # already safe markup, not escaped twice
