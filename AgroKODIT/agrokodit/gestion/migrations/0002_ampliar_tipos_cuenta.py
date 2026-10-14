from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='perfilusuario',
            name='rol',
            field=models.CharField(
                choices=[
                    ('jefe', 'Jefe de cuadrilla'),
                    ('trabajador', 'Trabajador'),
                    ('recursos_humanos', 'Recursos Humanos'),
                    ('gerencia', 'Gerencia'),
                ],
                default='trabajador',
                max_length=20,
            ),
        ),
    ]
