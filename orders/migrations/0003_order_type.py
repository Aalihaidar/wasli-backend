from django.db import migrations, models


class Migration(migrations.Migration):
    """``fulfilment_type`` becomes ``order_type``, the name the API contract uses. A rename keeps
    every existing value (only ``car`` exists), and the choices now list the other two types."""

    dependencies = [
        ("orders", "0002_distance_to_the_restaurant_only"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="fulfilment_type",
            new_name="order_type",
        ),
        migrations.AlterField(
            model_name="order",
            name="order_type",
            field=models.CharField(
                choices=[
                    ("car", "To the car"),
                    ("dine_in", "Dine in"),
                    ("delivery", "Delivery"),
                ],
                default="car",
                max_length=10,
            ),
        ),
    ]
