from django.db import models

from django.conf import settings
from django.core.validators import RegexValidator


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='perfil_agricola')
    rol = models.CharField(max_length=20, choices=[
        ('jefe', 'Jefe de cuadrilla'),
        ('trabajador', 'Trabajador'),
        ('recursos_humanos', 'Recursos Humanos'),
        ('gerencia', 'Gerencia'),
        ('cuenta_plenillera', 'Planillera'),
    ], default='trabajador')
    trabajador_id = models.CharField(
        'ID del trabajador en MongoDB', max_length=24, unique=True, null=True, blank=True,
        validators=[RegexValidator(r'^[0-9a-f]{24}$', 'Ingresa un ObjectId de MongoDB válido en minúsculas.')],
    )
    cuadrilla_id = models.CharField('Cuadrilla a cargo (jefe)', max_length=100, blank=True)

    def save(self, *args, **kwargs):
        self.trabajador_id = self.trabajador_id or None
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.usuario} - {self.get_rol_display()}'
