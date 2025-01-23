# Generated by Django 5.1.3 on 2024-12-16 19:46

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Patologia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('id_api', models.IntegerField(unique=True)),
                ('nombre', models.CharField(max_length=255)),
                ('costo_mensual', models.DecimalField(decimal_places=0, max_digits=10)),
            ],
        ),
    ]
