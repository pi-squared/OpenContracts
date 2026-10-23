from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("corpuses", "0060_corpus_default_agent")]

    operations = [
        migrations.AddField(
            model_name="corpus",
            name="workflow_label_policy",
            field=models.JSONField(default=dict, blank=True),
        )
    ]
