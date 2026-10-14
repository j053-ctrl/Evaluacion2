from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import PerfilUsuario


def perfil_usuario(user):
    return PerfilUsuario.objects.filter(usuario=user).first()


def rol_usuario(user):
    if user.is_active and user.is_superuser:
        return 'administrador'
    perfil = perfil_usuario(user)
    return perfil.rol if perfil else 'trabajador'


def equipo_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if rol_usuario(request.user) not in ('administrador', 'jefe'):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def administrador_required(view):
    @login_required
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_superuser:
            raise PermissionDenied('Solo el administrador puede modificar los datos.')
        return view(request, *args, **kwargs)
    return wrapper

