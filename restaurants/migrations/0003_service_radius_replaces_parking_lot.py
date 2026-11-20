import django.core.validators
from django.db import migrations, models


def copy_the_lot_radius(apps, schema_editor):
    """Keep what a restaurant already had: its lot's radius becomes its own service distance."""
    Restaurant = apps.get_model("restaurants", "Restaurant")
    for restaurant in Restaurant.objects.select_related("parking_lot"):
        restaurant.service_radius_m = restaurant.parking_lot.radius_m
        restaurant.save(update_fields=["service_radius_m"])


class Migration(migrations.Migration):
    """A restaurant has its own optional service distance; the parking lot is gone.

    Not reversible: the lots are deleted, and a restaurant cannot get back a lot it never had.
    """

    dependencies = [
        ("restaurants", "0002_optional_arabic_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="restaurant",
            name="service_radius_m",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Metres from the restaurant that it serves cars. Leave empty for no limit.",
                null=True,
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
        migrations.RunPython(copy_the_lot_radius, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="restaurant",
            name="parking_lot",
        ),
        migrations.DeleteModel(
            name="ParkingLot",
        ),
    ]
