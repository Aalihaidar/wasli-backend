from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction

from core.locales import ARABIC_OPTIONAL_HELP, ArabicFallbackMixin, arabic_or_english
from core.models import BaseModel
from core.money import CURRENCY
from core.permissions import Role
from core.tenancy import RestaurantOwnedModel

_slug_validator = RegexValidator(
    r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    "Lowercase letters and digits, separated by single hyphens.",
)
_colour_validator = RegexValidator(
    r"^#[0-9a-fA-F]{6}$", "Use a hex colour such as #1A73E8."
)
_latitude_validators = [MinValueValidator(-90), MaxValueValidator(90)]
_longitude_validators = [MinValueValidator(-180), MaxValueValidator(180)]

# Words that are routes of their own under /api/v1/restaurants/, so no restaurant can use them
# as its slug (GET /restaurants/nearby is the nearby list, never a restaurant).
RESERVED_SLUGS = frozenset({"nearby"})

ROLE_CHOICES = [(role.value, role.value.title()) for role in Role]


class ParkingLot(BaseModel):
    """A parking area shared by one or more restaurants. A customer is "at" a restaurant when
    they are within ``radius_m`` metres of the lot's centre."""

    name = models.CharField(max_length=150)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(validators=_latitude_validators)
    longitude = models.FloatField(validators=_longitude_validators)
    radius_m = models.PositiveIntegerField(
        default=300, validators=[MinValueValidator(1)]
    )

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Restaurant(ArabicFallbackMixin, BaseModel):
    class SubscriptionStatus(models.TextChoices):
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"

    # Used in URLs and QR codes (/r/<slug>).
    slug = models.SlugField(max_length=60, unique=True, validators=[_slug_validator])
    name_en = models.CharField(max_length=150)
    name_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
    # Empty means the default welcome text of the conversation engine.
    welcome_message_en = models.TextField(blank=True)
    welcome_message_ar = models.TextField(blank=True)
    logo = models.ImageField(upload_to="restaurants/logos/", blank=True)
    cover = models.ImageField(upload_to="restaurants/covers/", blank=True)
    brand_colour = models.CharField(
        max_length=7, blank=True, validators=[_colour_validator]
    )
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(validators=_latitude_validators)
    longitude = models.FloatField(validators=_longitude_validators)
    parking_lot = models.ForeignKey(
        ParkingLot, on_delete=models.PROTECT, related_name="restaurants"
    )
    currency = models.CharField(max_length=3, default=CURRENCY, editable=False)
    timezone = models.CharField(max_length=64, default="Asia/Dubai")
    # Deactivated, never deleted: orders refer to the restaurant.
    is_active = models.BooleanField(default=True)
    # Informational only: marks a restaurant that is not a real customer (a test or fake
    # one). It changes no behaviour; the admin shows it as a column and a filter.
    is_demo = models.BooleanField(
        default=False,
        help_text="Marks a test or fake restaurant. Informational only.",
    )
    subscription_status = models.CharField(
        max_length=10,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL,
    )
    subscription_paid_until = models.DateField(null=True, blank=True)
    # Set by the restaurant site's heartbeat; read to tell whether its screen is online.
    screen_last_seen_at = models.DateTimeField(null=True, blank=True, editable=False)
    default_eta_minutes = models.PositiveSmallIntegerField(
        default=10, validators=[MinValueValidator(1)]
    )
    accepts_cash = models.BooleanField(default=True)
    accepts_card = models.BooleanField(default=False)
    # The number the next order gets; read and bumped under a row lock when an order is created.
    next_order_number = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        ordering = ("name_en",)

    def __str__(self) -> str:
        return self.name_en

    def clean(self) -> None:
        super().clean()
        self._check_slug()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self._check_slug()
        super().save(*args, **kwargs)

    def _check_slug(self) -> None:
        if self.slug in RESERVED_SLUGS:
            raise ValidationError(
                {"slug": f"'{self.slug}' is reserved; choose another."}
            )


class RestaurantMenuImage(RestaurantOwnedModel):
    """A picture of the menu that the bot sends in the chat."""

    image = models.ImageField(upload_to="restaurants/menu/")
    caption_en = models.CharField(max_length=150, blank=True)
    caption_ar = models.CharField(
        max_length=150, blank=True, help_text=ARABIC_OPTIONAL_HELP
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "created_at")

    def __str__(self) -> str:
        return f"{self.restaurant} #{self.sort_order}"

    @property
    def caption_ar_display(self) -> str:
        return arabic_or_english(self.caption_ar, self.caption_en)


class StaffMembership(RestaurantOwnedModel):
    """Which restaurant a user works for, and with which role.

    The role is mapped to permission codes in ``core.permissions``. Rules kept here:

    * every restaurant account signs in with a username, so the user must have one;
    * the user is not a customer: an account is staff or a customer, never both;
    * the last active admin of a restaurant cannot be demoted, deactivated or removed;
    * a member is deactivated, never deleted, so their history stays attached.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_memberships",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("restaurant__name_en", "user__username")
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["user", "restaurant"], name="unique_member_per_restaurant"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} at {self.restaurant} ({self.role})"

    def clean(self) -> None:
        super().clean()
        self._check_rules()

    def save(self, *args: Any, **kwargs: Any) -> None:
        with transaction.atomic():
            self._check_rules()
            super().save(*args, **kwargs)

    def delete(
        self, using: Any = None, keep_parents: bool = False
    ) -> tuple[int, dict[str, int]]:
        with transaction.atomic():
            self._check_rules(removing=True)
            return super().delete(using=using, keep_parents=keep_parents)

    def _check_rules(self, *, removing: bool = False) -> None:
        if not removing and self.user_id is not None and not self.user.username:
            raise ValidationError(
                {"user": "A restaurant account must have a username to sign in with."}
            )
        # A person is a customer or restaurant staff, never both (customers.Customer).
        if (
            not removing
            and self.user_id is not None
            and getattr(self.user, "customer", None) is not None
        ):
            raise ValidationError(
                {
                    "user": "A customer account cannot also be a restaurant staff account."
                }
            )
        self._check_last_admin(removing=removing)

    def _check_last_admin(self, *, removing: bool) -> None:
        if self._state.adding:
            return
        before = StaffMembership.objects.filter(pk=self.pk).first()
        if before is None or before.role != Role.ADMIN or not before.is_active:
            return
        stays_admin = (
            not removing
            and self.role == Role.ADMIN
            and self.is_active
            and self.restaurant_id == before.restaurant_id
        )
        if stays_admin:
            return
        # Lock the restaurant so two admins cannot step down at the same time.
        Restaurant.objects.select_for_update().filter(pk=before.restaurant_id).first()
        others = (
            StaffMembership.objects.filter(
                restaurant_id=before.restaurant_id,
                role=Role.ADMIN,
                is_active=True,
            )
            .exclude(pk=self.pk)
            .exists()
        )
        if not others:
            raise ValidationError(
                "The last active admin of a restaurant cannot be demoted, "
                "deactivated or removed. Add another admin first."
            )
