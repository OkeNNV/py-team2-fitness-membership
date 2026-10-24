from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("plan_service", "0004_alter_membershipplan_duration_days_and_more"),
        ("plan_service", "0004_membershipplan_stripe_product_id"),
    ]

    operations = []
