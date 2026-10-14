import re

from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from gestion.db import (
    administradores_collection, trabajadores_collection, usuarios_collection,
)


ROLES = {
    'Trabajador': 'trabajador',
    'Jefe de Cuadrilla': 'jefe',
    'Recursos Humanos': 'recursos_humanos',
    'Gerencia': 'gerencia',
}


class Command(BaseCommand):
    help = 'Unifica en usuarios las credenciales existentes de todos los roles.'

    def handle(self, *args, **options):
        copiados = 0
        omitidos = 0
        try:
            if usuarios_collection.name not in usuarios_collection.database.list_collection_names():
                usuarios_collection.database.create_collection(usuarios_collection.name)

            for ficha in trabajadores_collection.find({'password': {'$exists': True, '$ne': ''}}):
                rol = ROLES.get(ficha.get('rol'))
                rut = ficha.get('rut', '').upper()
                if not rol or not rut:
                    omitidos += 1
                    continue
                usuarios_collection.update_one({'rut': rut}, {'$set': {
                    'trabajador_id': ficha['_id'], 'rut': rut,
                    'nombre': ficha.get('nombre', ''), 'apellido': ficha.get('apellido', ''),
                    'rol': rol, 'cuadrilla_id': ficha.get('cuadrilla_id', '') if rol == 'jefe' else '',
                    'password': ficha['password'], 'activo': True,
                }}, upsert=True)
                copiados += 1

            for administrador in administradores_collection.find({}):
                rut = (administrador.get('rut') or administrador.get('username') or '').upper()
                if not re.fullmatch(r'\d{7,8}-[\dK]', rut):
                    omitidos += 1
                    continue
                usuarios_collection.update_one({'rut': rut}, {'$set': {
                    'rut': rut, 'username': rut,
                    'nombre': administrador.get('nombre', ''),
                    'rol': 'administrador', 'password': administrador.get('password', ''),
                    'activo': administrador.get('activo', True),
                }}, upsert=True)
                copiados += 1

            usuarios_collection.create_index('rut', unique=True, name='rut_unico')
            usuarios_collection.create_index('rol', name='rol_usuarios')
        except PyMongoError as error:
            raise CommandError(f'No se pudo unificar las cuentas: {error}')

        self.stdout.write(self.style.SUCCESS(
            f'Colección usuarios preparada: {copiados} cuentas copiadas y {omitidos} omitidas.'
        ))
