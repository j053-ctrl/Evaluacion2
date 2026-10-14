from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError, transaction
from pymongo.errors import PyMongoError

from .db import (
    administradores_collection, trabajadores_collection, usuarios_collection,
)
from .models import PerfilUsuario


class MongoTrabajadorBackend(BaseBackend):
    """Autentica las cuentas operativas con credenciales de MongoDB Atlas."""

    ROLES = {
        'Trabajador': 'trabajador',
        'Jefe de Cuadrilla': 'jefe',
        'Recursos Humanos': 'recursos_humanos',
        'Gerencia': 'gerencia',
        'Planillera': 'cuenta_plenillera',
    }

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        username = username.upper()
        try:
            cuenta = usuarios_collection.find_one({
                'rut': username,
                'rol': {'$in': ['trabajador', 'jefe', 'gerencia', 'recursos_humanos', 'cuenta_plenillera']},
                'activo': {'$ne': False},
            })
        except PyMongoError:
            cuenta = None
        rol = cuenta.get('rol') if cuenta else None

        if cuenta is None:
            try:
                legado = trabajadores_collection.find_one({'rut': username})
            except PyMongoError:
                legado = None
            rol = self.ROLES.get(legado.get('rol')) if legado else None
            cuenta = legado

        if not rol or not cuenta or not check_password(password, cuenta.get('password', '')):
            return None

        trabajador = cuenta
        trabajador_id = cuenta.get('trabajador_id') or cuenta.get('_id')
        if cuenta.get('trabajador_id'):
            try:
                ficha = trabajadores_collection.find_one({'_id': trabajador_id})
            except PyMongoError:
                ficha = None
            if ficha:
                trabajador = {**cuenta, **ficha, 'password': cuenta.get('password', '')}

        try:
            with transaction.atomic():
                usuario, creado = get_user_model().objects.get_or_create(username=username)
                if usuario.is_superuser:
                    return None
                usuario.first_name = trabajador.get('nombre', '')
                usuario.last_name = trabajador.get('apellido', '')
                usuario.is_active = True
                usuario.is_staff = False
                usuario.is_superuser = False
                usuario.set_unusable_password()
                usuario.save()
                PerfilUsuario.objects.update_or_create(
                    usuario=usuario,
                    defaults={
                        'rol': rol,
                        'trabajador_id': str(trabajador_id),
                        'cuadrilla_id': trabajador.get('cuadrilla_id', '') if rol == 'jefe' else '',
                    },
                )
        except (IntegrityError, KeyError):
            return None
        return usuario

    def get_user(self, user_id):
        try:
            return get_user_model().objects.get(pk=user_id, is_active=True)
        except get_user_model().DoesNotExist:
            return None


class MongoAdministradorBackend(BaseBackend):
    """Autentica administradores desde la colección unificada usuarios."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        identificador = username.strip()
        try:
            administrador = usuarios_collection.find_one({
                '$or': [{'rut': identificador.upper()}, {'username': identificador}],
                'rol': 'administrador',
                'activo': {'$ne': False},
            })
        except PyMongoError:
            administrador = None
        if administrador is None:
            try:
                administrador = administradores_collection.find_one({
                    'username': identificador, 'activo': {'$ne': False},
                })
            except PyMongoError:
                return None
        if not administrador or not check_password(password, administrador.get('password', '')):
            return None

        username_sesion = administrador.get('rut') or administrador.get('username') or identificador
        usuario, creado = get_user_model().objects.get_or_create(username=username_sesion)
        if not creado and hasattr(usuario, 'perfil_agricola') and not usuario.is_superuser:
            return None
        usuario.first_name = administrador.get('nombre', '')
        usuario.is_active = True
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.set_unusable_password()
        usuario.save()
        return usuario

    def get_user(self, user_id):
        try:
            return get_user_model().objects.get(pk=user_id, is_active=True)
        except get_user_model().DoesNotExist:
            return None
