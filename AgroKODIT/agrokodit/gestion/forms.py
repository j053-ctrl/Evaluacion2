from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from bson import ObjectId
from datetime import date

from .models import PerfilUsuario


class PredioForm(forms.Form):
    ESTADOS = (('Activo', 'Activo'), ('Inactivo', 'Inactivo'))

    codigo = forms.RegexField(
        label='Código', regex=r'^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$', max_length=20,
        help_text='Entre 2 y 20 caracteres; puedes usar letras, números, guion y guion bajo.',
        error_messages={'invalid': 'Usa entre 2 y 20 caracteres válidos.'},
    )
    nombre = forms.CharField(label='Nombre del predio', max_length=120)
    ubicacion = forms.CharField(label='Dirección o sector', max_length=180)
    comuna = forms.CharField(max_length=80)
    region = forms.CharField(label='Región', max_length=80)
    superficie_hectareas = forms.DecimalField(
        label='Superficie (ha)', min_value=0.01, max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
    )
    encargado = forms.CharField(max_length=120, required=False)
    telefono = forms.CharField(
        label='Teléfono', max_length=20, required=False,
        help_text='Opcional. Ejemplo: +56 9 1234 5678.',
    )
    estado = forms.ChoiceField(choices=ESTADOS)
    observaciones = forms.CharField(
        required=False, max_length=500,
        widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            )

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()

    def clean_telefono(self):
        telefono = self.cleaned_data['telefono'].strip()
        if telefono and (not all(c.isdigit() or c in '+- ()' for c in telefono) or
                         sum(c.isdigit() for c in telefono) < 8):
            raise forms.ValidationError('Ingresa un teléfono válido con al menos 8 dígitos.')
        return telefono


class HuertoForm(forms.Form):
    ESTADOS = (('Activo', 'Activo'), ('En formación', 'En formación'), ('Inactivo', 'Inactivo'))
    SISTEMAS_RIEGO = (
        ('Goteo', 'Goteo'), ('Microaspersión', 'Microaspersión'),
        ('Aspersión', 'Aspersión'), ('Surco', 'Surco'), ('Otro', 'Otro'),
    )

    codigo = forms.RegexField(
        label='Código', regex=r'^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$', max_length=20,
        help_text='Entre 2 y 20 caracteres; puedes usar letras, números, guion y guion bajo.',
        error_messages={'invalid': 'Usa entre 2 y 20 caracteres válidos.'},
    )
    nombre = forms.CharField(label='Nombre del huerto', max_length=120)
    predio_id = forms.ChoiceField(label='Predio')
    especie = forms.CharField(label='Especie o cultivo', max_length=80)
    variedad = forms.CharField(max_length=80, required=False)
    superficie_hectareas = forms.DecimalField(
        label='Superficie (ha)', min_value=0.01, max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
    )
    anio_plantacion = forms.IntegerField(
        label='Año de plantación', min_value=1900, max_value=date.today().year,
        required=False, widget=forms.NumberInput(attrs={'min': '1900', 'max': date.today().year}),
    )
    sistema_riego = forms.ChoiceField(label='Sistema de riego', choices=SISTEMAS_RIEGO)
    estado = forms.ChoiceField(choices=ESTADOS)
    observaciones = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, predios=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['predio_id'].choices = [('', 'Selecciona un predio')] + [
            (str(predio['_id']), f"{predio.get('codigo', 'S/C')} — {predio.get('nombre', 'Sin nombre')}")
            for predio in predios
        ]
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            )

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()


class CuartelForm(forms.Form):
    ESTADOS = (
        ('Productivo', 'Productivo'), ('En formación', 'En formación'),
        ('En renovación', 'En renovación'), ('Inactivo', 'Inactivo'),
    )

    codigo = forms.RegexField(
        label='Código', regex=r'^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$', max_length=20,
        help_text='Entre 2 y 20 caracteres; puedes usar letras, números, guion y guion bajo.',
        error_messages={'invalid': 'Usa entre 2 y 20 caracteres válidos.'},
    )
    nombre = forms.CharField(label='Nombre o número del cuartel', max_length=120)
    huerto_id = forms.ChoiceField(label='Huerto al que pertenece')
    superficie_hectareas = forms.DecimalField(
        label='Superficie asignada (ha)', min_value=0.01, max_digits=12, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
    )
    numero_hileras = forms.IntegerField(
        label='Número de hileras', min_value=1,
        widget=forms.NumberInput(attrs={'min': '1'}),
    )
    numero_plantas = forms.IntegerField(
        label='Cantidad de plantas', min_value=1,
        widget=forms.NumberInput(attrs={'min': '1'}),
    )
    distancia_hileras_m = forms.DecimalField(
        label='Distancia entre hileras (m)', min_value=0.1, max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.1', 'min': '0.1'}),
    )
    distancia_plantas_m = forms.DecimalField(
        label='Distancia entre plantas (m)', min_value=0.1, max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={'step': '0.1', 'min': '0.1'}),
    )
    portainjerto = forms.CharField(max_length=80, required=False)
    sector_riego = forms.CharField(
        label='Sector o válvula de riego', max_length=80, required=False,
    )
    estado = forms.ChoiceField(choices=ESTADOS)
    observaciones = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, huertos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['huerto_id'].choices = [('', 'Selecciona un huerto')] + [
            (
                str(huerto['_id']),
                f"{huerto.get('codigo', 'S/C')} — {huerto.get('nombre', 'Sin nombre')}"
                f" ({huerto.get('predio_nombre', 'Predio no indicado')})",
            )
            for huerto in huertos
        ]
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            )

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()


class CuadrillaForm(forms.Form):
    TURNOS = (
        ('Jornada completa', 'Jornada completa'), ('Mañana', 'Mañana'),
        ('Tarde', 'Tarde'), ('Por tarea', 'Por tarea'),
    )
    ESTADOS = (('Activa', 'Activa'), ('Pausada', 'Pausada'), ('Inactiva', 'Inactiva'))

    codigo = forms.RegexField(
        label='Código', regex=r'^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$', max_length=20,
        help_text='Código interno único de la cuadrilla.',
        error_messages={'invalid': 'Usa entre 2 y 20 letras, números, guiones o guiones bajos.'},
    )
    nombre = forms.CharField(label='Nombre de la cuadrilla', max_length=120)
    jefe_id = forms.ChoiceField(label='Jefe de cuadrilla', required=False)
    integrantes = forms.MultipleChoiceField(
        label='Trabajadores integrantes', required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Cada trabajador puede pertenecer solamente a una cuadrilla.',
    )
    unidad_trabajo = forms.ChoiceField(label='Lugar de trabajo', required=False)
    labor_actual = forms.CharField(label='Labor o tarea actual', max_length=120)
    turno = forms.ChoiceField(choices=TURNOS)
    fecha_inicio = forms.DateField(
        label='Inicio de la asignación', required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    estado = forms.ChoiceField(choices=ESTADOS)
    observaciones = forms.CharField(
        required=False, max_length=500, widget=forms.Textarea(attrs={'rows': 3}),
    )

    def __init__(self, *args, trabajadores=(), unidades=(), **kwargs):
        super().__init__(*args, **kwargs)
        jefes = [t for t in trabajadores if t.get('rol') == 'Jefe de Cuadrilla']
        operarios = [t for t in trabajadores if t.get('rol') == 'Trabajador']
        etiqueta = lambda t: f"{t.get('nombre', '')} {t.get('apellido', '')} · {t.get('rut', 'Sin RUT')}".strip()
        self.fields['jefe_id'].choices = [('', 'Sin jefe asignado')] + [
            (str(t['_id']), etiqueta(t)) for t in jefes
        ]
        self.fields['integrantes'].choices = [
            (str(t['_id']), etiqueta(t)) for t in operarios
        ]
        self.fields['unidad_trabajo'].choices = [('', 'Sin lugar asignado')] + [
            (u['valor'], u['etiqueta']) for u in unidades
        ]
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = 'form-check-input'
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = (
                    'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
                )

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()


class ColleraForm(forms.Form):
    codigo = forms.RegexField(
        label='Código', regex=r'^[A-Za-z0-9][A-Za-z0-9_-]{1,19}$', max_length=20,
        help_text='Código único de la pareja.',
        error_messages={'invalid': 'Usa entre 2 y 20 letras, números, guiones o guiones bajos.'},
    )
    cuadrilla_id = forms.ChoiceField(label='Cuadrilla')
    trabajadores = forms.MultipleChoiceField(
        label='Trabajadores', widget=forms.CheckboxSelectMultiple,
        help_text='Selecciona exactamente dos trabajadores de la misma cuadrilla.',
    )
    activa = forms.BooleanField(label='Collera activa', required=False, initial=True)

    def __init__(self, *args, cuadrillas=(), trabajadores=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.trabajadores_disponibles = list(trabajadores)
        self.fields['cuadrilla_id'].choices = [('', 'Selecciona una cuadrilla')] + [
            (c.get('codigo', ''), f"{c.get('codigo', '')} — {c.get('nombre', 'Sin nombre')}")
            for c in cuadrillas
        ]
        self.fields['trabajadores'].choices = [
            (str(t['_id']), f"{t.get('nombre', '')} {t.get('apellido', '')} · {t.get('rut', 'Sin RUT')} · {t.get('cuadrilla_id', 'Sin cuadrilla')}")
            for t in self.trabajadores_disponibles if t.get('rol') == 'Trabajador'
        ]
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = (
                    'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
                )

    def clean_codigo(self):
        return self.cleaned_data['codigo'].strip().upper()

    def clean(self):
        data = super().clean()
        ids = data.get('trabajadores') or []
        cuadrilla = data.get('cuadrilla_id')
        if len(ids) != 2 or len(set(ids)) != 2:
            self.add_error('trabajadores', 'Una collera debe tener exactamente dos trabajadores.')
        por_id = {str(t['_id']): t for t in self.trabajadores_disponibles}
        if cuadrilla and any(por_id.get(id, {}).get('cuadrilla_id') != cuadrilla for id in ids):
            self.add_error('trabajadores', 'Los dos trabajadores deben pertenecer a la cuadrilla seleccionada.')
        return data


class JornadaForm(forms.Form):
    ASISTENCIAS = (
        ('Presente', 'Presente'), ('Atraso', 'Atraso'),
        ('Ausente', 'Ausente'), ('Permiso', 'Permiso'),
    )
    CALIDADES = (
        ('Primera', 'Primera'), ('Segunda', 'Segunda'),
        ('Descarte', 'Descarte'), ('Sin clasificación', 'Sin clasificación'),
    )

    fecha = forms.DateField(label='Fecha', initial=date.today, widget=forms.DateInput(attrs={'type': 'date'}))
    trabajador_id = forms.ChoiceField(label='Trabajador')
    cuartel_id = forms.ChoiceField(label='Cuartel')
    asistencia = forms.ChoiceField(choices=ASISTENCIAS)
    hora_entrada = forms.TimeField(label='Entrada', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    hora_salida = forms.TimeField(label='Salida', required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    labor = forms.CharField(label='Labor realizada', max_length=120)
    kilos = forms.DecimalField(label='Kilos cosechados', min_value=0, max_digits=10, decimal_places=2,
                               initial=0, widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0'}))
    calidad = forms.ChoiceField(choices=CALIDADES)
    capachos = forms.IntegerField(label='Capachos cosechados', min_value=0, initial=0, required=False)
    bines = forms.IntegerField(label='Bines cosechados', min_value=0, initial=0, required=False)
    bines_con_hojas = forms.CharField(
        label='Códigos de los bines entregados con hojas', required=False, max_length=1000,
        help_text='Escribe un código por línea o sepáralos con comas. Deja vacío si ninguno tenía hojas.',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    perdidas_kg = forms.DecimalField(label='Pérdidas (kg)', min_value=0, max_digits=10, decimal_places=2,
                                     initial=0, widget=forms.NumberInput(attrs={'step': '0.01', 'min': '0'}))
    observaciones = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, trabajadores=(), cuarteles=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['trabajador_id'].choices = [('', 'Selecciona un trabajador')] + [
            (str(t['_id']), f"{t.get('nombre', '')} {t.get('apellido', '')} · {t.get('cuadrilla_id', 'Sin cuadrilla')}")
            for t in trabajadores if t.get('rol') in ('Trabajador', 'Planillera')
        ]
        self.fields['cuartel_id'].choices = [('', 'Selecciona un cuartel')] + [
            (str(c['_id']), f"{c.get('codigo', '')} — {c.get('nombre', 'Sin nombre')} ({c.get('huerto_nombre', 'Sin huerto')})")
            for c in cuarteles
        ]
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            )

    def clean(self):
        data = super().clean()
        entrada, salida = data.get('hora_entrada'), data.get('hora_salida')
        asistencia = data.get('asistencia')
        if asistencia in ('Presente', 'Atraso') and (not entrada or not salida):
            self.add_error('hora_entrada', 'Indica la entrada y salida de una jornada trabajada.')
        if entrada and salida and salida <= entrada:
            self.add_error('hora_salida', 'La salida debe ser posterior a la entrada.')
        if asistencia in ('Ausente', 'Permiso') and (data.get('kilos') or 0) > 0:
            self.add_error('kilos', 'Una ausencia o permiso no puede registrar producción.')
        if (data.get('perdidas_kg') or 0) > (data.get('kilos') or 0):
            self.add_error('perdidas_kg', 'Las pérdidas no pueden superar los kilos cosechados.')
        for campo in ('capachos', 'bines'):
            if campo not in self.errors:
                data[campo] = data.get(campo) or 0
                if asistencia in ('Ausente', 'Permiso') and data[campo] > 0:
                    self.add_error(campo, 'Una ausencia o permiso no puede registrar cosecha.')
        codigos = [codigo.strip() for codigo in data.get('bines_con_hojas', '').replace(',', '\n').splitlines() if codigo.strip()]
        if len(codigos) != len(set(codigos)):
            self.add_error('bines_con_hojas', 'No repitas el código de un bin.')
        if len(codigos) > (data.get('bines') or 0):
            self.add_error('bines_con_hojas', 'Los bines con hojas no pueden superar los bines cosechados.')
        if asistencia in ('Ausente', 'Permiso') and codigos:
            self.add_error('bines_con_hojas', 'Una ausencia o permiso no puede registrar entregas de bines.')
        data['bines_con_hojas'] = codigos
        return data


class CrearAdministradorForm(forms.Form):
    rut = forms.RegexField(
        label='RUT del administrador', regex=r'^\d{7,8}-[\dkK]$',
        help_text='Se utilizará para iniciar sesión. Escríbelo sin puntos.',
    )
    nombre = forms.CharField(label='Nombre', max_length=150)
    password1 = forms.CharField(label='Contraseña', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean_rut(self):
        rut = self.cleaned_data['rut'].upper()
        numero, digito = rut.split('-')
        suma = sum(int(n) * (2 + i % 6) for i, n in enumerate(reversed(numero)))
        valor = 11 - suma % 11
        esperado = '0' if valor == 11 else 'K' if valor == 10 else str(valor)
        if digito != esperado:
            raise forms.ValidationError('El dígito verificador del RUT no es válido.')
        if get_user_model().objects.filter(username=rut).exists():
            raise forms.ValidationError('Ya existe una cuenta con este RUT.')
        return rut

    def clean(self):
        data = super().clean()
        password1 = data.get('password1')
        password2 = data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        if password1:
            try:
                validate_password(password1)
            except ValidationError as error:
                self.add_error('password1', error)
        return data

    def save(self, collection):
        rut = self.cleaned_data['rut']
        if collection.find_one({'rut': rut}) is not None:
            raise forms.ValidationError('Ya existe una cuenta con este RUT.')

        usuario = None
        insertado = False
        try:
            with transaction.atomic():
                usuario = get_user_model().objects.create_user(
                    username=rut,
                    first_name=self.cleaned_data['nombre'],
                    is_staff=True,
                    is_superuser=True,
                )
                usuario.set_unusable_password()
                usuario.save(update_fields=['password'])
                collection.insert_one({
                    'rut': rut,
                    'username': rut,
                    'nombre': self.cleaned_data['nombre'],
                    'rol': 'administrador',
                    'password': make_password(self.cleaned_data['password1']),
                    'activo': True,
                })
                insertado = True
        except Exception:
            if insertado:
                collection.delete_one({'rut': rut})
            raise
        return usuario


class CrearCuentaForm(UserCreationForm):
    primer_nombre = forms.CharField(label='Primer nombre', max_length=70)
    segundo_nombre = forms.CharField(label='Segundo nombre', max_length=70, required=False)
    apellido_paterno = forms.CharField(label='Apellido paterno', max_length=70)
    apellido_materno = forms.CharField(label='Apellido materno', max_length=70, required=False)
    collera_id = forms.CharField(label='Código de collera', max_length=100, required=False,
                                help_text='Código de la pareja de trabajadores, si corresponde.')
    rut = forms.RegexField(label='RUT', regex=r'^\d{7,8}-[\dkK]$', help_text='Sin puntos y con guion. Ejemplo: 12345678-5.')
    rol = forms.ChoiceField(label='Tipo de cuenta', choices=PerfilUsuario._meta.get_field('rol').choices)
    cuadrilla_id = forms.CharField(label='Código de cuadrilla', max_length=100, required=False,
                                  help_text='Obligatorio para el jefe. Usa el mismo código asignado a los trabajadores de su equipo.')

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('primer_nombre', 'segundo_nombre', 'apellido_paterno', 'apellido_materno', 'rut', 'rol', 'cuadrilla_id', 'collera_id')
        labels = {'username': 'Nombre de usuario', 'first_name': 'Nombre', 'last_name': 'Apellido'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].label = 'Contraseña'
        self.fields['password2'].label = 'Confirmar contraseña'
        self.fields['password1'].help_text = 'Usa al menos 8 caracteres. Evita contraseñas comunes, solo números o similares al usuario.'
        self.fields['password2'].help_text = 'Escribe nuevamente la contraseña.'
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'

    def clean(self):
        data = super().clean()
        if data.get('rol') == 'jefe' and not data.get('cuadrilla_id'):
            self.add_error('cuadrilla_id', 'Indica la cuadrilla a cargo del jefe.')
        return data

    def clean_collera_id(self):
        if self.cleaned_data.get('rol') != 'trabajador':
            return ''
        return self.cleaned_data['collera_id']

    def clean_cuadrilla_id(self):
        if self.cleaned_data.get('rol') in ('recursos_humanos', 'gerencia', 'cuenta_plenillera'):
            return ''
        return self.cleaned_data['cuadrilla_id']

    def clean_rut(self):
        rut = self.cleaned_data['rut'].upper()
        numero, digito = rut.split('-')
        suma = sum(int(n) * (2 + i % 6) for i, n in enumerate(reversed(numero)))
        valor = 11 - suma % 11
        esperado = '0' if valor == 11 else 'K' if valor == 10 else str(valor)
        if digito != esperado:
            raise forms.ValidationError('El dígito verificador del RUT no es válido.')
        if get_user_model().objects.filter(username=rut).exists():
            raise forms.ValidationError('Ya existe una cuenta con este RUT.')
        return rut

    def _post_clean(self):
        self.instance.username = self.cleaned_data.get('rut', '')
        self.instance.first_name = ' '.join(filter(None, [self.cleaned_data.get('primer_nombre'), self.cleaned_data.get('segundo_nombre')]))
        self.instance.last_name = ' '.join(filter(None, [self.cleaned_data.get('apellido_paterno'), self.cleaned_data.get('apellido_materno')]))
        super()._post_clean()

    def save(self, collection):
        if collection.find_one({'rut': self.cleaned_data['rut']}) is not None:
            raise forms.ValidationError('Ya existe una ficha con este RUT. No se creó una cuenta duplicada.')
        from .db import usuarios_collection

        trabajador_id = ObjectId()
        rol = self.cleaned_data['rol']
        ficha_insertada = False
        cuenta_insertada = False
        if usuarios_collection.find_one({'rut': self.cleaned_data['rut']}) is not None:
            raise forms.ValidationError('Ya existe una cuenta de usuario con este RUT.')
        try:
            with transaction.atomic():
                usuario = super().save(commit=False)
                usuario.is_staff = False
                usuario.is_superuser = False
                usuario.set_unusable_password()
                usuario.save()
                PerfilUsuario.objects.create(
                    usuario=usuario, rol=rol, trabajador_id=str(trabajador_id),
                    cuadrilla_id=self.cleaned_data['cuadrilla_id'] if rol == 'jefe' else '',
                )
                collection.insert_one({
                    '_id': trabajador_id, 'rut': self.cleaned_data['rut'],
                    'nombre': usuario.first_name, 'apellido': usuario.last_name,
                    **{campo: self.cleaned_data[campo] for campo in ('primer_nombre', 'segundo_nombre', 'apellido_paterno', 'apellido_materno')},
                    'rol': dict(PerfilUsuario._meta.get_field('rol').choices)[rol],
                    'cuadrilla_id': self.cleaned_data['cuadrilla_id'], 'collera_id': self.cleaned_data['collera_id'],
                    'ganancia_dia': 0,
                })
                ficha_insertada = True
                usuarios_collection.insert_one({
                    '_id': ObjectId(),
                    'trabajador_id': trabajador_id,
                    'rut': self.cleaned_data['rut'],
                    'nombre': usuario.first_name,
                    'apellido': usuario.last_name,
                    'rol': rol,
                    'cuadrilla_id': self.cleaned_data['cuadrilla_id'] if rol == 'jefe' else '',
                    'password': make_password(self.cleaned_data['password1']),
                    'activo': True,
                })
                cuenta_insertada = True
        except Exception:
            if cuenta_insertada:
                usuarios_collection.delete_one({'trabajador_id': trabajador_id})
            if ficha_insertada:
                collection.delete_one({'_id': trabajador_id})
            raise
        return usuario
