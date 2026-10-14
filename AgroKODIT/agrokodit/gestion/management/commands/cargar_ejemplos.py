from datetime import date, datetime, timedelta, timezone
from hashlib import sha256

from bson import ObjectId
from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError


def documentos_ejemplo(fecha):
    """Referencias estables para poder repetir la carga sin duplicar datos."""
    ahora = datetime.now(timezone.utc)
    documentos = []

    def agregar(coleccion, clave, **datos):
        oid = ObjectId(sha256(f'agrokodit-ejemplo-v1:{coleccion}:{clave}'.encode()).hexdigest()[:24])
        doc = {'_id': oid, 'datos_ejemplo': True, 'creado_en': ahora,
               'actualizado_en': ahora, **datos}
        documentos.append((coleccion, doc))
        return doc

    for n, (especie, variedad) in enumerate([('Manzano', 'Gala'), ('Cerezo', 'Santina')], 1):
        predio = agregar('predios', str(n), codigo=f'DEMO-P{n}', nombre=f'Predio ejemplo {n}',
            ubicacion='Camino rural s/n', comuna='Curicó', region='Maule',
            superficie_hectareas=20.0, encargado='Encargado de ejemplo', telefono='+56900000000',
            estado='Activo', observaciones='Datos ficticios de demostración.')
        huerto = agregar('huertos', str(n), codigo=f'DEMO-H{n}', nombre=f'Huerto ejemplo {n}',
            predio_id=predio['_id'], predio_codigo=predio['codigo'], predio_nombre=predio['nombre'],
            especie=especie, variedad=variedad, superficie_hectareas=10.0,
            anio_plantacion=2020, sistema_riego='Goteo', estado='Activo', observaciones='Ejemplo')
        cuartel = agregar('cuarteles', str(n), codigo=f'DEMO-C{n}', nombre=f'Cuartel ejemplo {n}',
            huerto_id=huerto['_id'], huerto_codigo=huerto['codigo'], huerto_nombre=huerto['nombre'],
            predio_nombre=predio['nombre'], especie=especie, variedad=variedad,
            superficie_hectareas=5.0, numero_hileras=25, numero_plantas=2500,
            distancia_hileras_m=4.0, distancia_plantas_m=5.0, portainjerto='Ejemplo',
            sector_riego=f'Sector {n}', estado='Activo', observaciones='Ejemplo')
        codigo_cuadrilla, codigo_collera = f'DEMO-Q{n}', f'DEMO-CO{n}'
        personal = []
        for i, (nombre, apellido) in enumerate([('Alex', 'Ejemplo'), ('Camila', 'Prueba'), ('Diego', 'Demo')]):
            personal.append(agregar('trabajadores', f'{n}:{i}', nombre=f'{nombre} {n}', apellido=apellido,
                rut='', rol='Jefe de Cuadrilla' if i == 0 else 'Trabajador',
                cuadrilla_id=codigo_cuadrilla, collera_id='' if i == 0 else codigo_collera,
                estado='Activo'))
        nombres = [f"{t['nombre']} {t['apellido']}" for t in personal]
        agregar('cuadrillas', str(n), codigo=codigo_cuadrilla, nombre=f'Cuadrilla ejemplo {n}',
            jefe_id=personal[0]['_id'], jefe_nombre=nombres[0],
            integrantes_ids=[t['_id'] for t in personal[1:]], integrantes_nombres=nombres[1:],
            unidad_trabajo=f"cuartel:{cuartel['_id']}", unidad_tipo='cuartel',
            unidad_id=str(cuartel['_id']), unidad_etiqueta=f"Cuartel: {cuartel['codigo']} — {cuartel['nombre']}",
            labor_actual='Cosecha', turno='Jornada completa', fecha_inicio=fecha.isoformat(),
            estado='Activa', observaciones='Ejemplo')
        agregar('colleras', str(n), codigo=codigo_collera, cuadrilla_id=codigo_cuadrilla,
            trabajadores_ids=[t['_id'] for t in personal[1:]], trabajadores_nombres=nombres[1:], activa=True)
        for dia in range(3):
            fecha_jornada = (fecha - timedelta(days=dia)).isoformat()
            total = 0
            for i, trabajador in enumerate(personal[1:], 1):
                kilos = float(180 + n * 10 + i * 5 + dia * 10)
                total += kilos
                agregar('jornadas', f'{n}:{i}:{dia}', fecha=fecha_jornada,
                    trabajador_id=trabajador['_id'], trabajador_nombre=nombres[i],
                    cuadrilla_id=codigo_cuadrilla, collera_id=codigo_collera,
                    cuartel_id=cuartel['_id'], cuartel_codigo=cuartel['codigo'], cuartel_nombre=cuartel['nombre'],
                    asistencia='Presente', hora_entrada='08:00', hora_salida='16:00', horas_trabajadas=8.0,
                    labor='Cosecha', kilos=kilos, capachos=20, bines=1, bines_con_hojas='',
                    calidad='Primera', perdidas_kg=2.0, observaciones='Producción ficticia de ejemplo',
                    registrado_por='demo', validado=True)
            agregar('reportes', f'{n}:{dia}', titulo=f'Reporte ejemplo {codigo_cuadrilla} - {fecha_jornada}',
                fecha=fecha_jornada, contenido=f'Datos de ejemplo. Cuadrilla {codigo_cuadrilla}, collera {codigo_collera}, '
                f'cuartel {cuartel["codigo"]}. Asistencia: 2 presentes. Producción: {total} kg. '
                'Capachos: 40. Bines: 2. Bines con hojas: ninguno. Pérdidas: 4 kg.',
                autor='demo', estado='publicado', revisado_por='demo', publicado_en=ahora, enviado_en=ahora)
    return documentos


class Command(BaseCommand):
    help = 'Agrega datos ficticios relacionados sin reemplazar documentos existentes ni crear cuentas de acceso.'

    def add_arguments(self, parser):
        parser.add_argument('--fecha', type=date.fromisoformat, default=date(2026, 10, 13),
                            help='Último día de las jornadas (AAAA-MM-DD).')

    def handle(self, *args, **options):
        from gestion.db import db

        creados = {}
        try:
            db.client.admin.command('ping')
            for coleccion, documento in documentos_ejemplo(options['fecha']):
                resultado = db[coleccion].update_one({'_id': documento['_id']}, {'$setOnInsert': documento}, upsert=True)
                creados[coleccion] = creados.get(coleccion, 0) + int(resultado.upserted_id is not None)
        except PyMongoError:
            raise CommandError('No se pudo completar la carga en MongoDB. Revisa la conexión y vuelve a ejecutar; '
                               'los documentos ya insertados no se duplicarán.') from None
        for coleccion, cantidad in creados.items():
            self.stdout.write(f'{coleccion}: {cantidad} documentos nuevos')
        self.stdout.write(self.style.SUCCESS('Carga de ejemplos completada.'))
