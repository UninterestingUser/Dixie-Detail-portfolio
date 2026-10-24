from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0007_link_vehicles_and_approvals'),
    ]

    operations = [
        migrations.CreateModel(
            name='VehicleDataRefresh',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('started_at', models.DateTimeField()),
                ('finished_at', models.DateTimeField()),
                ('result', models.CharField(choices=[('succeeded', 'Succeeded'), ('failed', 'Failed')], max_length=10)),
                ('models_added', models.PositiveIntegerField(default=0)),
                ('models_changed', models.PositiveIntegerField(default=0, help_text='Models with a model year added or changed, or a year range moved.')),
                ('sent_to_queue', models.PositiveIntegerField(default=0, help_text='Model years that entered the review queue.')),
                ('held', models.PositiveIntegerField(default=0, help_text='Model years whose class or size the refresh would have changed, held in the review queue.')),
                ('message', models.TextField(blank=True, help_text='Why a failed refresh stopped.')),
            ],
            options={
                'verbose_name_plural': 'vehicle data refreshes',
                'ordering': ['-started_at'],
            },
        ),
    ]
