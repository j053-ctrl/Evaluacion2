from .db import (
    administradores_collection, cuadrillas_collection, cuarteles_collection,
    huertos_collection, predios_collection, trabajadores_collection,
    colleras_collection, jornadas_collection, usuarios_collection,
)
from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_POST, require_http_methods
from bson import ObjectId
from bson.errors import InvalidId
from .permissions import administrador_required, equipo_required, perfil_usuario, rol_usuario
from .forms import (
    CrearAdministradorForm, CrearCuentaForm, CuadrillaForm, CuartelForm,
    HuertoForm, PredioForm, ColleraForm, JornadaForm,
)
from .models import PerfilUsuario
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.exceptions import PermissionDenied
from pymongo.errors import PyMongoError
from datetime import datetime, timezone
import re
import csv


ROL_INTERNO_POR_NOMBRE = {
    'Trabajador': 'trabajador',
    'Jefe de Cuadrilla': 'jefe',
    'Recursos Humanos': 'recursos_humanos',
    'Gerencia': 'gerencia',
    'Planillera': 'cuenta_plenillera',
}


def sincronizar_cuenta_por_rol(perfil, trabajador, datos, password_hash=None):
    """Mantiene la credencial y el rol dentro de la colección usuarios."""
    nuevo_rol = ROL_INTERNO_POR_NOMBRE[datos['rol']]
    filtro = {'trabajador_id': trabajador['_id']}
    cuenta = usuarios_collection.find_one(filtro)
    password_guardada = password_hash or (cuenta or {}).get('password') or trabajador.get('password')
    cambios = {
        'trabajador_id': trabajador['_id'],
        'rut': datos['rut'].upper(),
        'nombre': datos['nombre'],
        'apellido': datos['apellido'],
        'rol': nuevo_rol,
        'cuadrilla_id': datos.get('cuadrilla_id', '') if nuevo_rol == 'jefe' else '',
        'activo': True,
    }
    if password_guardada:
        cambios['password'] = password_guardada

    if cuenta:
        usuarios_collection.update_one({'_id': cuenta['_id']}, {'$set': cambios})
    elif password_guardada:
        usuarios_collection.insert_one({'_id': ObjectId(), **cambios})

    perfil.rol = nuevo_rol
    perfil.cuadrilla_id = datos.get('cuadrilla_id', '') if nuevo_rol == 'jefe' else ''
    perfil.save(update_fields=['rol', 'cuadrilla_id'])


def recuperar_cuenta(request):
    return render(request, 'gestion/recuperar_cuenta.html')


@administrador_required
@require_http_methods(['GET', 'POST'])
def administradores(request):
    form = CrearAdministradorForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            form.save(usuarios_collection)
        except ValidationError as error:
            form.add_error(None, error)
        except (PyMongoError, IntegrityError):
            form.add_error(None, 'No se pudo crear la cuenta de administrador.')
        else:
            messages.success(request, 'Cuenta de administrador creada en la colección usuarios de MongoDB Atlas.')
            return redirect('administradores')

    try:
        lista_administradores = list(usuarios_collection.find(
            {'rol': 'administrador'}, {'password': 0},
        ))
    except PyMongoError:
        lista_administradores = []
        messages.error(request, 'No se pudo consultar la colección de administradores.')
    return render(request, 'gestion/administradores.html', {
        'form': form, 'administradores': lista_administradores,
    })


@administrador_required
@require_http_methods(['GET', 'POST'])
def crear_cuenta(request):
    form = CrearCuentaForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            usuario = form.save(trabajadores_collection)
        except ValidationError as error:
            form.add_error(None, error)
        except (PyMongoError, IntegrityError):
            form.add_error(None, 'No se pudo completar la creación de la cuenta. Revisa la conexión y los datos antes de reintentar.')
        else:
            messages.success(
                request,
                f'Cuenta {usuario.username} creada como {usuario.perfil_agricola.get_rol_display()} '
                'y guardada en la colección usuarios de MongoDB Atlas.',
            )
            return redirect('crear_cuenta')
    return render(request, 'gestion/crear_cuenta.html', {'form': form})


def trabajador_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Trabajador no encontrado')


@login_required
@require_http_methods(['GET', 'POST'])
def editar_trabajador(request, id):
    rol_acceso = rol_usuario(request.user)
    if rol_acceso not in ('administrador', 'gerencia'):
        raise PermissionDenied('Solo Administración y Gerencia pueden editar estos datos.')
    es_administrador = rol_acceso == 'administrador'
    object_id = trabajador_object_id(id)
    trabajador = trabajadores_collection.find_one({'_id': object_id})
    if trabajador is None:
        raise Http404('Trabajador no encontrado')

    perfil = PerfilUsuario.objects.select_related('usuario').filter(trabajador_id=str(object_id)).first()
    cambiar_password = request.user.is_superuser and request.method == 'POST' and bool(
        request.POST.get('new_password1') or request.POST.get('new_password2')
    )
    password_form = SetPasswordForm(
        perfil.usuario, request.POST if cambiar_password else None
    ) if perfil and request.user.is_superuser else None
    if password_form:
        for campo in password_form.fields.values():
            campo.required = False
            campo.widget.attrs['class'] = 'form-control'

    error = None
    if request.method == 'POST':
        codigos = {
            campo: request.POST.get(campo, '').strip()
            for campo in ('cuadrilla_id', 'collera_id')
        }
        if not es_administrador:
            resultado = trabajadores_collection.update_one(
                {'_id': object_id}, {'$set': codigos}
            )
            if not resultado.matched_count:
                raise Http404('Trabajador no encontrado')
            return redirect('trabajadores')

        datos = {
            campo: request.POST.get(campo, '').strip()
            for campo in ('rut', 'nombre', 'apellido', 'rol')
        }
        datos.update(codigos)
        ganancia_dia = request.POST.get('ganancia_dia', '').strip()
        incluye_ganancia = 'ganancia_dia' in request.POST
        if not all(datos[campo] for campo in ('rut', 'nombre', 'apellido', 'rol')):
            error = 'Completa todos los campos.'
        elif incluye_ganancia and not ganancia_dia.isdigit():
            error = 'La ganancia del día debe ser un monto entero igual o mayor que cero.'
        elif datos['rol'] not in (
            'Trabajador', 'Jefe de Cuadrilla', 'Recursos Humanos', 'Gerencia', 'Planillera',
        ):
            error = 'Selecciona un rol válido.'
        elif cambiar_password and not perfil:
            error = 'Este trabajador no tiene una cuenta vinculada.'
        elif cambiar_password and not password_form.is_valid():
            error = 'Revisa los campos de la nueva contraseña.'
        elif cambiar_password and not all(request.POST.get(campo) for campo in ('new_password1', 'new_password2')):
            error = 'Escribe y confirma la nueva contraseña.'
        else:
            if incluye_ganancia:
                datos['ganancia_dia'] = int(ganancia_dia)
            password_hash = make_password(password_form.cleaned_data['new_password1']) if cambiar_password else None
            resultado = trabajadores_collection.update_one(
                {'_id': object_id}, {'$set': datos}
            )
            if not resultado.matched_count:
                raise Http404('Trabajador no encontrado')
            if perfil:
                sincronizar_cuenta_por_rol(perfil, trabajador, datos, password_hash)
            if cambiar_password:
                perfil.usuario.set_unusable_password()
                perfil.usuario.save(update_fields=['password'])
            return redirect('trabajadores')
        trabajador.update(datos)

    return render(request, 'gestion/agregar_trabajador.html', {
        'editando': True,
        'trabajador': trabajador,
        'error': error,
        'password_form': password_form,
        'edicion_solo_codigos': not es_administrador,
    })


@administrador_required
@require_POST
def eliminar_trabajador(request, id):
    object_id = trabajador_object_id(id)
    with transaction.atomic():
        perfil = PerfilUsuario.objects.select_related('usuario').filter(trabajador_id=str(object_id)).first()
        if perfil and (perfil.usuario.is_superuser or perfil.usuario.is_staff or perfil.usuario_id == request.user.pk):
            raise PermissionDenied('No puedes eliminar una cuenta administrativa desde Trabajadores.')
        usuarios_collection.delete_one({'trabajador_id': object_id})
        resultado = trabajadores_collection.delete_one({'_id': object_id})
        if not resultado.deleted_count and not perfil:
            raise Http404('Trabajador no encontrado')
        if perfil:
            perfil.usuario.delete()
    return redirect('trabajadores')

@require_POST
def cerrar_sesion(request):
    logout(request)
    return redirect('login')


@login_required
def inicio(request):
    if not request.user.is_superuser:
        return render(request, 'gestion/panel_operativo.html', {
            'rol': rol_usuario(request.user),
            'perfil': perfil_usuario(request.user),
        })
    return render(request, 'gestion/inicio.html')

@administrador_required
def agregar_trabajador(request):
    return redirect('crear_cuenta')

def predio_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Predio no encontrado')


def datos_predio(form):
    return {
        'codigo': form.cleaned_data['codigo'],
        'nombre': form.cleaned_data['nombre'].strip(),
        'ubicacion': form.cleaned_data['ubicacion'].strip(),
        'comuna': form.cleaned_data['comuna'].strip(),
        'region': form.cleaned_data['region'].strip(),
        'superficie_hectareas': float(form.cleaned_data['superficie_hectareas']),
        'encargado': form.cleaned_data['encargado'].strip(),
        'telefono': form.cleaned_data['telefono'],
        'estado': form.cleaned_data['estado'],
        'observaciones': form.cleaned_data['observaciones'].strip(),
    }


def contexto_predios(request, form=None, predio_editando=None):
    busqueda = request.GET.get('q', '').strip()
    filtro = {}
    if busqueda:
        patron = re.escape(busqueda)
        filtro = {'$or': [
            {campo: {'$regex': patron, '$options': 'i'}}
            for campo in ('codigo', 'nombre', 'ubicacion', 'comuna', 'region', 'encargado')
        ]}
    try:
        predios = list(predios_collection.find(filtro).sort('nombre', 1))
    except PyMongoError:
        predios = []
        messages.error(request, 'No se pudo consultar los predios. Revisa la conexión con MongoDB Atlas.')
    for predio in predios:
        predio['id'] = str(predio['_id'])
    return {
        'form': form or PredioForm(initial={'estado': 'Activo'}),
        'predios': predios,
        'predio_editando': predio_editando,
        'busqueda': busqueda,
        'total_predios': len(predios),
        'predios_activos': sum(p.get('estado') == 'Activo' for p in predios),
        'superficie_total': sum(float(p.get('superficie_hectareas') or 0) for p in predios),
    }


@administrador_required
@require_http_methods(['GET', 'POST'])
def predios(request):
    form = PredioForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        datos = datos_predio(form)
        try:
            if predios_collection.find_one({'codigo': datos['codigo']}) is not None:
                form.add_error('codigo', 'Ya existe un predio con este código.')
            else:
                ahora = datetime.now(timezone.utc)
                predios_collection.insert_one({**datos, 'creado_en': ahora, 'actualizado_en': ahora})
                messages.success(request, f'Predio “{datos["nombre"]}” registrado correctamente.')
                return redirect('predios')
        except PyMongoError:
            form.add_error(None, 'No se pudo guardar el predio. Revisa la conexión e inténtalo nuevamente.')
    return render(request, 'gestion/predios.html', contexto_predios(request, form))


@administrador_required
@require_http_methods(['GET', 'POST'])
def editar_predio(request, id):
    object_id = predio_object_id(id)
    try:
        predio = predios_collection.find_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo consultar el predio.')
        return redirect('predios')
    if predio is None:
        raise Http404('Predio no encontrado')

    form = PredioForm(request.POST or None, initial=predio)
    if request.method == 'POST' and form.is_valid():
        datos = datos_predio(form)
        try:
            duplicado = predios_collection.find_one({
                'codigo': datos['codigo'], '_id': {'$ne': object_id},
            })
            if duplicado is not None:
                form.add_error('codigo', 'Ya existe otro predio con este código.')
            else:
                resultado = predios_collection.update_one(
                    {'_id': object_id},
                    {'$set': {**datos, 'actualizado_en': datetime.now(timezone.utc)}},
                )
                if not resultado.matched_count:
                    raise Http404('Predio no encontrado')
                messages.success(request, f'Predio “{datos["nombre"]}” actualizado correctamente.')
                return redirect('predios')
        except PyMongoError:
            form.add_error(None, 'No se pudo actualizar el predio. Inténtalo nuevamente.')
    predio['id'] = str(predio['_id'])
    return render(request, 'gestion/predios.html', contexto_predios(request, form, predio))


@administrador_required
@require_POST
def eliminar_predio(request, id):
    object_id = predio_object_id(id)
    try:
        if huertos_collection.find_one({'predio_id': object_id}) is not None:
            messages.error(request, 'No se puede eliminar el predio porque tiene huertos asociados.')
            return redirect('predios')
        resultado = predios_collection.delete_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo eliminar el predio. Inténtalo nuevamente.')
    else:
        if not resultado.deleted_count:
            raise Http404('Predio no encontrado')
        messages.success(request, 'Predio eliminado correctamente.')
    return redirect('predios')

def huerto_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Huerto no encontrado')


def obtener_predios_para_huerto(request):
    try:
        return list(predios_collection.find({}, {'codigo': 1, 'nombre': 1}).sort('nombre', 1))
    except PyMongoError:
        messages.error(request, 'No se pudo cargar la lista de predios.')
        return []


def datos_huerto(form, predio):
    return {
        'codigo': form.cleaned_data['codigo'],
        'nombre': form.cleaned_data['nombre'].strip(),
        'predio_id': predio['_id'],
        'predio_codigo': predio.get('codigo', ''),
        'predio_nombre': predio.get('nombre', ''),
        'especie': form.cleaned_data['especie'].strip(),
        'variedad': form.cleaned_data['variedad'].strip(),
        'superficie_hectareas': float(form.cleaned_data['superficie_hectareas']),
        'anio_plantacion': form.cleaned_data['anio_plantacion'],
        'sistema_riego': form.cleaned_data['sistema_riego'],
        'estado': form.cleaned_data['estado'],
        'observaciones': form.cleaned_data['observaciones'].strip(),
    }


def contexto_huertos(request, predios, form=None, huerto_editando=None):
    busqueda = request.GET.get('q', '').strip()
    filtro = {}
    if busqueda:
        patron = re.escape(busqueda)
        filtro = {'$or': [
            {campo: {'$regex': patron, '$options': 'i'}}
            for campo in ('codigo', 'nombre', 'predio_codigo', 'predio_nombre', 'especie', 'variedad')
        ]}
    try:
        huertos = list(huertos_collection.find(filtro).sort('nombre', 1))
    except PyMongoError:
        huertos = []
        messages.error(request, 'No se pudo consultar los huertos. Revisa la conexión con MongoDB Atlas.')
    for huerto in huertos:
        huerto['id'] = str(huerto['_id'])
    return {
        'form': form or HuertoForm(predios=predios, initial={'estado': 'Activo'}),
        'huertos': huertos,
        'huerto_editando': huerto_editando,
        'busqueda': busqueda,
        'total_huertos': len(huertos),
        'huertos_activos': sum(h.get('estado') == 'Activo' for h in huertos),
        'superficie_total': sum(float(h.get('superficie_hectareas') or 0) for h in huertos),
        'hay_predios': bool(predios),
    }


@administrador_required
@require_http_methods(['GET', 'POST'])
def huertos(request):
    predios = obtener_predios_para_huerto(request)
    form = HuertoForm(request.POST if request.method == 'POST' else None, predios=predios)
    if request.method == 'POST' and form.is_valid():
        try:
            predio = predios_collection.find_one({'_id': ObjectId(form.cleaned_data['predio_id'])})
            if predio is None:
                form.add_error('predio_id', 'El predio seleccionado ya no existe.')
            elif huertos_collection.find_one({'codigo': form.cleaned_data['codigo']}) is not None:
                form.add_error('codigo', 'Ya existe un huerto con este código.')
            else:
                ahora = datetime.now(timezone.utc)
                datos = datos_huerto(form, predio)
                huertos_collection.insert_one({**datos, 'creado_en': ahora, 'actualizado_en': ahora})
                messages.success(request, f'Huerto “{datos["nombre"]}” registrado correctamente.')
                return redirect('huertos')
        except (InvalidId, PyMongoError):
            form.add_error(None, 'No se pudo guardar el huerto. Revisa la conexión e inténtalo nuevamente.')
    return render(request, 'gestion/huertos.html', contexto_huertos(request, predios, form))


@administrador_required
@require_http_methods(['GET', 'POST'])
def editar_huerto(request, id):
    object_id = huerto_object_id(id)
    predios = obtener_predios_para_huerto(request)
    try:
        huerto = huertos_collection.find_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo consultar el huerto.')
        return redirect('huertos')
    if huerto is None:
        raise Http404('Huerto no encontrado')
    inicial = {**huerto, 'predio_id': str(huerto.get('predio_id', ''))}
    form = HuertoForm(request.POST or None, predios=predios, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            predio = predios_collection.find_one({'_id': ObjectId(form.cleaned_data['predio_id'])})
            duplicado = huertos_collection.find_one({
                'codigo': form.cleaned_data['codigo'], '_id': {'$ne': object_id},
            })
            if predio is None:
                form.add_error('predio_id', 'El predio seleccionado ya no existe.')
            elif duplicado is not None:
                form.add_error('codigo', 'Ya existe otro huerto con este código.')
            else:
                datos = datos_huerto(form, predio)
                resultado = huertos_collection.update_one(
                    {'_id': object_id},
                    {'$set': {**datos, 'actualizado_en': datetime.now(timezone.utc)}},
                )
                if not resultado.matched_count:
                    raise Http404('Huerto no encontrado')
                messages.success(request, f'Huerto “{datos["nombre"]}” actualizado correctamente.')
                return redirect('huertos')
        except (InvalidId, PyMongoError):
            form.add_error(None, 'No se pudo actualizar el huerto. Inténtalo nuevamente.')
    huerto['id'] = str(huerto['_id'])
    return render(request, 'gestion/huertos.html', contexto_huertos(request, predios, form, huerto))


@administrador_required
@require_POST
def eliminar_huerto(request, id):
    object_id = huerto_object_id(id)
    try:
        if cuarteles_collection.find_one({'huerto_id': object_id}) is not None:
            messages.error(request, 'No se puede eliminar el huerto porque tiene cuarteles asociados.')
            return redirect('huertos')
        resultado = huertos_collection.delete_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo eliminar el huerto. Inténtalo nuevamente.')
    else:
        if not resultado.deleted_count:
            raise Http404('Huerto no encontrado')
        messages.success(request, 'Huerto eliminado correctamente.')
    return redirect('huertos')

def cuartel_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Cuartel no encontrado')


def obtener_huertos_para_cuartel(request):
    try:
        campos = {
            'codigo': 1, 'nombre': 1, 'predio_nombre': 1,
            'especie': 1, 'variedad': 1, 'superficie_hectareas': 1,
        }
        return list(huertos_collection.find({}, campos).sort('nombre', 1))
    except PyMongoError:
        messages.error(request, 'No se pudo cargar la lista de huertos.')
        return []


def datos_cuartel(form, huerto):
    return {
        'codigo': form.cleaned_data['codigo'],
        'nombre': form.cleaned_data['nombre'].strip(),
        'huerto_id': huerto['_id'],
        'huerto_codigo': huerto.get('codigo', ''),
        'huerto_nombre': huerto.get('nombre', ''),
        'predio_nombre': huerto.get('predio_nombre', ''),
        'especie': huerto.get('especie', ''),
        'variedad': huerto.get('variedad', ''),
        'superficie_hectareas': float(form.cleaned_data['superficie_hectareas']),
        'numero_hileras': form.cleaned_data['numero_hileras'],
        'numero_plantas': form.cleaned_data['numero_plantas'],
        'distancia_hileras_m': float(form.cleaned_data['distancia_hileras_m']),
        'distancia_plantas_m': float(form.cleaned_data['distancia_plantas_m']),
        'portainjerto': form.cleaned_data['portainjerto'].strip(),
        'sector_riego': form.cleaned_data['sector_riego'].strip(),
        'estado': form.cleaned_data['estado'],
        'observaciones': form.cleaned_data['observaciones'].strip(),
    }


def superficie_disponible_cuartel(huerto, excluir_id=None):
    filtro = {'huerto_id': huerto['_id']}
    if excluir_id is not None:
        filtro['_id'] = {'$ne': excluir_id}
    asignada = sum(
        float(c.get('superficie_hectareas') or 0)
        for c in cuarteles_collection.find(filtro, {'superficie_hectareas': 1})
    )
    return max(0, float(huerto.get('superficie_hectareas') or 0) - asignada)


def contexto_cuarteles(request, huertos, form=None, cuartel_editando=None):
    busqueda = request.GET.get('q', '').strip()
    filtro = {}
    if busqueda:
        patron = re.escape(busqueda)
        filtro = {'$or': [
            {campo: {'$regex': patron, '$options': 'i'}}
            for campo in (
                'codigo', 'nombre', 'huerto_codigo', 'huerto_nombre',
                'predio_nombre', 'especie', 'variedad', 'sector_riego',
            )
        ]}
    try:
        cuarteles = list(cuarteles_collection.find(filtro).sort('nombre', 1))
    except PyMongoError:
        cuarteles = []
        messages.error(request, 'No se pudo consultar los cuarteles. Revisa la conexión con MongoDB Atlas.')
    for cuartel in cuarteles:
        cuartel['id'] = str(cuartel['_id'])
        superficie = float(cuartel.get('superficie_hectareas') or 0)
        cuartel['densidad_plantas'] = round(cuartel.get('numero_plantas', 0) / superficie) if superficie else 0
    return {
        'form': form or CuartelForm(huertos=huertos, initial={'estado': 'Productivo'}),
        'cuarteles': cuarteles,
        'cuartel_editando': cuartel_editando,
        'busqueda': busqueda,
        'total_cuarteles': len(cuarteles),
        'cuarteles_productivos': sum(c.get('estado') == 'Productivo' for c in cuarteles),
        'total_plantas': sum(int(c.get('numero_plantas') or 0) for c in cuarteles),
        'superficie_total': sum(float(c.get('superficie_hectareas') or 0) for c in cuarteles),
        'hay_huertos': bool(huertos),
    }


@administrador_required
@require_http_methods(['GET', 'POST'])
def cuarteles(request):
    huertos = obtener_huertos_para_cuartel(request)
    form = CuartelForm(request.POST if request.method == 'POST' else None, huertos=huertos)
    if request.method == 'POST' and form.is_valid():
        try:
            huerto = huertos_collection.find_one({'_id': ObjectId(form.cleaned_data['huerto_id'])})
            if huerto is None:
                form.add_error('huerto_id', 'El huerto seleccionado ya no existe.')
            elif cuarteles_collection.find_one({'codigo': form.cleaned_data['codigo']}) is not None:
                form.add_error('codigo', 'Ya existe un cuartel con este código.')
            else:
                disponible = superficie_disponible_cuartel(huerto)
                solicitada = float(form.cleaned_data['superficie_hectareas'])
                if solicitada > disponible:
                    form.add_error(
                        'superficie_hectareas',
                        f'El huerto solo tiene {disponible:.2f} ha disponibles para nuevos cuarteles.',
                    )
                else:
                    ahora = datetime.now(timezone.utc)
                    datos = datos_cuartel(form, huerto)
                    cuarteles_collection.insert_one({**datos, 'creado_en': ahora, 'actualizado_en': ahora})
                    messages.success(request, f'Cuartel “{datos["nombre"]}” registrado correctamente.')
                    return redirect('cuarteles')
        except (InvalidId, PyMongoError):
            form.add_error(None, 'No se pudo guardar el cuartel. Revisa la conexión e inténtalo nuevamente.')
    return render(request, 'gestion/cuarteles.html', contexto_cuarteles(request, huertos, form))


@administrador_required
@require_http_methods(['GET', 'POST'])
def editar_cuartel(request, id):
    object_id = cuartel_object_id(id)
    huertos = obtener_huertos_para_cuartel(request)
    try:
        cuartel = cuarteles_collection.find_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo consultar el cuartel.')
        return redirect('cuarteles')
    if cuartel is None:
        raise Http404('Cuartel no encontrado')
    inicial = {**cuartel, 'huerto_id': str(cuartel.get('huerto_id', ''))}
    form = CuartelForm(request.POST or None, huertos=huertos, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            huerto = huertos_collection.find_one({'_id': ObjectId(form.cleaned_data['huerto_id'])})
            duplicado = cuarteles_collection.find_one({
                'codigo': form.cleaned_data['codigo'], '_id': {'$ne': object_id},
            })
            if huerto is None:
                form.add_error('huerto_id', 'El huerto seleccionado ya no existe.')
            elif duplicado is not None:
                form.add_error('codigo', 'Ya existe otro cuartel con este código.')
            else:
                disponible = superficie_disponible_cuartel(huerto, object_id)
                solicitada = float(form.cleaned_data['superficie_hectareas'])
                if solicitada > disponible:
                    form.add_error(
                        'superficie_hectareas',
                        f'El huerto solo tiene {disponible:.2f} ha disponibles para este cuartel.',
                    )
                else:
                    datos = datos_cuartel(form, huerto)
                    resultado = cuarteles_collection.update_one(
                        {'_id': object_id},
                        {'$set': {**datos, 'actualizado_en': datetime.now(timezone.utc)}},
                    )
                    if not resultado.matched_count:
                        raise Http404('Cuartel no encontrado')
                    messages.success(request, f'Cuartel “{datos["nombre"]}” actualizado correctamente.')
                    return redirect('cuarteles')
        except (InvalidId, PyMongoError):
            form.add_error(None, 'No se pudo actualizar el cuartel. Inténtalo nuevamente.')
    cuartel['id'] = str(cuartel['_id'])
    return render(request, 'gestion/cuarteles.html', contexto_cuarteles(request, huertos, form, cuartel))


@administrador_required
@require_POST
def eliminar_cuartel(request, id):
    object_id = cuartel_object_id(id)
    try:
        resultado = cuarteles_collection.delete_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo eliminar el cuartel. Inténtalo nuevamente.')
    else:
        if not resultado.deleted_count:
            raise Http404('Cuartel no encontrado')
        messages.success(request, 'Cuartel eliminado correctamente.')
    return redirect('cuarteles')

def cuadrilla_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Cuadrilla no encontrada')


def obtener_personal_cuadrillas(request):
    try:
        return list(trabajadores_collection.find(
            {'rol': {'$in': ['Trabajador', 'Jefe de Cuadrilla']}},
            {'rut': 1, 'nombre': 1, 'apellido': 1, 'rol': 1, 'cuadrilla_id': 1},
        ).sort([('apellido', 1), ('nombre', 1)]))
    except PyMongoError:
        messages.error(request, 'No se pudo cargar el personal disponible.')
        return []


def obtener_unidades_cuadrillas(request):
    unidades = []
    try:
        colecciones = (
            ('predio', 'Predio', predios_collection),
            ('huerto', 'Huerto', huertos_collection),
            ('cuartel', 'Cuartel', cuarteles_collection),
        )
        for tipo, titulo, coleccion in colecciones:
            for item in coleccion.find({}, {'codigo': 1, 'nombre': 1}).sort('nombre', 1):
                unidades.append({
                    'valor': f'{tipo}:{item["_id"]}',
                    'tipo': tipo,
                    'id': str(item['_id']),
                    'etiqueta': f'{titulo}: {item.get("codigo", "S/C")} — {item.get("nombre", "Sin nombre")}',
                })
    except PyMongoError:
        messages.error(request, 'No se pudieron cargar los lugares de trabajo.')
    return unidades


def datos_cuadrilla(form, personal, unidades):
    personal_por_id = {str(t['_id']): t for t in personal}
    unidad_por_valor = {u['valor']: u for u in unidades}
    jefe = personal_por_id.get(form.cleaned_data['jefe_id'])
    seleccionados = [
        personal_por_id[id] for id in form.cleaned_data['integrantes']
        if id in personal_por_id
    ]
    unidad = unidad_por_valor.get(form.cleaned_data['unidad_trabajo'])
    return {
        'codigo': form.cleaned_data['codigo'],
        'nombre': form.cleaned_data['nombre'].strip(),
        'jefe_id': jefe['_id'] if jefe else None,
        'jefe_nombre': f"{jefe.get('nombre', '')} {jefe.get('apellido', '')}".strip() if jefe else '',
        'integrantes_ids': [t['_id'] for t in seleccionados],
        'integrantes_nombres': [f"{t.get('nombre', '')} {t.get('apellido', '')}".strip() for t in seleccionados],
        'unidad_trabajo': unidad['valor'] if unidad else '',
        'unidad_tipo': unidad['tipo'] if unidad else '',
        'unidad_id': unidad['id'] if unidad else '',
        'unidad_etiqueta': unidad['etiqueta'] if unidad else '',
        'labor_actual': form.cleaned_data['labor_actual'].strip(),
        'turno': form.cleaned_data['turno'],
        'fecha_inicio': form.cleaned_data['fecha_inicio'].isoformat() if form.cleaned_data['fecha_inicio'] else '',
        'estado': form.cleaned_data['estado'],
        'observaciones': form.cleaned_data['observaciones'].strip(),
    }


def validar_disponibilidad_personal(form, personal, codigo_actual=''):
    ids = set(form.cleaned_data.get('integrantes', []))
    if form.cleaned_data.get('jefe_id'):
        ids.add(form.cleaned_data['jefe_id'])
    conflictos = []
    for trabajador in personal:
        asignacion = trabajador.get('cuadrilla_id', '')
        if str(trabajador['_id']) in ids and asignacion and asignacion != codigo_actual:
            conflictos.append(f"{trabajador.get('nombre', '')} {trabajador.get('apellido', '')}".strip())
    if conflictos:
        form.add_error(None, 'Ya pertenecen a otra cuadrilla: ' + ', '.join(conflictos) + '.')
    return not conflictos


def sincronizar_personal_cuadrilla(codigo_anterior, datos):
    if codigo_anterior:
        trabajadores_collection.update_many(
            {'cuadrilla_id': codigo_anterior}, {'$set': {'cuadrilla_id': ''}},
        )
        PerfilUsuario.objects.filter(cuadrilla_id=codigo_anterior).update(cuadrilla_id='')
    ids = list(datos['integrantes_ids'])
    if datos['jefe_id']:
        ids.append(datos['jefe_id'])
    if ids:
        trabajadores_collection.update_many(
            {'_id': {'$in': ids}}, {'$set': {'cuadrilla_id': datos['codigo']}},
        )
    if datos['jefe_id']:
        PerfilUsuario.objects.filter(
            trabajador_id=str(datos['jefe_id']), rol='jefe',
        ).update(cuadrilla_id=datos['codigo'])


def contexto_cuadrillas(request, personal, unidades, form=None, cuadrilla_editando=None):
    busqueda = request.GET.get('q', '').strip()
    filtro = {}
    if busqueda:
        patron = re.escape(busqueda)
        filtro = {'$or': [
            {campo: {'$regex': patron, '$options': 'i'}}
            for campo in ('codigo', 'nombre', 'jefe_nombre', 'labor_actual', 'unidad_etiqueta', 'estado')
        ]}
    try:
        cuadrillas_lista = list(cuadrillas_collection.find(filtro).sort('nombre', 1))
    except PyMongoError:
        cuadrillas_lista = []
        messages.error(request, 'No se pudo consultar las cuadrillas. Revisa la conexión con MongoDB Atlas.')
    for cuadrilla in cuadrillas_lista:
        cuadrilla['id'] = str(cuadrilla['_id'])
        cuadrilla['cantidad_integrantes'] = len(cuadrilla.get('integrantes_ids', []))
    return {
        'form': form or CuadrillaForm(
            trabajadores=personal, unidades=unidades,
            initial={'estado': 'Activa', 'turno': 'Jornada completa'},
        ),
        'cuadrillas': cuadrillas_lista,
        'cuadrilla_editando': cuadrilla_editando,
        'busqueda': busqueda,
        'total_cuadrillas': len(cuadrillas_lista),
        'cuadrillas_activas': sum(c.get('estado') == 'Activa' for c in cuadrillas_lista),
        'personal_asignado': sum(len(c.get('integrantes_ids', [])) + bool(c.get('jefe_id')) for c in cuadrillas_lista),
        'hay_personal': bool(personal),
    }


@administrador_required
@require_http_methods(['GET', 'POST'])
def cuadrillas(request):
    personal = obtener_personal_cuadrillas(request)
    unidades = obtener_unidades_cuadrillas(request)
    form = CuadrillaForm(
        request.POST if request.method == 'POST' else None,
        trabajadores=personal, unidades=unidades,
    )
    if request.method == 'POST' and form.is_valid() and validar_disponibilidad_personal(form, personal):
        try:
            if cuadrillas_collection.find_one({'codigo': form.cleaned_data['codigo']}) is not None:
                form.add_error('codigo', 'Ya existe una cuadrilla con este código.')
            else:
                datos = datos_cuadrilla(form, personal, unidades)
                ahora = datetime.now(timezone.utc)
                resultado = cuadrillas_collection.insert_one({**datos, 'creado_en': ahora, 'actualizado_en': ahora})
                try:
                    sincronizar_personal_cuadrilla('', datos)
                except Exception:
                    cuadrillas_collection.delete_one({'_id': resultado.inserted_id})
                    raise
                messages.success(request, f'Cuadrilla “{datos["nombre"]}” creada correctamente.')
                return redirect('cuadrillas')
        except (PyMongoError, IntegrityError):
            form.add_error(None, 'No se pudo guardar la cuadrilla. Inténtalo nuevamente.')
    return render(request, 'gestion/cuadrillas.html', contexto_cuadrillas(request, personal, unidades, form))


@administrador_required
@require_http_methods(['GET', 'POST'])
def editar_cuadrilla(request, id):
    object_id = cuadrilla_object_id(id)
    personal = obtener_personal_cuadrillas(request)
    unidades = obtener_unidades_cuadrillas(request)
    try:
        cuadrilla = cuadrillas_collection.find_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo consultar la cuadrilla.')
        return redirect('cuadrillas')
    if cuadrilla is None:
        raise Http404('Cuadrilla no encontrada')
    inicial = {
        **cuadrilla,
        'jefe_id': str(cuadrilla.get('jefe_id') or ''),
        'integrantes': [str(id) for id in cuadrilla.get('integrantes_ids', [])],
    }
    form = CuadrillaForm(request.POST or None, trabajadores=personal, unidades=unidades, initial=inicial)
    codigo_anterior = cuadrilla.get('codigo', '')
    if (request.method == 'POST' and form.is_valid() and
            validar_disponibilidad_personal(form, personal, codigo_anterior)):
        try:
            duplicado = cuadrillas_collection.find_one({
                'codigo': form.cleaned_data['codigo'], '_id': {'$ne': object_id},
            })
            if duplicado is not None:
                form.add_error('codigo', 'Ya existe otra cuadrilla con este código.')
            else:
                datos = datos_cuadrilla(form, personal, unidades)
                resultado = cuadrillas_collection.update_one(
                    {'_id': object_id},
                    {'$set': {**datos, 'actualizado_en': datetime.now(timezone.utc)}},
                )
                if not resultado.matched_count:
                    raise Http404('Cuadrilla no encontrada')
                sincronizar_personal_cuadrilla(codigo_anterior, datos)
                messages.success(request, f'Cuadrilla “{datos["nombre"]}” actualizada correctamente.')
                return redirect('cuadrillas')
        except (PyMongoError, IntegrityError):
            form.add_error(None, 'No se pudo actualizar la cuadrilla. Inténtalo nuevamente.')
    cuadrilla['id'] = str(cuadrilla['_id'])
    return render(request, 'gestion/cuadrillas.html', contexto_cuadrillas(request, personal, unidades, form, cuadrilla))


@administrador_required
@require_POST
def eliminar_cuadrilla(request, id):
    object_id = cuadrilla_object_id(id)
    try:
        cuadrilla = cuadrillas_collection.find_one({'_id': object_id})
        if cuadrilla is None:
            raise Http404('Cuadrilla no encontrada')
        trabajadores_collection.update_many(
            {'cuadrilla_id': cuadrilla.get('codigo', '')}, {'$set': {'cuadrilla_id': ''}},
        )
        PerfilUsuario.objects.filter(cuadrilla_id=cuadrilla.get('codigo', '')).update(cuadrilla_id='')
        cuadrillas_collection.delete_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo eliminar la cuadrilla. Inténtalo nuevamente.')
    else:
        messages.success(request, 'Cuadrilla eliminada y personal liberado correctamente.')
    return redirect('cuadrillas')


def _collera_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Collera no encontrada')


def _datos_para_colleras(request):
    try:
        cuadrillas = list(cuadrillas_collection.find({}, {'codigo': 1, 'nombre': 1}).sort('nombre', 1))
        trabajadores = list(trabajadores_collection.find(
            {'rol': 'Trabajador'},
            {'rut': 1, 'nombre': 1, 'apellido': 1, 'rol': 1, 'cuadrilla_id': 1, 'collera_id': 1},
        ).sort([('apellido', 1), ('nombre', 1)]))
        return cuadrillas, trabajadores
    except PyMongoError:
        messages.error(request, 'No se pudo cargar el personal para formar colleras.')
        return [], []


def _documento_collera(form, trabajadores):
    por_id = {str(t['_id']): t for t in trabajadores}
    integrantes = [por_id[id] for id in form.cleaned_data['trabajadores'] if id in por_id]
    return {
        'codigo': form.cleaned_data['codigo'],
        'cuadrilla_id': form.cleaned_data['cuadrilla_id'],
        'trabajadores_ids': [t['_id'] for t in integrantes],
        'trabajadores_nombres': [f"{t.get('nombre', '')} {t.get('apellido', '')}".strip() for t in integrantes],
        'activa': form.cleaned_data['activa'],
    }


def _validar_integrantes_collera(form, trabajadores, codigo_actual=''):
    por_id = {str(t['_id']): t for t in trabajadores}
    ocupados = []
    for id in form.cleaned_data.get('trabajadores', []):
        trabajador = por_id.get(id)
        if trabajador and trabajador.get('collera_id') and trabajador.get('collera_id') != codigo_actual:
            ocupados.append(f"{trabajador.get('nombre', '')} {trabajador.get('apellido', '')}".strip())
    if ocupados:
        form.add_error('trabajadores', 'Ya pertenecen a otra collera: ' + ', '.join(ocupados) + '.')
    return not ocupados


def _sincronizar_collera(codigo_anterior, datos):
    if codigo_anterior:
        trabajadores_collection.update_many(
            {'collera_id': codigo_anterior}, {'$set': {'collera_id': ''}},
        )
    if datos['activa'] and datos['trabajadores_ids']:
        trabajadores_collection.update_many(
            {'_id': {'$in': datos['trabajadores_ids']}},
            {'$set': {'collera_id': datos['codigo']}},
        )


def _contexto_collareras(request, form, editando=None):
    try:
        lista = list(colleras_collection.find({}).sort([('cuadrilla_id', 1), ('codigo', 1)]))
    except PyMongoError:
        lista = []
        messages.error(request, 'No se pudieron consultar las colleras.')
    for item in lista:
        item['id'] = str(item['_id'])
    return {
        'form': form, 'colleras': lista, 'collera_editando': editando,
        'total_colleras': len(lista), 'colleras_activas': sum(bool(c.get('activa')) for c in lista),
    }


@administrador_required
@require_http_methods(['GET', 'POST'])
def colleras(request):
    cuadrillas, trabajadores = _datos_para_colleras(request)
    form = ColleraForm(request.POST if request.method == 'POST' else None,
                       cuadrillas=cuadrillas, trabajadores=trabajadores)
    if request.method == 'POST' and form.is_valid() and _validar_integrantes_collera(form, trabajadores):
        try:
            if colleras_collection.find_one({'codigo': form.cleaned_data['codigo']}) is not None:
                form.add_error('codigo', 'Ya existe una collera con este código.')
            else:
                datos = _documento_collera(form, trabajadores)
                ahora = datetime.now(timezone.utc)
                resultado = colleras_collection.insert_one({**datos, 'creado_en': ahora, 'actualizado_en': ahora})
                try:
                    _sincronizar_collera('', datos)
                except Exception:
                    colleras_collection.delete_one({'_id': resultado.inserted_id})
                    raise
                messages.success(request, f'Collera “{datos["codigo"]}” creada correctamente.')
                return redirect('colleras')
        except PyMongoError:
            form.add_error(None, 'No se pudo guardar la collera.')
    return render(request, 'gestion/colleras.html', _contexto_collareras(request, form))


@administrador_required
@require_http_methods(['GET', 'POST'])
def editar_collera(request, id):
    object_id = _collera_object_id(id)
    cuadrillas, trabajadores = _datos_para_colleras(request)
    try:
        collera = colleras_collection.find_one({'_id': object_id})
    except PyMongoError:
        collera = None
    if collera is None:
        raise Http404('Collera no encontrada')
    inicial = {**collera, 'trabajadores': [str(i) for i in collera.get('trabajadores_ids', [])]}
    form = ColleraForm(request.POST or None, cuadrillas=cuadrillas, trabajadores=trabajadores, initial=inicial)
    if request.method == 'POST' and form.is_valid() and _validar_integrantes_collera(
            form, trabajadores, collera.get('codigo', '')):
        try:
            duplicada = colleras_collection.find_one({
                'codigo': form.cleaned_data['codigo'], '_id': {'$ne': object_id},
            })
            if duplicada:
                form.add_error('codigo', 'Ya existe otra collera con este código.')
            else:
                datos = _documento_collera(form, trabajadores)
                colleras_collection.update_one(
                    {'_id': object_id}, {'$set': {**datos, 'actualizado_en': datetime.now(timezone.utc)}},
                )
                _sincronizar_collera(collera.get('codigo', ''), datos)
                messages.success(request, 'Collera actualizada correctamente.')
                return redirect('colleras')
        except PyMongoError:
            form.add_error(None, 'No se pudo actualizar la collera.')
    collera['id'] = str(collera['_id'])
    return render(request, 'gestion/colleras.html', _contexto_collareras(request, form, collera))


@administrador_required
@require_POST
def eliminar_collera(request, id):
    object_id = _collera_object_id(id)
    try:
        collera = colleras_collection.find_one({'_id': object_id})
        if collera is None:
            raise Http404('Collera no encontrada')
        _sincronizar_collera(collera.get('codigo', ''), {'activa': False, 'trabajadores_ids': []})
        colleras_collection.delete_one({'_id': object_id})
    except PyMongoError:
        messages.error(request, 'No se pudo eliminar la collera.')
    else:
        messages.success(request, 'Collera eliminada y trabajadores liberados.')
    return redirect('colleras')


def _jornada_object_id(id):
    try:
        return ObjectId(id)
    except (InvalidId, TypeError):
        raise Http404('Jornada no encontrada')


def _personal_jornada(request, rol, perfil):
    filtro = {'rol': 'Trabajador'}
    if rol == 'cuenta_plenillera' and perfil and perfil.trabajador_id:
        filtro = {'$or': [{'rol': 'Trabajador'}, {'_id': trabajador_object_id(perfil.trabajador_id), 'rol': 'Planillera'}]}
    if rol == 'jefe':
        if not perfil or not perfil.cuadrilla_id:
            return []
        filtro['cuadrilla_id'] = perfil.cuadrilla_id
    try:
        return list(trabajadores_collection.find(
            filtro, {'nombre': 1, 'apellido': 1, 'rol': 1, 'cuadrilla_id': 1, 'collera_id': 1},
        ).sort([('apellido', 1), ('nombre', 1)]))
    except PyMongoError:
        messages.error(request, 'No se pudo cargar el personal de la jornada.')
        return []


def _cuarteles_jornada(request):
    try:
        return list(cuarteles_collection.find(
            {}, {'codigo': 1, 'nombre': 1, 'huerto_nombre': 1},
        ).sort('nombre', 1))
    except PyMongoError:
        messages.error(request, 'No se pudieron cargar los cuarteles.')
        return []


def _documento_jornada(form, personal, cuarteles, request):
    trabajador = {str(t['_id']): t for t in personal}[form.cleaned_data['trabajador_id']]
    cuartel = {str(c['_id']): c for c in cuarteles}[form.cleaned_data['cuartel_id']]
    entrada, salida = form.cleaned_data['hora_entrada'], form.cleaned_data['hora_salida']
    horas = 0
    if entrada and salida:
        horas = round(((salida.hour * 60 + salida.minute) - (entrada.hour * 60 + entrada.minute)) / 60, 2)
    return {
        'fecha': form.cleaned_data['fecha'].isoformat(),
        'trabajador_id': trabajador['_id'],
        'trabajador_nombre': f"{trabajador.get('nombre', '')} {trabajador.get('apellido', '')}".strip(),
        'cuadrilla_id': trabajador.get('cuadrilla_id', ''),
        'collera_id': trabajador.get('collera_id', ''),
        'cuartel_id': cuartel['_id'],
        'cuartel_codigo': cuartel.get('codigo', ''),
        'cuartel_nombre': cuartel.get('nombre', ''),
        'asistencia': form.cleaned_data['asistencia'],
        'hora_entrada': entrada.strftime('%H:%M') if entrada else '',
        'hora_salida': salida.strftime('%H:%M') if salida else '',
        'horas_trabajadas': horas,
        'labor': form.cleaned_data['labor'].strip(),
        'kilos': float(form.cleaned_data['kilos']),
        'capachos': form.cleaned_data['capachos'],
        'bines': form.cleaned_data['bines'],
        'bines_con_hojas': form.cleaned_data['bines_con_hojas'],
        'calidad': form.cleaned_data['calidad'],
        'perdidas_kg': float(form.cleaned_data['perdidas_kg']),
        'observaciones': form.cleaned_data['observaciones'].strip(),
        'registrado_por': request.user.username,
    }


def _filtro_fechas(request, filtro):
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    if desde or hasta:
        filtro['fecha'] = {}
        if desde:
            filtro['fecha']['$gte'] = desde
        if hasta:
            filtro['fecha']['$lte'] = hasta
    return desde, hasta


@login_required
@require_http_methods(['GET', 'POST'])
def jornadas(request):
    rol = rol_usuario(request.user)
    perfil = perfil_usuario(request.user)
    puede_gestionar = rol in ('administrador', 'jefe', 'cuenta_plenillera')
    personal = _personal_jornada(request, rol, perfil) if puede_gestionar else []
    cuarteles = _cuarteles_jornada(request) if puede_gestionar else []
    form = JornadaForm(request.POST if request.method == 'POST' else None,
                       trabajadores=personal, cuarteles=cuarteles)
    if request.method == 'POST':
        if not puede_gestionar:
            raise PermissionDenied('Tu perfil solo puede consultar jornadas.')
        if form.is_valid():
            try:
                datos = _documento_jornada(form, personal, cuarteles, request)
                duplicada = jornadas_collection.find_one({
                    'fecha': datos['fecha'], 'trabajador_id': datos['trabajador_id'],
                })
                if duplicada:
                    form.add_error(None, 'Ese trabajador ya tiene una jornada registrada en la fecha indicada.')
                else:
                    ahora = datetime.now(timezone.utc)
                    jornadas_collection.insert_one({
                        **datos, 'validado': rol == 'administrador',
                        'creado_en': ahora, 'actualizado_en': ahora,
                    })
                    messages.success(request, 'Jornada registrada correctamente.')
                    return redirect('jornadas')
            except (KeyError, PyMongoError):
                form.add_error(None, 'No se pudo guardar la jornada.')

    filtro = {}
    if rol == 'jefe':
        filtro['cuadrilla_id'] = perfil.cuadrilla_id if perfil else '__sin_cuadrilla__'
    elif rol == 'trabajador':
        if not perfil or not perfil.trabajador_id:
            filtro['_id'] = {'$exists': False}
        else:
            try:
                filtro['trabajador_id'] = ObjectId(perfil.trabajador_id)
            except (InvalidId, TypeError):
                filtro['_id'] = {'$exists': False}
    elif rol not in ('administrador', 'gerencia', 'recursos_humanos', 'cuenta_plenillera'):
        filtro['_id'] = {'$exists': False}
    desde, hasta = _filtro_fechas(request, filtro)
    try:
        registros = list(jornadas_collection.find(filtro).sort([('fecha', -1), ('trabajador_nombre', 1)]))
    except PyMongoError:
        registros = []
        messages.error(request, 'No se pudieron consultar las jornadas.')
    for registro in registros:
        registro['id'] = str(registro['_id'])

    resumen_collera = []
    if rol == 'trabajador' and perfil and perfil.trabajador_id:
        try:
            trabajador = trabajadores_collection.find_one({'_id': ObjectId(perfil.trabajador_id)}) or {}
            codigo_collera = trabajador.get('collera_id', '')
            if codigo_collera:
                filtro_collera = {'collera_id': codigo_collera}
                _filtro_fechas(request, filtro_collera)
                docs = list(jornadas_collection.find(filtro_collera))
                por_fecha = {}
                for doc in docs:
                    fila = por_fecha.setdefault(doc.get('fecha', ''), {'fecha': doc.get('fecha', ''), 'kilos': 0, 'perdidas': 0})
                    fila['kilos'] += float(doc.get('kilos') or 0)
                    fila['perdidas'] += float(doc.get('perdidas_kg') or 0)
                resumen_collera = sorted(por_fecha.values(), key=lambda x: x['fecha'], reverse=True)
        except (InvalidId, PyMongoError):
            pass
    resumen = {
        'registros': len(registros),
        'kilos': sum(float(r.get('kilos') or 0) for r in registros),
        'capachos': sum(int(r.get('capachos') or 0) for r in registros),
        'bines': sum(int(r.get('bines') or 0) for r in registros),
        'horas': sum(float(r.get('horas_trabajadas') or 0) for r in registros),
        'perdidas': sum(float(r.get('perdidas_kg') or 0) for r in registros),
    }
    return render(request, 'gestion/jornadas.html', {
        'form': form, 'registros': registros, 'resumen': resumen, 'rol': rol,
        'puede_gestionar': puede_gestionar, 'desde': desde, 'hasta': hasta,
        'resumen_collera': resumen_collera,
    })


def _jornada_permitida(request, jornada):
    rol = rol_usuario(request.user)
    if rol in ('administrador', 'cuenta_plenillera'):
        return True
    perfil = perfil_usuario(request.user)
    return rol == 'jefe' and perfil and jornada.get('cuadrilla_id') == perfil.cuadrilla_id


@login_required
@require_POST
def validar_jornada(request, id):
    object_id = _jornada_object_id(id)
    jornada = jornadas_collection.find_one({'_id': object_id})
    if jornada is None:
        raise Http404('Jornada no encontrada')
    if not _jornada_permitida(request, jornada):
        raise PermissionDenied('No puedes validar esta jornada.')
    jornadas_collection.update_one({'_id': object_id}, {'$set': {
        'validado': True, 'validado_por': request.user.username,
        'validado_en': datetime.now(timezone.utc),
    }})
    messages.success(request, 'Jornada validada para el cierre diario.')
    return redirect('jornadas')


@login_required
@require_POST
def eliminar_jornada(request, id):
    object_id = _jornada_object_id(id)
    jornada = jornadas_collection.find_one({'_id': object_id})
    if jornada is None:
        raise Http404('Jornada no encontrada')
    if not _jornada_permitida(request, jornada):
        raise PermissionDenied('No puedes eliminar esta jornada.')
    jornadas_collection.delete_one({'_id': object_id})
    messages.success(request, 'Jornada eliminada.')
    return redirect('jornadas')

@login_required
def reportes(request):
    if not request.user.is_superuser and rol_usuario(request.user) != 'cuenta_plenillera':
        rol = rol_usuario(request.user)
        perfil = perfil_usuario(request.user)
        ganancia_dia = None
        if rol == 'trabajador' and perfil and perfil.trabajador_id:
            try:
                trabajador = trabajadores_collection.find_one(
                    {'_id': ObjectId(perfil.trabajador_id)},
                    {'ganancia_dia': 1},
                )
                if trabajador is not None:
                    ganancia_dia = int(trabajador.get('ganancia_dia') or 0)
            except (InvalidId, TypeError, ValueError):
                ganancia_dia = None
        return render(request, 'gestion/reportes_operativos.html', {
            'rol': rol,
            'ganancia_dia': ganancia_dia,
        })
    tipo = request.GET.get('tipo', 'resumen')
    if tipo not in ('resumen', 'superficie', 'cultivos', 'cuadrillas', 'produccion'):
        tipo = 'resumen'
    busqueda = request.GET.get('q', '').strip()

    def consultar(coleccion, proyeccion=None):
        try:
            return list(coleccion.find({}, proyeccion))
        except PyMongoError:
            messages.error(request, 'Uno de los conjuntos de datos no pudo cargarse desde MongoDB Atlas.')
            return []

    predios = consultar(predios_collection)
    huertos_lista = consultar(huertos_collection)
    cuarteles_lista = consultar(cuarteles_collection)
    cuadrillas_lista = consultar(cuadrillas_collection)
    personal = consultar(trabajadores_collection, {'password': 0})
    agrupar = request.GET.get('agrupar', 'trabajador')
    if agrupar not in ('trabajador', 'collera', 'cuadrilla', 'cuartel', 'fecha'):
        agrupar = 'trabajador'
    filtro_jornadas = {}
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    if desde or hasta:
        filtro_jornadas['fecha'] = {}
        if desde:
            filtro_jornadas['fecha']['$gte'] = desde
        if hasta:
            filtro_jornadas['fecha']['$lte'] = hasta
    try:
        jornadas_lista = list(jornadas_collection.find(filtro_jornadas))
    except PyMongoError:
        jornadas_lista = []
        messages.error(request, 'No se pudieron cargar los registros operativos.')

    huertos_por_predio = {}
    for huerto in huertos_lista:
        huertos_por_predio.setdefault(str(huerto.get('predio_id', '')), []).append(huerto)
    cuarteles_por_huerto = {}
    for cuartel in cuarteles_lista:
        cuarteles_por_huerto.setdefault(str(cuartel.get('huerto_id', '')), []).append(cuartel)

    filas_superficie = []
    for predio in predios:
        huertos_predio = huertos_por_predio.get(str(predio['_id']), [])
        cuarteles_predio = [
            cuartel for huerto in huertos_predio
            for cuartel in cuarteles_por_huerto.get(str(huerto['_id']), [])
        ]
        superficie = float(predio.get('superficie_hectareas') or 0)
        asignada = sum(float(h.get('superficie_hectareas') or 0) for h in huertos_predio)
        filas_superficie.append({
            'codigo': predio.get('codigo', ''), 'nombre': predio.get('nombre', ''),
            'comuna': predio.get('comuna', ''), 'estado': predio.get('estado', ''),
            'superficie': superficie, 'superficie_asignada': asignada,
            'superficie_disponible': max(0, superficie - asignada),
            'ocupacion': round(asignada / superficie * 100, 1) if superficie else 0,
            'huertos': len(huertos_predio), 'cuarteles': len(cuarteles_predio),
            'plantas': sum(int(c.get('numero_plantas') or 0) for c in cuarteles_predio),
        })

    cultivos = {}
    for huerto in huertos_lista:
        especie = huerto.get('especie') or 'Sin especie'
        variedad = huerto.get('variedad') or 'Sin variedad'
        clave = (especie, variedad)
        fila = cultivos.setdefault(clave, {
            'especie': especie, 'variedad': variedad, 'huertos': 0,
            'superficie': 0.0, 'cuarteles': 0, 'plantas': 0,
        })
        fila['huertos'] += 1
        fila['superficie'] += float(huerto.get('superficie_hectareas') or 0)
        cuarteles_huerto = cuarteles_por_huerto.get(str(huerto['_id']), [])
        fila['cuarteles'] += len(cuarteles_huerto)
        fila['plantas'] += sum(int(c.get('numero_plantas') or 0) for c in cuarteles_huerto)
    filas_cultivos = sorted(cultivos.values(), key=lambda f: (f['especie'], f['variedad']))

    filas_cuadrillas = []
    for cuadrilla in cuadrillas_lista:
        filas_cuadrillas.append({
            'codigo': cuadrilla.get('codigo', ''), 'nombre': cuadrilla.get('nombre', ''),
            'jefe': cuadrilla.get('jefe_nombre', '') or 'Sin jefe',
            'integrantes': len(cuadrilla.get('integrantes_ids', [])),
            'labor': cuadrilla.get('labor_actual', ''),
            'lugar': cuadrilla.get('unidad_etiqueta', '') or 'Sin lugar asignado',
            'turno': cuadrilla.get('turno', ''), 'estado': cuadrilla.get('estado', ''),
        })

    campos_agrupacion = {
        'trabajador': ('trabajador_nombre', 'Trabajador'),
        'collera': ('collera_id', 'Collera'),
        'cuadrilla': ('cuadrilla_id', 'Cuadrilla'),
        'cuartel': ('cuartel_codigo', 'Cuartel'),
        'fecha': ('fecha', 'Fecha'),
    }
    campo, etiqueta_agrupacion = campos_agrupacion[agrupar]
    produccion = {}
    for jornada in jornadas_lista:
        clave = jornada.get(campo) or 'Sin asignar'
        fila = produccion.setdefault(clave, {
            'grupo': clave, 'registros': 0, 'presentes': 0, 'horas': 0.0,
            'kilos': 0.0, 'perdidas': 0.0, 'validados': 0,
        })
        fila['registros'] += 1
        fila['presentes'] += jornada.get('asistencia') in ('Presente', 'Atraso')
        fila['horas'] += float(jornada.get('horas_trabajadas') or 0)
        fila['kilos'] += float(jornada.get('kilos') or 0)
        fila['perdidas'] += float(jornada.get('perdidas_kg') or 0)
        fila['validados'] += bool(jornada.get('validado'))
    filas_produccion = sorted(produccion.values(), key=lambda f: str(f['grupo']))
    for fila in filas_produccion:
        fila['rendimiento'] = round(fila['kilos'] / fila['horas'], 2) if fila['horas'] else 0

    if busqueda:
        termino = busqueda.casefold()
        def coincide(fila):
            return termino in ' '.join(str(valor) for valor in fila.values()).casefold()
        filas_superficie = [f for f in filas_superficie if coincide(f)]
        filas_cultivos = [f for f in filas_cultivos if coincide(f)]
        filas_cuadrillas = [f for f in filas_cuadrillas if coincide(f)]
        filas_produccion = [f for f in filas_produccion if coincide(f)]

    superficie_predios = sum(float(p.get('superficie_hectareas') or 0) for p in predios)
    superficie_huertos = sum(float(h.get('superficie_hectareas') or 0) for h in huertos_lista)
    resumen = {
        'predios': len(predios), 'predios_activos': sum(p.get('estado') == 'Activo' for p in predios),
        'huertos': len(huertos_lista), 'huertos_activos': sum(h.get('estado') == 'Activo' for h in huertos_lista),
        'cuarteles': len(cuarteles_lista),
        'cuarteles_productivos': sum(c.get('estado') == 'Productivo' for c in cuarteles_lista),
        'cuadrillas': len(cuadrillas_lista),
        'cuadrillas_activas': sum(c.get('estado') == 'Activa' for c in cuadrillas_lista),
        'personal': len(personal),
        'personal_asignado': sum(1 for t in personal if t.get('cuadrilla_id')),
        'superficie_predios': superficie_predios,
        'superficie_huertos': superficie_huertos,
        'ocupacion': round(superficie_huertos / superficie_predios * 100, 1) if superficie_predios else 0,
        'plantas': sum(int(c.get('numero_plantas') or 0) for c in cuarteles_lista),
        'jornadas': len(jornadas_lista),
        'kilos': sum(float(j.get('kilos') or 0) for j in jornadas_lista),
        'horas': sum(float(j.get('horas_trabajadas') or 0) for j in jornadas_lista),
    }

    if request.GET.get('exportar') == 'csv':
        configuracion = {
            'superficie': (
                'reporte_superficie.csv',
                ['Código', 'Predio', 'Comuna', 'Estado', 'Superficie ha', 'Asignada ha', 'Disponible ha', 'Ocupación %', 'Huertos', 'Cuarteles', 'Plantas'],
                filas_superficie,
                ('codigo', 'nombre', 'comuna', 'estado', 'superficie', 'superficie_asignada', 'superficie_disponible', 'ocupacion', 'huertos', 'cuarteles', 'plantas'),
            ),
            'cultivos': (
                'reporte_cultivos.csv',
                ['Especie', 'Variedad', 'Huertos', 'Superficie ha', 'Cuarteles', 'Plantas'],
                filas_cultivos, ('especie', 'variedad', 'huertos', 'superficie', 'cuarteles', 'plantas'),
            ),
            'cuadrillas': (
                'reporte_cuadrillas.csv',
                ['Código', 'Cuadrilla', 'Jefe', 'Integrantes', 'Labor', 'Lugar', 'Turno', 'Estado'],
                filas_cuadrillas, ('codigo', 'nombre', 'jefe', 'integrantes', 'labor', 'lugar', 'turno', 'estado'),
            ),
            'produccion': (
                'reporte_produccion.csv',
                [etiqueta_agrupacion, 'Registros', 'Asistencias', 'Horas', 'Kilos', 'Pérdidas kg', 'Kg por hora', 'Validados'],
                filas_produccion,
                ('grupo', 'registros', 'presentes', 'horas', 'kilos', 'perdidas', 'rendimiento', 'validados'),
            ),
        }
        if tipo in configuracion:
            nombre, encabezados, filas, claves = configuracion[tipo]
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{nombre}"'
            response.write('\ufeff')
            writer = csv.writer(response)
            writer.writerow(encabezados)
            for fila in filas:
                valores = []
                for clave in claves:
                    valor = fila[clave]
                    if isinstance(valor, str) and valor.startswith(('=', '+', '-', '@')):
                        valor = "'" + valor
                    valores.append(valor)
                writer.writerow(valores)
            return response

    return render(request, 'gestion/reportes.html', {
        'tipo': tipo, 'busqueda': busqueda, 'resumen': resumen,
        'filas_superficie': filas_superficie, 'filas_cultivos': filas_cultivos,
        'filas_cuadrillas': filas_cuadrillas,
        'filas_produccion': filas_produccion, 'agrupar': agrupar,
        'etiqueta_agrupacion': etiqueta_agrupacion, 'desde': desde, 'hasta': hasta,
        'generado_en': datetime.now().strftime('%d-%m-%Y %H:%M'),
    })

@login_required
def trabajadores(request):
    rol = rol_usuario(request.user)
    perfil = perfil_usuario(request.user)
    if request.method == 'POST':
        if rol != 'administrador':
            raise PermissionDenied('Solo el administrador puede asignar pagos.')
        trabajador_id = request.POST.get('trabajador_id', '').strip()
        ganancia_dia = request.POST.get('ganancia_dia', '').strip()
        roles_pago = {
            'rol_trabajador': 'Trabajador',
            'rol_gerencia': 'Gerencia',
            'rol_jefe': 'Jefe de Cuadrilla',
            'rol_recursos_humanos': 'Recursos Humanos',
            'rol_planillera': 'Planillera',
        }
        if not ganancia_dia.isdigit():
            messages.error(request, 'El pago del día debe ser un monto entero igual o mayor que cero.')
        elif trabajador_id in roles_pago:
            rol_pago = roles_pago[trabajador_id]
            try:
                resultado = trabajadores_collection.update_many(
                    {'rol': rol_pago},
                    {'$set': {'ganancia_dia': int(ganancia_dia)}},
                )
            except PyMongoError:
                messages.error(request, 'No se pudo guardar el pago del día. Inténtalo nuevamente.')
            else:
                if resultado.matched_count:
                    messages.success(
                        request,
                        f'Pago del día asignado a {resultado.matched_count} personas con rol {rol_pago}.',
                    )
                else:
                    messages.error(request, f'No hay personas con rol {rol_pago} para actualizar.')
        else:
            try:
                object_id = ObjectId(trabajador_id)
            except (InvalidId, TypeError):
                messages.error(request, 'Selecciona un trabajador válido.')
            else:
                try:
                    resultado = trabajadores_collection.update_one(
                        {'_id': object_id, 'rol': {'$ne': 'Administrador'}},
                        {'$set': {'ganancia_dia': int(ganancia_dia)}},
                    )
                except PyMongoError:
                    messages.error(request, 'No se pudo guardar el pago del día. Inténtalo nuevamente.')
                else:
                    if resultado.matched_count:
                        messages.success(request, 'Pago del día guardado correctamente.')
                    else:
                        messages.error(request, 'El trabajador seleccionado no existe.')
        return redirect('trabajadores')

    if rol in ('administrador', 'jefe', 'gerencia', 'cuenta_plenillera'):
        lista_trabajadores = list(trabajadores_collection.find({
            'rol': {'$ne': 'Administrador'},
        }))
    elif rol in ('trabajador', 'recursos_humanos', 'gerencia') and perfil and perfil.trabajador_id:
        lista_trabajadores = list(trabajadores_collection.find({'_id': ObjectId(perfil.trabajador_id)}))
    else:
        lista_trabajadores = []

    for trabajador in lista_trabajadores:
        trabajador['id'] = str(trabajador['_id'])
        try:
            trabajador['ganancia_dia'] = int(trabajador.get('ganancia_dia') or 0)
        except (TypeError, ValueError):
            trabajador['ganancia_dia'] = 0

    if rol == 'administrador':
        perfiles = {
            p.trabajador_id: p for p in PerfilUsuario.objects.select_related('usuario').exclude(trabajador_id=None).exclude(trabajador_id='')
        }
        for trabajador in lista_trabajadores:
            vinculo = perfiles.get(trabajador['id'])
            trabajador['cuenta'] = vinculo.usuario.username if vinculo else ''
            trabajador['password_configurada'] = bool(vinculo and vinculo.usuario.has_usable_password())
        ids_presentes = {t['id'] for t in lista_trabajadores}
        for id_ficha, vinculo in perfiles.items():
            if id_ficha not in ids_presentes:
                try:
                    object_id = ObjectId(id_ficha)
                except (InvalidId, TypeError):
                    continue
                ficha = {
                    '_id': object_id, 'id': id_ficha, 'rut': vinculo.usuario.username,
                    'nombre': vinculo.usuario.first_name, 'apellido': vinculo.usuario.last_name,
                    'rol': vinculo.get_rol_display(), 'cuenta': vinculo.usuario.username,
                    'cuadrilla_id': vinculo.cuadrilla_id if vinculo.rol == 'jefe' else '',
                    'collera_id': '',
                    'password_configurada': vinculo.usuario.has_usable_password(),
                }
                trabajadores_collection.update_one(
                    {'_id': object_id},
                    {'$setOnInsert': {
                        clave: valor for clave, valor in ficha.items()
                        if clave not in ('_id', 'id', 'cuenta', 'password_configurada')
                    }},
                    upsert=True,
                )
                lista_trabajadores.append(ficha)

    return render(
        request,
        'gestion/trabajadores.html',
        {
            'trabajadores': lista_trabajadores,
            'rol': rol,
            'puede_editar': rol in ('administrador', 'gerencia'),
        }
    )
