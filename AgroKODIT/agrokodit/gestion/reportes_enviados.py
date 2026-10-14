from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from pymongo.errors import PyMongoError

from .db import reportes_collection
from .permissions import rol_usuario


class ReporteForm(forms.Form):
    titulo = forms.CharField(label='Título', max_length=150)
    fecha = forms.DateField(label='Día reportado', widget=forms.DateInput(attrs={'type': 'date'}))
    contenido = forms.CharField(label='Contenido del reporte', max_length=10000, widget=forms.Textarea(attrs={'rows': 12}),
        help_text='Incluye asistencia, kilos, capachos, bines y los códigos de los bines entregados con hojas.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


@login_required
@require_http_methods(['GET', 'POST'])
def reportes_enviados(request):
    rol = rol_usuario(request.user)
    admin = rol == 'administrador'
    planillera = rol == 'cuenta_plenillera'
    if request.method == 'POST' and not (admin or planillera):
        raise PermissionDenied
    documento = None
    form = ReporteForm()
    try:
        identificador = request.POST.get('id') if request.method == 'POST' else request.GET.get('editar')
        if identificador:
            try:
                oid = ObjectId(identificador)
            except (InvalidId, TypeError):
                raise Http404('Reporte no encontrado')
            filtro = {'_id': oid}
            if admin:
                filtro['estado'] = {'$ne': 'borrador'}
            else:
                filtro['autor'] = request.user.username
            documento = reportes_collection.find_one(filtro)
            if not documento:
                raise Http404('Reporte no encontrado')
            documento['id'] = str(documento['_id'])
            form = ReporteForm(initial=documento)
        if request.method == 'POST':
            accion = request.POST.get('accion')
            ahora = datetime.now(timezone.utc)
            if accion == 'publicar_todos':
                if not admin:
                    raise PermissionDenied('Solo el administrador puede publicar todos los reportes.')
                resultado = reportes_collection.update_many(
                    {'estado': 'enviado'},
                    {'$set': {'estado': 'publicado', 'revisado_por': request.user.username,
                              'publicado_en': ahora, 'actualizado_en': ahora}},
                )
                messages.success(request, f'{resultado.modified_count} reportes publicados y actualizados en la base de datos.')
                return redirect('reportes_enviados')
            elif accion in ('guardar', 'enviar'):
                if not planillera or (documento and documento['estado'] not in ('borrador', 'devuelto')):
                    raise PermissionDenied('Solo puedes editar tus borradores o reportes devueltos.')
                form = ReporteForm(request.POST)
                if form.is_valid():
                    datos = {**form.cleaned_data, 'fecha': form.cleaned_data['fecha'].isoformat(),
                             'estado': 'enviado' if accion == 'enviar' else 'borrador', 'actualizado_en': ahora}
                    if accion == 'enviar':
                        datos['enviado_en'] = ahora
                    if documento:
                        resultado = reportes_collection.update_one(
                            {'_id': documento['_id'], 'autor': request.user.username, 'estado': documento['estado']}, {'$set': datos})
                        if not resultado.matched_count:
                            messages.error(request, 'El reporte cambió. Recarga la página antes de editarlo.')
                            return redirect('reportes_enviados')
                    else:
                        reportes_collection.insert_one({**datos, 'autor': request.user.username, 'creado_en': ahora})
                    messages.success(request, 'Reporte enviado al administrador.' if accion == 'enviar' else 'Borrador guardado.')
                    return redirect('reportes_enviados')
            elif accion in ('publicar', 'devolver'):
                if not admin or not documento or documento['estado'] != 'enviado':
                    raise PermissionDenied('Solo el administrador puede revisar reportes enviados.')
                datos = {'estado': 'publicado' if accion == 'publicar' else 'devuelto', 'revisado_por': request.user.username,
                         'actualizado_en': ahora, 'comentario_admin': request.POST.get('comentario_admin', '').strip()[:2000]}
                if accion == 'publicar':
                    datos['publicado_en'] = ahora
                resultado = reportes_collection.update_one({'_id': documento['_id'], 'estado': 'enviado'}, {'$set': datos})
                if resultado.matched_count:
                    messages.success(request, 'Reporte publicado.' if accion == 'publicar' else 'Reporte devuelto para corrección.')
                else:
                    messages.error(request, 'El reporte ya fue revisado. Recarga la página.')
                return redirect('reportes_enviados')
            else:
                raise PermissionDenied('Acción no permitida.')
        filtro = {'estado': {'$ne': 'borrador'}} if admin else ({'$or': [{'autor': request.user.username}, {'estado': 'publicado'}]} if planillera else {'estado': 'publicado'})
        registros = list(reportes_collection.find(filtro, {'contenido': 0}).sort('actualizado_en', -1))
        for registro in registros:
            registro['id'] = str(registro['_id'])
        publicados = list(reportes_collection.find({'estado': 'publicado'}).sort('publicado_en', -1))
    except PyMongoError:
        messages.error(request, 'No se pudieron guardar o consultar los reportes. Intenta nuevamente.')
        registros, publicados = [], []
    return render(request, 'gestion/reportes_enviados.html', {
        'form': form, 'reporte': documento, 'registros': registros, 'publicados': publicados,
        'es_admin': admin, 'es_planillera': planillera,
        'puede_editar': planillera and (not documento or documento['estado'] in ('borrador', 'devuelto')),
    })
