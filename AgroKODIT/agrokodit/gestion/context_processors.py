from .permissions import rol_usuario


def acceso(request):
    if not request.user.is_authenticated:
        return {}
    rol = rol_usuario(request.user)
    return {'rol_acceso': rol, 'nombre_rol': {
        'administrador': 'Administrador', 'jefe': 'Jefe de cuadrilla',
        'trabajador': 'Trabajador', 'recursos_humanos': 'Recursos Humanos',
        'gerencia': 'Gerencia',
        'cuenta_plenillera': 'Planillera',
    }[rol]}
