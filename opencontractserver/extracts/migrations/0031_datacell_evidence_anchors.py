from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("extracts", "0030_source_permission_hot_path_indexes")]

    operations = [
        migrations.AddField(
            model_name="datacell",
            name="evidence_anchors",
            field=models.JSONField(
                default=dict,
                blank=True,
                help_text="Quotation anchors for original and corrected finding versions; retrieval history remains in sources.",
            ),
        )
    ]
