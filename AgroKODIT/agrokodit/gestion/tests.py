from unittest.mock import patch

from bson import ObjectId
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from .models import PerfilUsuario


class PrediosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_predios', password='Clave-Predios-789!'
        )
        cls.operador = get_user_model().objects.create_user('operador_predios')

    def setUp(self):
        self.client.force_login(self.admin)
        patcher = patch('gestion.views.predios_collection')
        self.collection = patcher.start()
        self.addCleanup(patcher.stop)
        huertos_patcher = patch('gestion.views.huertos_collection')
        self.huertos_collection = huertos_patcher.start()
        self.addCleanup(huertos_patcher.stop)
        self.huertos_collection.find_one.return_value = None
        self.id = ObjectId()
        self.predio = {
            '_id': self.id, 'codigo': 'PR-01', 'nombre': 'Los Aromos',
            'ubicacion': 'Camino Rural 120', 'comuna': 'Curicó',
            'region': 'Maule', 'superficie_hectareas': 42.5,
            'encargado': 'Ana Pérez', 'telefono': '+56 9 1234 5678',
            'estado': 'Activo', 'observaciones': 'Producción principal.',
        }
        self.datos = {
            clave: str(valor) for clave, valor in self.predio.items()
            if clave != '_id'
        }
        self.collection.find.return_value.sort.return_value = [self.predio.copy()]

    def test_listado_muestra_resumen_y_acciones(self):
        response = self.client.get(reverse('predios'))
        self.assertContains(response, 'Los Aromos')
        self.assertContains(response, '42,50 ha')
        self.assertContains(response, reverse('editar_predio', args=[str(self.id)]))
        self.assertContains(response, reverse('eliminar_predio', args=[str(self.id)]))
        self.collection.find.assert_called_once_with({})

    def test_registrar_predio_normaliza_codigo_y_guarda(self):
        self.collection.find_one.return_value = None
        datos = {**self.datos, 'codigo': 'pr-02'}
        response = self.client.post(reverse('predios'), datos)
        self.assertRedirects(response, reverse('predios'), fetch_redirect_response=False)
        documento = self.collection.insert_one.call_args.args[0]
        self.assertEqual(documento['codigo'], 'PR-02')
        self.assertEqual(documento['superficie_hectareas'], 42.5)
        self.assertIn('creado_en', documento)
        self.assertIn('actualizado_en', documento)

    def test_rechaza_codigo_duplicado_y_datos_invalidos(self):
        self.collection.find_one.return_value = self.predio
        response = self.client.post(reverse('predios'), self.datos)
        self.assertContains(response, 'Ya existe un predio con este código.')
        self.collection.insert_one.assert_not_called()
        datos = {**self.datos, 'superficie_hectareas': '0', 'telefono': 'abc'}
        response = self.client.post(reverse('predios'), datos)
        self.assertIn('superficie_hectareas', response.context['form'].errors)
        self.assertContains(response, 'Ingresa un teléfono válido')
        self.collection.insert_one.assert_not_called()

    def test_editar_y_eliminar_predio(self):
        self.collection.find_one.side_effect = [self.predio.copy(), None]
        resultado = self.collection.update_one.return_value
        resultado.matched_count = 1
        response = self.client.post(
            reverse('editar_predio', args=[str(self.id)]),
            {**self.datos, 'nombre': 'Los Aromos Norte'},
        )
        self.assertRedirects(response, reverse('predios'), fetch_redirect_response=False)
        cambios = self.collection.update_one.call_args.args[1]['$set']
        self.assertEqual(cambios['nombre'], 'Los Aromos Norte')
        self.assertIn('actualizado_en', cambios)

        self.collection.delete_one.return_value.deleted_count = 1
        response = self.client.post(reverse('eliminar_predio', args=[str(self.id)]))
        self.assertRedirects(response, reverse('predios'), fetch_redirect_response=False)
        self.collection.delete_one.assert_called_once_with({'_id': self.id})

    def test_busqueda_escapa_expresiones_y_solo_administra_el_superusuario(self):
        self.client.get(reverse('predios') + '?q=Los.*')
        filtro = self.collection.find.call_args.args[0]
        self.assertEqual(filtro['$or'][0]['codigo']['$regex'], r'Los\.\*')

        self.client.force_login(self.operador)
        for url in (
            reverse('predios'), reverse('editar_predio', args=[str(self.id)]),
            reverse('eliminar_predio', args=[str(self.id)]),
        ):
            self.assertEqual(self.client.post(url, self.datos).status_code, 403)


class HuertosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_huertos', password='Clave-Huertos-789!'
        )

    def setUp(self):
        self.client.force_login(self.admin)
        predios_patcher = patch('gestion.views.predios_collection')
        huertos_patcher = patch('gestion.views.huertos_collection')
        self.predios_collection = predios_patcher.start()
        self.collection = huertos_patcher.start()
        self.addCleanup(predios_patcher.stop)
        self.addCleanup(huertos_patcher.stop)
        cuarteles_patcher = patch('gestion.views.cuarteles_collection')
        self.cuarteles_collection = cuarteles_patcher.start()
        self.addCleanup(cuarteles_patcher.stop)
        self.cuarteles_collection.find_one.return_value = None

        self.predio_id = ObjectId()
        self.predio = {'_id': self.predio_id, 'codigo': 'PR-01', 'nombre': 'Los Aromos'}
        self.predios_collection.find.return_value.sort.return_value = [self.predio.copy()]
        self.predios_collection.find_one.return_value = self.predio.copy()

        self.id = ObjectId()
        self.huerto = {
            '_id': self.id, 'codigo': 'HT-01', 'nombre': 'Cerezos Norte',
            'predio_id': self.predio_id, 'predio_codigo': 'PR-01',
            'predio_nombre': 'Los Aromos', 'especie': 'Cerezo',
            'variedad': 'Santina', 'superficie_hectareas': 12.0,
            'anio_plantacion': 2020, 'sistema_riego': 'Goteo',
            'estado': 'Activo', 'observaciones': 'Sector norte.',
        }
        self.datos = {
            'codigo': 'HT-01', 'nombre': 'Cerezos Norte',
            'predio_id': str(self.predio_id), 'especie': 'Cerezo',
            'variedad': 'Santina', 'superficie_hectareas': '12.00',
            'anio_plantacion': '2020', 'sistema_riego': 'Goteo',
            'estado': 'Activo', 'observaciones': 'Sector norte.',
        }
        self.collection.find.return_value.sort.return_value = [self.huerto.copy()]

    def test_listado_muestra_relacion_resumen_y_acciones(self):
        response = self.client.get(reverse('huertos'))
        self.assertContains(response, 'Cerezos Norte')
        self.assertContains(response, 'Los Aromos')
        self.assertContains(response, reverse('editar_huerto', args=[str(self.id)]))
        self.assertContains(response, reverse('eliminar_huerto', args=[str(self.id)]))

    def test_registra_huerto_vinculado_al_predio(self):
        self.collection.find_one.return_value = None
        response = self.client.post(reverse('huertos'), {**self.datos, 'codigo': 'ht-02'})
        self.assertRedirects(response, reverse('huertos'), fetch_redirect_response=False)
        documento = self.collection.insert_one.call_args.args[0]
        self.assertEqual(documento['codigo'], 'HT-02')
        self.assertEqual(documento['predio_id'], self.predio_id)
        self.assertEqual(documento['predio_nombre'], 'Los Aromos')
        self.assertEqual(documento['superficie_hectareas'], 12.0)

    def test_rechaza_codigo_duplicado_y_exige_predio_existente(self):
        self.collection.find_one.return_value = self.huerto
        response = self.client.post(reverse('huertos'), self.datos)
        self.assertContains(response, 'Ya existe un huerto con este código.')
        self.collection.insert_one.assert_not_called()

        self.predios_collection.find_one.return_value = None
        self.collection.find_one.return_value = None
        response = self.client.post(reverse('huertos'), self.datos)
        self.assertContains(response, 'El predio seleccionado ya no existe.')
        self.collection.insert_one.assert_not_called()

    def test_edita_y_elimina_huerto(self):
        self.collection.find_one.side_effect = [self.huerto.copy(), None]
        self.collection.update_one.return_value.matched_count = 1
        response = self.client.post(
            reverse('editar_huerto', args=[str(self.id)]),
            {**self.datos, 'nombre': 'Cerezos Renovados'},
        )
        self.assertRedirects(response, reverse('huertos'), fetch_redirect_response=False)
        cambios = self.collection.update_one.call_args.args[1]['$set']
        self.assertEqual(cambios['nombre'], 'Cerezos Renovados')

        self.collection.delete_one.return_value.deleted_count = 1
        response = self.client.post(reverse('eliminar_huerto', args=[str(self.id)]))
        self.assertRedirects(response, reverse('huertos'), fetch_redirect_response=False)
        self.collection.delete_one.assert_called_once_with({'_id': self.id})

    def test_sin_predios_orienta_y_bloquea_registro(self):
        self.predios_collection.find.return_value.sort.return_value = []
        self.collection.find.return_value.sort.return_value = []
        response = self.client.get(reverse('huertos'))
        self.assertContains(response, 'primero debes crear al menos un predio')
        self.assertContains(response, 'disabled')


class CuartelesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_cuarteles', password='Clave-Cuarteles-789!'
        )

    def setUp(self):
        self.client.force_login(self.admin)
        huertos_patcher = patch('gestion.views.huertos_collection')
        cuarteles_patcher = patch('gestion.views.cuarteles_collection')
        self.huertos_collection = huertos_patcher.start()
        self.collection = cuarteles_patcher.start()
        self.addCleanup(huertos_patcher.stop)
        self.addCleanup(cuarteles_patcher.stop)

        self.huerto_id = ObjectId()
        self.huerto = {
            '_id': self.huerto_id, 'codigo': 'HT-01', 'nombre': 'Cerezos Norte',
            'predio_nombre': 'Los Aromos', 'especie': 'Cerezo',
            'variedad': 'Santina', 'superficie_hectareas': 12.0,
        }
        self.huertos_collection.find.return_value.sort.return_value = [self.huerto.copy()]
        self.huertos_collection.find_one.return_value = self.huerto.copy()

        self.id = ObjectId()
        self.cuartel = {
            '_id': self.id, 'codigo': 'CT-01', 'nombre': 'Cuartel Norte 1',
            'huerto_id': self.huerto_id, 'huerto_codigo': 'HT-01',
            'huerto_nombre': 'Cerezos Norte', 'predio_nombre': 'Los Aromos',
            'especie': 'Cerezo', 'variedad': 'Santina',
            'superficie_hectareas': 4.0, 'numero_hileras': 25,
            'numero_plantas': 2400, 'distancia_hileras_m': 4.5,
            'distancia_plantas_m': 2.0, 'portainjerto': 'Colt',
            'sector_riego': 'Válvula 3', 'estado': 'Productivo',
            'observaciones': 'Cosecha temprana.',
        }
        self.datos = {
            'codigo': 'CT-01', 'nombre': 'Cuartel Norte 1',
            'huerto_id': str(self.huerto_id), 'superficie_hectareas': '4.00',
            'numero_hileras': '25', 'numero_plantas': '2400',
            'distancia_hileras_m': '4.5', 'distancia_plantas_m': '2.0',
            'portainjerto': 'Colt', 'sector_riego': 'Válvula 3',
            'estado': 'Productivo', 'observaciones': 'Cosecha temprana.',
        }
        cursor = self.collection.find.return_value
        cursor.sort.return_value = [self.cuartel.copy()]
        cursor.__iter__.return_value = iter([])

    def test_listado_muestra_datos_productivos_y_densidad(self):
        response = self.client.get(reverse('cuarteles'))
        self.assertContains(response, 'Cuartel Norte 1')
        self.assertContains(response, '2400 plantas')
        self.assertContains(response, '600 plantas/ha')
        self.assertContains(response, '4,50 × 2,00 m')
        self.assertContains(response, reverse('editar_cuartel', args=[str(self.id)]))

    def test_registra_datos_propios_del_cuartel(self):
        self.collection.find_one.return_value = None
        response = self.client.post(reverse('cuarteles'), {**self.datos, 'codigo': 'ct-02'})
        self.assertRedirects(response, reverse('cuarteles'), fetch_redirect_response=False)
        documento = self.collection.insert_one.call_args.args[0]
        self.assertEqual(documento['codigo'], 'CT-02')
        self.assertEqual(documento['huerto_id'], self.huerto_id)
        self.assertEqual(documento['numero_hileras'], 25)
        self.assertEqual(documento['numero_plantas'], 2400)
        self.assertEqual(documento['distancia_hileras_m'], 4.5)
        self.assertEqual(documento['sector_riego'], 'Válvula 3')

    def test_no_permite_exceder_superficie_disponible_del_huerto(self):
        self.collection.find_one.return_value = None
        self.collection.find.return_value.__iter__.return_value = iter([
            {'superficie_hectareas': 8.0},
        ])
        response = self.client.post(
            reverse('cuarteles'), {**self.datos, 'superficie_hectareas': '5.00'}
        )
        self.assertContains(response, 'solo tiene 4.00 ha disponibles')
        self.collection.insert_one.assert_not_called()

    def test_edita_y_elimina_cuartel(self):
        self.collection.find_one.side_effect = [self.cuartel.copy(), None]
        self.collection.update_one.return_value.matched_count = 1
        response = self.client.post(
            reverse('editar_cuartel', args=[str(self.id)]),
            {**self.datos, 'numero_plantas': '2500'},
        )
        self.assertRedirects(response, reverse('cuarteles'), fetch_redirect_response=False)
        cambios = self.collection.update_one.call_args.args[1]['$set']
        self.assertEqual(cambios['numero_plantas'], 2500)

        self.collection.delete_one.return_value.deleted_count = 1
        response = self.client.post(reverse('eliminar_cuartel', args=[str(self.id)]))
        self.assertRedirects(response, reverse('cuarteles'), fetch_redirect_response=False)
        self.collection.delete_one.assert_called_once_with({'_id': self.id})

    def test_sin_huertos_indica_el_paso_previo(self):
        self.huertos_collection.find.return_value.sort.return_value = []
        self.collection.find.return_value.sort.return_value = []
        response = self.client.get(reverse('cuarteles'))
        self.assertContains(response, 'primero debes registrar un huerto')
        self.assertContains(response, 'disabled')


class CuadrillasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_cuadrillas', password='Clave-Cuadrillas-789!'
        )

    def setUp(self):
        self.client.force_login(self.admin)
        nombres = (
            'trabajadores_collection', 'cuadrillas_collection', 'predios_collection',
            'huertos_collection', 'cuarteles_collection',
        )
        self.mocks = {}
        for nombre in nombres:
            patcher = patch(f'gestion.views.{nombre}')
            self.mocks[nombre] = patcher.start()
            self.addCleanup(patcher.stop)
        self.trabajadores = self.mocks['trabajadores_collection']
        self.collection = self.mocks['cuadrillas_collection']

        self.jefe_id = ObjectId()
        self.trabajador_id = ObjectId()
        self.personal = [
            {'_id': self.jefe_id, 'rut': '11111111-1', 'nombre': 'Juan',
             'apellido': 'Jefe', 'rol': 'Jefe de Cuadrilla', 'cuadrilla_id': ''},
            {'_id': self.trabajador_id, 'rut': '12345678-5', 'nombre': 'Ana',
             'apellido': 'Pérez', 'rol': 'Trabajador', 'cuadrilla_id': ''},
        ]
        self.trabajadores.find.return_value.sort.return_value = self.personal
        for nombre in ('predios_collection', 'huertos_collection', 'cuarteles_collection'):
            self.mocks[nombre].find.return_value.sort.return_value = []

        self.id = ObjectId()
        self.cuadrilla = {
            '_id': self.id, 'codigo': 'CD-01', 'nombre': 'Equipo Cosecha',
            'jefe_id': self.jefe_id, 'jefe_nombre': 'Juan Jefe',
            'integrantes_ids': [self.trabajador_id], 'integrantes_nombres': ['Ana Pérez'],
            'unidad_trabajo': '', 'unidad_tipo': '', 'unidad_id': '',
            'unidad_etiqueta': '', 'labor_actual': 'Cosecha de cerezas',
            'turno': 'Mañana', 'fecha_inicio': '2026-09-23',
            'estado': 'Activa', 'observaciones': '',
        }
        self.collection.find.return_value.sort.return_value = [self.cuadrilla.copy()]
        self.datos = {
            'codigo': 'CD-01', 'nombre': 'Equipo Cosecha',
            'jefe_id': str(self.jefe_id), 'integrantes': [str(self.trabajador_id)],
            'unidad_trabajo': '', 'labor_actual': 'Cosecha de cerezas',
            'turno': 'Mañana', 'fecha_inicio': '2026-09-23',
            'estado': 'Activa', 'observaciones': '',
        }

    def test_listado_muestra_jefe_integrantes_y_asignacion(self):
        response = self.client.get(reverse('cuadrillas'))
        self.assertContains(response, 'Equipo Cosecha')
        self.assertContains(response, 'Juan Jefe')
        self.assertContains(response, 'Ana Pérez')
        self.assertContains(response, 'Cosecha de cerezas')
        self.assertContains(response, reverse('editar_cuadrilla', args=[str(self.id)]))

    def test_crea_cuadrilla_y_sincroniza_personal(self):
        usuario_jefe = get_user_model().objects.create_user('jefe_cuadrilla')
        perfil = PerfilUsuario.objects.create(
            usuario=usuario_jefe, rol='jefe', trabajador_id=str(self.jefe_id)
        )
        self.collection.find_one.return_value = None
        self.collection.insert_one.return_value.inserted_id = self.id
        response = self.client.post(reverse('cuadrillas'), self.datos)
        self.assertRedirects(response, reverse('cuadrillas'), fetch_redirect_response=False)
        documento = self.collection.insert_one.call_args.args[0]
        self.assertEqual(documento['jefe_id'], self.jefe_id)
        self.assertEqual(documento['integrantes_ids'], [self.trabajador_id])
        self.trabajadores.update_many.assert_called_once_with(
            {'_id': {'$in': [self.trabajador_id, self.jefe_id]}},
            {'$set': {'cuadrilla_id': 'CD-01'}},
        )
        perfil.refresh_from_db()
        self.assertEqual(perfil.cuadrilla_id, 'CD-01')

    def test_impide_asignar_personal_que_ya_esta_en_otro_equipo(self):
        self.personal[1]['cuadrilla_id'] = 'CD-OTRA'
        response = self.client.post(reverse('cuadrillas'), self.datos)
        self.assertContains(response, 'Ya pertenecen a otra cuadrilla: Ana Pérez.')
        self.collection.insert_one.assert_not_called()

    def test_edita_y_resincroniza_integrantes(self):
        self.personal[0]['cuadrilla_id'] = 'CD-01'
        self.personal[1]['cuadrilla_id'] = 'CD-01'
        self.collection.find_one.side_effect = [self.cuadrilla.copy(), None]
        self.collection.update_one.return_value.matched_count = 1
        response = self.client.post(
            reverse('editar_cuadrilla', args=[str(self.id)]),
            {**self.datos, 'codigo': 'CD-02', 'labor_actual': 'Poda'},
        )
        self.assertRedirects(response, reverse('cuadrillas'), fetch_redirect_response=False)
        cambios = self.collection.update_one.call_args.args[1]['$set']
        self.assertEqual(cambios['codigo'], 'CD-02')
        self.assertEqual(cambios['labor_actual'], 'Poda')
        self.assertEqual(self.trabajadores.update_many.call_count, 2)

    def test_eliminar_libera_al_personal(self):
        self.collection.find_one.return_value = self.cuadrilla.copy()
        response = self.client.post(reverse('eliminar_cuadrilla', args=[str(self.id)]))
        self.assertRedirects(response, reverse('cuadrillas'), fetch_redirect_response=False)
        self.trabajadores.update_many.assert_called_once_with(
            {'cuadrilla_id': 'CD-01'}, {'$set': {'cuadrilla_id': ''}},
        )
        self.collection.delete_one.assert_called_once_with({'_id': self.id})


class ReportesAdministradorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_reportes', password='Clave-Reportes-789!'
        )

    def setUp(self):
        self.client.force_login(self.admin)
        nombres = (
            'predios_collection', 'huertos_collection', 'cuarteles_collection',
            'cuadrillas_collection', 'trabajadores_collection', 'jornadas_collection',
        )
        self.mocks = {}
        for nombre in nombres:
            patcher = patch(f'gestion.views.{nombre}')
            self.mocks[nombre] = patcher.start()
            self.addCleanup(patcher.stop)

        self.predio_id = ObjectId()
        self.huerto_id = ObjectId()
        self.mocks['predios_collection'].find.return_value = [{
            '_id': self.predio_id, 'codigo': 'PR-01', 'nombre': 'Los Aromos',
            'comuna': 'Curicó', 'estado': 'Activo', 'superficie_hectareas': 100,
        }]
        self.mocks['huertos_collection'].find.return_value = [{
            '_id': self.huerto_id, 'predio_id': self.predio_id,
            'codigo': 'HT-01', 'nombre': 'Cerezos', 'estado': 'Activo',
            'especie': 'Cerezo', 'variedad': 'Santina',
            'superficie_hectareas': 60,
        }]
        self.mocks['cuarteles_collection'].find.return_value = [{
            '_id': ObjectId(), 'huerto_id': self.huerto_id,
            'estado': 'Productivo', 'numero_plantas': 5000,
        }]
        self.mocks['cuadrillas_collection'].find.return_value = [{
            '_id': ObjectId(), 'codigo': 'CD-01', 'nombre': 'Cosecha',
            'jefe_nombre': 'Juan Jefe', 'integrantes_ids': [ObjectId(), ObjectId()],
            'labor_actual': 'Cosecha', 'unidad_etiqueta': 'Huerto: HT-01 — Cerezos',
            'turno': 'Mañana', 'estado': 'Activa',
        }]
        self.mocks['trabajadores_collection'].find.return_value = [
            {'_id': ObjectId(), 'cuadrilla_id': 'CD-01'},
            {'_id': ObjectId(), 'cuadrilla_id': ''},
        ]
        self.mocks['jornadas_collection'].find.return_value = [{
            '_id': ObjectId(), 'fecha': '2026-09-30', 'trabajador_nombre': 'Ana Pérez',
            'cuadrilla_id': 'CD-01', 'collera_id': 'COL-01', 'cuartel_codigo': 'CT-01',
            'asistencia': 'Presente', 'horas_trabajadas': 8, 'kilos': 120,
            'perdidas_kg': 3, 'validado': True,
        }]

    def test_resumen_calcula_indicadores_reales(self):
        response = self.client.get(reverse('reportes'))
        self.assertContains(response, 'Administrador de reportes')
        self.assertContains(response, '60,0%')
        self.assertContains(response, '5000 plantas')
        self.assertContains(response, '1 / 2')
        self.assertContains(response, 'no inventar datos', count=0)

    def test_reporte_superficie_calcula_disponibilidad(self):
        response = self.client.get(reverse('reportes') + '?tipo=superficie')
        self.assertContains(response, 'Los Aromos')
        self.assertContains(response, '100,00 ha')
        self.assertContains(response, '60,00 ha')
        self.assertContains(response, '40,00 ha')
        self.assertContains(response, '1 huertos')

    def test_reporte_cultivos_y_filtro(self):
        response = self.client.get(reverse('reportes') + '?tipo=cultivos&q=Santina')
        self.assertContains(response, 'Cerezo')
        self.assertContains(response, 'Santina')
        response = self.client.get(reverse('reportes') + '?tipo=cultivos&q=Manzano')
        self.assertContains(response, 'No hay cultivos que coincidan')

    def test_exporta_csv_y_neutraliza_formulas(self):
        self.mocks['cuadrillas_collection'].find.return_value[0]['nombre'] = '=EQUIPO'
        response = self.client.get(reverse('reportes') + '?tipo=cuadrillas&exportar=csv')
        self.assertEqual(response.status_code, 200)
        self.assertIn('reporte_cuadrillas.csv', response['Content-Disposition'])
        contenido = response.content.decode('utf-8-sig')
        self.assertIn('Código,Cuadrilla,Jefe', contenido)
        self.assertIn("'=EQUIPO", contenido)

    def test_reporte_operativo_agrupa_y_calcula_rendimiento(self):
        response = self.client.get(reverse('reportes') + '?tipo=produccion&agrupar=collera')
        self.assertContains(response, 'COL-01')
        self.assertContains(response, '120,00')
        self.assertContains(response, '15,00')


class TrabajadoresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser('administrador', password='ClavePrueba-789')

    def setUp(self):
        self.client.force_login(self.usuario)
        patcher = patch('gestion.views.trabajadores_collection')
        self.collection = patcher.start()
        self.addCleanup(patcher.stop)
        usuarios_patcher = patch('gestion.views.usuarios_collection')
        self.usuarios = usuarios_patcher.start()
        self.addCleanup(usuarios_patcher.stop)
        self.usuarios.find_one.return_value = None
        self.id = ObjectId()
        self.datos = {
            'rut': '12345678-5', 'nombre': 'Ana',
            'apellido': 'Perez', 'rol': 'Jefe de Cuadrilla',
            'cuadrilla_id': '', 'collera_id': '',
        }
        self.collection.find_one.return_value = {'_id': self.id, **self.datos}

    def test_cuenta_sin_ficha_se_da_de_alta_en_mongodb_y_es_eliminable(self):
        usuario = get_user_model().objects.create_user('21953142-7')
        PerfilUsuario.objects.create(usuario=usuario, trabajador_id=str(self.id))
        self.collection.find.return_value = []
        response = self.client.get(reverse('trabajadores'))
        self.assertContains(response, '21953142-7')
        self.assertNotContains(response, 'Cuenta existente sin ficha')
        self.assertContains(response, reverse('editar_trabajador', args=[str(self.id)]))
        alta = self.collection.update_one.call_args
        self.assertEqual(alta.args[0], {'_id': self.id})
        self.assertTrue(alta.kwargs['upsert'])
        self.assertEqual(alta.args[1]['$setOnInsert']['rut'], '21953142-7')
        self.collection.delete_one.return_value.deleted_count = 0
        response = self.client.post(reverse('eliminar_trabajador', args=[str(self.id)]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user_model().objects.filter(pk=usuario.pk).exists())
        self.assertFalse(PerfilUsuario.objects.filter(trabajador_id=str(self.id)).exists())

    def test_eliminar_ficha_elimina_cuenta_vinculada(self):
        usuario = get_user_model().objects.create_user('cuenta_borrar')
        PerfilUsuario.objects.create(usuario=usuario, trabajador_id=str(self.id))
        self.collection.delete_one.return_value.deleted_count = 1
        self.client.post(reverse('eliminar_trabajador', args=[str(self.id)]))
        self.assertFalse(get_user_model().objects.filter(pk=usuario.pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.usuario.pk).exists())

    def test_listado_con_acciones(self):
        self.collection.find.return_value = [{'_id': self.id, **self.datos}]
        response = self.client.get(reverse('trabajadores'))
        self.assertContains(response, 'Ana')
        self.assertContains(response, 'Ganancia del día')
        self.assertContains(response, '$ 0')
        self.collection.find.assert_called_once_with({'rol': {'$ne': 'Administrador'}})
        for accion in ('editar_trabajador', 'eliminar_trabajador'):
            self.assertContains(response, reverse(accion, args=[str(self.id)]))

    def test_administracion_muestra_tarjeta_y_guarda_pago_del_dia(self):
        self.collection.find.return_value = [{'_id': self.id, **self.datos}]
        response = self.client.get(reverse('trabajadores'))
        self.assertContains(response, 'Asignar pago del día')
        self.assertContains(response, 'Ana Perez')
        self.collection.find.assert_called_once_with({'rol': {'$ne': 'Administrador'}})

        self.collection.update_one.reset_mock()
        self.collection.update_one.return_value.matched_count = 1
        response = self.client.post(reverse('trabajadores'), {
            'trabajador_id': str(self.id), 'ganancia_dia': '28000',
        })
        self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
        self.collection.update_one.assert_called_once_with(
            {'_id': self.id, 'rol': {'$ne': 'Administrador'}},
            {'$set': {'ganancia_dia': 28000}},
        )

    def test_administracion_rechaza_pago_invalido(self):
        for trabajador_id, monto in (('invalido', '10000'), (str(self.id), '-1')):
            self.collection.update_one.reset_mock()
            response = self.client.post(reverse('trabajadores'), {
                'trabajador_id': trabajador_id, 'ganancia_dia': monto,
            })
            self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
            self.collection.update_one.assert_not_called()

    def test_administracion_asigna_el_mismo_pago_por_rol(self):
        opciones = {
            'rol_trabajador': 'Trabajador',
            'rol_gerencia': 'Gerencia',
            'rol_jefe': 'Jefe de Cuadrilla',
            'rol_recursos_humanos': 'Recursos Humanos',
        }
        self.collection.update_many.return_value.matched_count = 3
        for opcion, rol in opciones.items():
            self.collection.update_many.reset_mock()
            response = self.client.post(reverse('trabajadores'), {
                'trabajador_id': opcion, 'ganancia_dia': '30000',
            })
            self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
            self.collection.update_many.assert_called_once_with(
                {'rol': rol}, {'$set': {'ganancia_dia': 30000}},
            )
        self.collection.update_one.assert_not_called()

    def test_editar_password_cambia_solo_cuenta_vinculada(self):
        usuario = get_user_model().objects.create_user('cuenta_vinculada', password='Anterior-678!')
        PerfilUsuario.objects.create(usuario=usuario, trabajador_id=str(self.id))
        url = reverse('editar_trabajador', args=[str(self.id)])
        self.assertContains(self.client.get(url), 'Cambiar contraseña')
        response = self.client.post(url, {**self.datos,
            'new_password1': 'Nueva-Cosecha-957!', 'new_password2': 'Nueva-Cosecha-957!'})
        self.assertEqual(response.status_code, 302)
        usuario.refresh_from_db()
        self.assertFalse(usuario.has_usable_password())
        cuenta = self.usuarios.insert_one.call_args.args[0]
        password_atlas = cuenta['password']
        self.assertTrue(check_password('Nueva-Cosecha-957!', password_atlas))
        self.assertNotIn('password', self.collection.update_one.call_args.args[1]['$set'])
        response = self.client.post(url, self.datos)
        self.assertEqual(response.status_code, 302)
        usuario.refresh_from_db()
        self.assertFalse(usuario.has_usable_password())

    def test_editar_password_invalida_no_modifica(self):
        usuario = get_user_model().objects.create_user('cuenta_vinculada', password='Anterior-678!')
        PerfilUsuario.objects.create(usuario=usuario, trabajador_id=str(self.id))
        url = reverse('editar_trabajador', args=[str(self.id)])
        for primera, segunda in [('123', '123'), ('Nueva-957!', ''), ('', 'Nueva-957!'), ('Nueva-957!', 'Distinta-678!')]:
            response = self.client.post(url, {**self.datos, 'new_password1': primera, 'new_password2': segunda})
            self.assertEqual(response.status_code, 200)
            self.collection.update_one.assert_not_called()
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password('Anterior-678!'))

    def test_listado_vacio(self):
        self.collection.find.return_value = []
        self.assertContains(self.client.get(reverse('trabajadores')),
                            'No hay trabajadores registrados.')

    def test_agregar_redirige_al_formulario_unificado(self):
        for metodo in (self.client.get, self.client.post):
            response = metodo(reverse('agregar_trabajador'))
            self.assertRedirects(response, reverse('crear_cuenta'))
        self.collection.insert_one.assert_not_called()

    def test_editar_muestra_datos_y_guarda(self):
        url = reverse('editar_trabajador', args=[str(self.id)])
        response = self.client.get(url)
        self.assertContains(response, 'value="Ana"')
        self.assertContains(response, 'Ganancia del día')
        self.assertContains(response, 'value="Jefe de Cuadrilla" selected')
        response = self.client.post(url, self.datos)
        self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
        self.collection.update_one.assert_called_once_with(
            {'_id': self.id}, {'$set': {
                clave: self.datos[clave]
                for clave in ('rut', 'nombre', 'apellido', 'rol', 'cuadrilla_id', 'collera_id')
            }})

    def test_editar_guarda_una_ganancia_diaria_valida(self):
        url = reverse('editar_trabajador', args=[str(self.id)])
        response = self.client.post(url, {**self.datos, 'ganancia_dia': '25000'})
        self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
        datos_guardados = self.collection.update_one.call_args.args[1]['$set']
        self.assertEqual(datos_guardados['ganancia_dia'], 25000)

    def test_editar_rechaza_una_ganancia_diaria_invalida(self):
        url = reverse('editar_trabajador', args=[str(self.id)])
        for monto in ('-1', '12.5', 'texto', ''):
            self.collection.update_one.reset_mock()
            response = self.client.post(url, {**self.datos, 'ganancia_dia': monto})
            self.assertContains(response, 'La ganancia del día debe ser un monto entero')
            self.collection.update_one.assert_not_called()

    def test_editar_rechaza_datos_invalidos(self):
        url = reverse('editar_trabajador', args=[str(self.id)])
        self.assertNotContains(self.client.get(url), 'value="Administrador"')
        for datos in ({}, {**self.datos, 'rol': 'Desconocido'},
                      {**self.datos, 'rol': 'Administrador'}):
            response = self.client.post(url, datos)
            self.assertContains(response, 'alert-danger')
        self.collection.update_one.assert_not_called()

    def test_editar_acepta_roles_de_recursos_humanos_y_gerencia(self):
        url = reverse('editar_trabajador', args=[str(self.id)])
        formulario = self.client.get(url)
        self.assertContains(formulario, 'value="Recursos Humanos"')
        self.assertContains(formulario, 'value="Gerencia"')
        for rol in ('Recursos Humanos', 'Gerencia'):
            response = self.client.post(url, {
                **self.datos, 'rol': rol,
                'cuadrilla_id': 'Equipo anterior', 'collera_id': 'Collera anterior',
            })
            self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
            datos_guardados = self.collection.update_one.call_args.args[1]['$set']
            self.assertEqual(datos_guardados['rol'], rol)
            self.assertEqual(datos_guardados['cuadrilla_id'], 'Equipo anterior')
            self.assertEqual(datos_guardados['collera_id'], 'Collera anterior')

    def test_editar_muestra_codigos_de_cuadrilla_y_collera(self):
        response = self.client.get(reverse('editar_trabajador', args=[str(self.id)]))
        self.assertContains(response, 'Código de cuadrilla')
        self.assertContains(response, 'Código de collera')
        self.assertContains(response, 'name="cuadrilla_id"')
        self.assertContains(response, 'name="collera_id"')

    def test_eliminar_solo_por_post(self):
        url = reverse('eliminar_trabajador', args=[str(self.id)])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.collection.delete_one.assert_not_called()
        response = self.client.post(url)
        self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
        self.collection.delete_one.assert_called_once_with({'_id': self.id})

    def test_identificadores_invalidos_e_inexistentes(self):
        self.collection.find_one.return_value = None
        self.collection.delete_one.return_value.deleted_count = 0
        for id in ('invalido', str(self.id)):
            self.assertEqual(self.client.get(
                reverse('editar_trabajador', args=[id])).status_code, 404)
            self.assertEqual(self.client.post(
                reverse('eliminar_trabajador', args=[id])).status_code, 404)


class AdministradoresTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_inicial', password='Clave-Inicial-789!'
        )

    def test_crea_administrador_en_coleccion_separada(self):
        self.client.force_login(self.admin)
        with patch('gestion.views.usuarios_collection') as collection:
            collection.find_one.return_value = None
            collection.find.return_value = []
            response = self.client.post(reverse('administradores'), {
                'rut': '12345678-5',
                'nombre': 'Administradora Atlas',
                'password1': 'Clave-Atlas-957!',
                'password2': 'Clave-Atlas-957!',
            })
            self.assertRedirects(
                response, reverse('administradores'), fetch_redirect_response=False
            )
            documento = collection.insert_one.call_args.args[0]
            self.assertEqual(documento['rut'], '12345678-5')
            self.assertNotEqual(documento['password'], 'Clave-Atlas-957!')
            self.assertEqual(documento['rol'], 'administrador')
        usuario = get_user_model().objects.get(username='12345678-5')
        self.assertTrue(usuario.is_superuser)
        self.assertFalse(usuario.has_usable_password())
        self.assertFalse(PerfilUsuario.objects.filter(usuario=usuario).exists())

    def test_autentica_administrador_desde_mongodb(self):
        with patch('gestion.backends.usuarios_collection') as collection:
            collection.find_one.return_value = {
                'rut': '12345678-5',
                'nombre': 'Administradora Atlas',
                'rol': 'administrador',
                'password': make_password('Clave-Atlas-957!'),
                'activo': True,
            }
            usuario = authenticate(
                username='12345678-5', password='Clave-Atlas-957!'
            )
        self.assertIsNotNone(usuario)
        self.assertTrue(usuario.is_superuser)
        self.assertTrue(usuario.is_staff)
        self.assertFalse(PerfilUsuario.objects.filter(usuario=usuario).exists())

    def test_solo_administrador_accede_a_cuentas_administrativas(self):
        usuario = get_user_model().objects.create_user('trabajador_comun')
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('administradores')).status_code, 403)


class PermisosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.trabajador = get_user_model().objects.create_user('trabajador')
        cls.staff = get_user_model().objects.create_user('personal', is_staff=True)

    def test_sin_asignacion_no_consulta_mongodb(self):
        self.client.force_login(self.trabajador)
        with patch('gestion.views.trabajadores_collection') as collection:
            response = self.client.get(reverse('trabajadores'))
            self.assertContains(response, 'No hay datos vinculados')
            collection.find.assert_not_called()

    def test_jefe_consulta_todos_los_trabajadores_y_sus_ganancias(self):
        perfil = PerfilUsuario.objects.create(usuario=self.trabajador, rol='jefe', cuadrilla_id='A')
        self.client.force_login(self.trabajador)
        with patch('gestion.views.trabajadores_collection') as collection:
            collection.find.return_value = [{
                '_id': ObjectId(), 'rut': '12345678-5', 'nombre': 'Ana',
                'apellido': 'Perez', 'rol': 'Trabajador',
                'cuadrilla_id': 'B', 'ganancia_dia': 32000,
            }]
            response = self.client.get(reverse('trabajadores'))
            self.assertContains(response, 'Ana')
            self.assertContains(response, 'Ganancia del día')
            self.assertContains(response, '$ 32000')
            collection.find.assert_called_once_with({'rol': {'$ne': 'Administrador'}})
        self.assertContains(self.client.get(reverse('inicio')), 'Panel del jefe de cuadrilla')
        self.assertEqual(self.client.post(reverse('agregar_trabajador'), {}).status_code, 403)
        perfil.cuadrilla_id = ''
        perfil.save()
        with patch('gestion.views.trabajadores_collection') as collection:
            collection.find.return_value = []
            self.client.get(reverse('trabajadores'))
            collection.find.assert_called_once_with({'rol': {'$ne': 'Administrador'}})

    def test_roles_operativos_no_acceden_a_estructura_ni_perfiles(self):
        perfil = PerfilUsuario.objects.create(usuario=self.trabajador)
        self.client.force_login(self.trabajador)
        for rol in ('trabajador', 'jefe'):
            perfil.rol = rol
            perfil.save()
            for nombre in ('predios', 'huertos', 'cuarteles'):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin:gestion_perfilusuario_changelist')).status_code, 403)

    def test_trabajador_consulta_sin_botones_de_administracion(self):
        self.trabajador.first_name = 'Ana'
        self.trabajador.last_name = 'Perez'
        self.trabajador.save(update_fields=['first_name', 'last_name'])
        self.client.force_login(self.trabajador)
        trabajador_id = ObjectId()
        PerfilUsuario.objects.create(usuario=self.trabajador, trabajador_id=str(trabajador_id))
        with patch('gestion.views.trabajadores_collection') as collection:
            collection.find.return_value = [{
                '_id': trabajador_id, 'nombre': 'Ana', 'apellido': 'Perez',
                'rut': '12345678-5', 'rol': 'Trabajador', 'ganancia_dia': 25000,
            }]
            response = self.client.get(reverse('trabajadores'))
            self.assertContains(response, 'Ana')
            self.assertContains(response, 'Ana Perez')
            self.assertContains(response, 'Trabajador')
            self.assertNotContains(response, 'Ganancia del día')
            self.assertNotContains(response, '$ 25000')
            collection.find.assert_called_once_with({'_id': trabajador_id})
            for texto in ('Agregar trabajador', 'Editar', 'Eliminar', '<th>Acciones</th>'):
                self.assertNotContains(response, texto)
            collection.find_one.return_value = {'ganancia_dia': 25000}
            jornada = self.client.get(reverse('reportes'))
            self.assertContains(jornada, 'Ganancia del día')
            self.assertContains(jornada, '$ 25000')
            collection.find_one.assert_called_once_with(
                {'_id': trabajador_id}, {'ganancia_dia': 1}
            )
        self.assertEqual(self.client.get(reverse('inicio')).status_code, 200)
        self.assertContains(self.client.get(reverse('inicio')), 'Panel del trabajador')

    def test_escritura_bloqueada_incluso_con_url_directa_y_rol_falsificado(self):
        urls = [reverse('agregar_trabajador')]
        urls += [reverse(nombre, args=[str(ObjectId())]) for nombre in
                 ('editar_trabajador', 'eliminar_trabajador')]
        for usuario in (self.trabajador, self.staff):
            self.client.force_login(usuario)
            with patch('gestion.views.trabajadores_collection') as collection:
                self.assertEqual(self.client.post(reverse('trabajadores'), {
                    'trabajador_id': str(ObjectId()), 'ganancia_dia': '25000',
                }).status_code, 403)
                for url in urls:
                    self.assertEqual(self.client.get(url).status_code, 403)
                    response = self.client.post(url, {
                        'rol': 'Administrador', 'is_superuser': 'true',
                    })
                    self.assertEqual(response.status_code, 403)
                self.assertEqual(collection.mock_calls, [])
            usuario.refresh_from_db()
            self.assertFalse(usuario.is_superuser)

    def test_trabajador_no_accede_a_administracion_de_usuarios(self):
        self.client.force_login(self.trabajador)
        self.assertEqual(self.client.get(reverse('admin:auth_user_changelist')).status_code, 302)

    def test_recursos_humanos_no_puede_editar(self):
        perfil = PerfilUsuario.objects.create(
            usuario=self.trabajador, rol='recursos_humanos', trabajador_id=str(ObjectId())
        )
        self.client.force_login(self.trabajador)
        with patch('gestion.views.trabajadores_collection') as collection:
            for nombre in ('editar_trabajador', 'eliminar_trabajador'):
                url = reverse(nombre, args=[str(ObjectId())])
                self.assertEqual(self.client.post(url, {}).status_code, 403)
            self.assertEqual(collection.mock_calls, [])

    def test_gerencia_edita_solo_codigos_de_cuadrilla_y_collera(self):
        PerfilUsuario.objects.create(
            usuario=self.trabajador, rol='gerencia', trabajador_id=str(ObjectId())
        )
        self.client.force_login(self.trabajador)
        trabajador_id = ObjectId()
        url = reverse('editar_trabajador', args=[str(trabajador_id)])
        with patch('gestion.views.trabajadores_collection') as collection:
            collection.find_one.return_value = {
                '_id': trabajador_id, 'rut': '12345678-5', 'nombre': 'Ana',
                'apellido': 'Perez', 'rol': 'Trabajador', 'cuadrilla_id': 'A',
                'collera_id': 'C-1', 'ganancia_dia': 25000,
            }
            formulario = self.client.get(url)
            self.assertContains(formulario, 'Editar códigos del trabajador')
            self.assertContains(formulario, 'name="cuadrilla_id"')
            self.assertContains(formulario, 'name="collera_id"')
            for campo in ('name="rut"', 'name="nombre"', 'name="apellido"',
                          'name="rol"', 'name="ganancia_dia"'):
                self.assertNotContains(formulario, campo)

            collection.update_one.return_value.matched_count = 1
            response = self.client.post(url, {
                'cuadrilla_id': 'CUAD-02', 'collera_id': 'COL-08',
                'rol': 'Administrador', 'ganancia_dia': '999999',
            })
            self.assertRedirects(response, reverse('trabajadores'), fetch_redirect_response=False)
            collection.update_one.assert_called_once_with(
                {'_id': trabajador_id},
                {'$set': {'cuadrilla_id': 'CUAD-02', 'collera_id': 'COL-08'}},
            )
            self.assertEqual(self.client.post(
                reverse('eliminar_trabajador', args=[str(trabajador_id)])
            ).status_code, 403)


class LoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user('operador', password='ClavePrueba-789')

    def test_paginas_y_acciones_requieren_sesion(self):
        for nombre in ('inicio', 'trabajadores', 'predios', 'huertos', 'cuarteles',
                       'cuadrillas', 'reportes', 'agregar_trabajador'):
            url = reverse(nombre)
            self.assertRedirects(self.client.get(url), '/login/?next=' + url,
                                 fetch_redirect_response=False)
        with patch('gestion.views.trabajadores_collection') as collection:
            urls = [reverse('agregar_trabajador')]
            urls += [reverse(nombre, args=[str(ObjectId())]) for nombre in
                     ('editar_trabajador', 'eliminar_trabajador')]
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 302)
                self.assertEqual(self.client.post(url, {}).status_code, 302)
            self.assertEqual(collection.mock_calls, [])

    def test_login_correcto_y_destino(self):
        self.assertContains(self.client.get(reverse('login')), 'Iniciar sesión')
        response = self.client.post(reverse('login'), {
            'username': 'operador', 'password': 'ClavePrueba-789',
            'next': reverse('reportes'),
        })
        self.assertRedirects(response, reverse('reportes'))
        self.assertContains(self.client.get(reverse('inicio')), 'Cerrar sesión')

    def test_autentica_trabajador_desde_mongodb(self):
        trabajador_id = ObjectId()
        cuenta_trabajador = {
                '_id': ObjectId(), 'trabajador_id': trabajador_id,
                'rut': '12345678-5',
                'nombre': 'Ana',
                'apellido': 'Perez',
                'rol': 'trabajador',
                'cuadrilla_id': 'Equipo A',
                'password': make_password('Cosecha-Segura-827!'),
            }
        with patch('gestion.backends.trabajadores_collection') as collection, \
             patch('gestion.backends.usuarios_collection') as usuarios:
            usuarios.find_one.side_effect = lambda filtro: (
                None if filtro.get('rol') == 'administrador' else cuenta_trabajador
            )
            collection.find_one.return_value = {
                '_id': trabajador_id, 'rut': '12345678-5', 'nombre': 'Ana',
                'apellido': 'Perez', 'rol': 'Trabajador', 'cuadrilla_id': 'Equipo A',
            }
            usuario = authenticate(
                username='12345678-5', password='Cosecha-Segura-827!'
            )
        self.assertIsNotNone(usuario)
        self.assertFalse(usuario.has_usable_password())
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(usuario.perfil_agricola.rol, 'trabajador')
        self.assertEqual(usuario.perfil_agricola.trabajador_id, str(trabajador_id))

    def test_autentica_cada_coleccion_con_su_rol(self):
        casos = (
            ('jefe', 'Jefe de Cuadrilla', '21000001-1'),
            ('gerencia', 'Gerencia', '21000002-2'),
            ('recursos_humanos', 'Recursos Humanos', '21000003-3'),
        )
        for rol, nombre_rol, rut in casos:
            with self.subTest(rol=rol):
                trabajador_id = ObjectId()
                cuenta_rol = {
                    '_id': ObjectId(), 'trabajador_id': trabajador_id, 'rut': rut,
                    'nombre': 'Cuenta', 'apellido': nombre_rol, 'rol': rol,
                    'cuadrilla_id': 'CUAD-01' if rol == 'jefe' else '',
                    'password': make_password('Clave-Rol-957!'), 'activo': True,
                }
                with patch('gestion.backends.trabajadores_collection') as fichas, \
                     patch('gestion.backends.usuarios_collection') as usuarios:
                    usuarios.find_one.side_effect = lambda filtro: (
                        None if filtro.get('rol') == 'administrador' else cuenta_rol
                    )
                    fichas.find_one.return_value = {
                        '_id': trabajador_id, 'rut': rut, 'nombre': 'Cuenta',
                        'apellido': nombre_rol, 'rol': nombre_rol,
                        'cuadrilla_id': 'CUAD-01' if rol == 'jefe' else '',
                    }
                    usuario = authenticate(username=rut, password='Clave-Rol-957!')
                self.assertIsNotNone(usuario)
                self.assertEqual(usuario.perfil_agricola.rol, rol)
                self.assertEqual(
                    usuario.perfil_agricola.cuadrilla_id,
                    'CUAD-01' if rol == 'jefe' else '',
                )

    def test_login_incorrecto(self):
        response = self.client.post(reverse('login'), {
            'username': 'operador', 'password': 'incorrecta',
        })
        self.assertContains(response, 'No pudimos iniciar sesión')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_destino_externo_no_se_permite(self):
        response = self.client.post(reverse('login'), {
            'username': 'operador', 'password': 'ClavePrueba-789',
            'next': 'https://example.com/',
        })
        self.assertRedirects(response, reverse('inicio'))

    def test_logout_y_login_exigen_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(reverse('login'), {}).status_code, 403)
        client.force_login(self.usuario)
        self.assertEqual(client.get(reverse('logout')).status_code, 405)
        self.assertEqual(client.post(reverse('logout')).status_code, 403)
        client.get(reverse('inicio'))
        response = client.post(reverse('logout'), {
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', client.session)
        self.assertEqual(client.get(reverse('inicio')).status_code, 302)


class CrearCuentaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('admincuentas', password='Prueba-789!')
        cls.operador = get_user_model().objects.create_user('operadorcuentas')

    def setUp(self):
        patcher = patch('gestion.views.trabajadores_collection')
        self.collection = patcher.start()
        self.addCleanup(patcher.stop)
        self.collection.find_one.return_value = None
        usuarios_patcher = patch('gestion.db.usuarios_collection')
        self.usuarios = usuarios_patcher.start()
        self.addCleanup(usuarios_patcher.stop)
        self.usuarios.find_one.return_value = None

    def datos(self, username, rol):
        return {'username': username, 'rol': rol, 'cuadrilla_id': 'Equipo-A',
                'primer_nombre': 'Ana', 'segundo_nombre': 'Maria', 'apellido_paterno': 'Perez', 'apellido_materno': 'Soto',
                'rut': '11111111-1' if rol == 'jefe' else '12345678-5', 'collera_id': 'P01',
                'password1': 'Cosecha-Segura-827!', 'password2': 'Cosecha-Segura-827!',
                'is_superuser': 'true', 'is_staff': 'true'}

    def test_crea_ambos_perfiles_sin_privilegios(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('crear_cuenta')), 'Tipo de cuenta')
        for rol in ('jefe', 'trabajador'):
            response = self.client.post(reverse('crear_cuenta'), self.datos('nuevo_' + rol, rol))
            self.assertRedirects(response, reverse('crear_cuenta'))
            usuario = get_user_model().objects.get(username='11111111-1' if rol == 'jefe' else '12345678-5')
            self.assertFalse(usuario.has_usable_password())
            self.assertFalse(usuario.is_staff)
            self.assertFalse(usuario.is_superuser)
            self.assertEqual(usuario.perfil_agricola.rol, rol)
            ficha = self.collection.insert_one.call_args[0][0]
            self.assertEqual(str(ficha['_id']), usuario.perfil_agricola.trabajador_id)
            self.assertEqual(ficha['nombre'], 'Ana Maria')
            self.assertEqual(ficha['apellido'], 'Perez Soto')
            self.assertEqual(ficha['segundo_nombre'], 'Maria')
            self.assertEqual(ficha['apellido_materno'], 'Soto')
            self.assertEqual(ficha['cuadrilla_id'], 'Equipo-A')
            self.assertEqual(ficha['collera_id'], '' if rol == 'jefe' else 'P01')
            self.assertNotIn('password', ficha)
            cuenta = self.usuarios.insert_one.call_args.args[0]
            self.assertEqual(cuenta['trabajador_id'], ficha['_id'])
            self.assertEqual(cuenta['rol'], rol)
            self.assertTrue(check_password('Cosecha-Segura-827!', cuenta['password']))
            self.assertEqual(usuario.perfil_agricola.cuadrilla_id, 'Equipo-A' if rol == 'jefe' else '')

    def test_crea_cuentas_de_recursos_humanos_y_gerencia(self):
        self.client.force_login(self.admin)
        formulario = self.client.get(reverse('crear_cuenta'))
        self.assertContains(formulario, 'Recursos Humanos')
        self.assertContains(formulario, 'Gerencia')
        for rut, tipo, nombre in (
            ('11111111-1', 'recursos_humanos', 'Recursos Humanos'),
            ('12345678-5', 'gerencia', 'Gerencia'),
        ):
            datos = self.datos('nuevo', tipo)
            datos['rut'] = rut
            response = self.client.post(reverse('crear_cuenta'), datos)
            self.assertRedirects(response, reverse('crear_cuenta'))
            usuario = get_user_model().objects.get(username=rut)
            self.assertEqual(usuario.perfil_agricola.rol, tipo)
            self.assertFalse(usuario.is_staff)
            self.assertFalse(usuario.is_superuser)
            self.assertEqual(self.collection.insert_one.call_args.args[0]['rol'], nombre)
            self.assertEqual(self.collection.insert_one.call_args.args[0]['collera_id'], '')
            self.assertEqual(self.collection.insert_one.call_args.args[0]['cuadrilla_id'], '')
            cuenta = self.usuarios.insert_one.call_args.args[0]
            self.assertEqual(cuenta['rut'], rut)
            self.assertEqual(cuenta['rol'], tipo)
            self.assertTrue(check_password('Cosecha-Segura-827!', cuenta['password']))

    def test_rechaza_errores_sin_crear_cuentas(self):
        self.client.force_login(self.admin)
        casos = [dict(rol='administrador'), dict(password2='distinta'),
                 dict(cuadrilla_id=''), dict(primer_nombre=''),
                 dict(password1='123', password2='123')]
        for cambios in casos:
            datos = self.datos('invalido', 'jefe')
            datos.update(cambios)
            response = self.client.post(reverse('crear_cuenta'), datos)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertEqual(get_user_model().objects.count(), 2)
        self.assertEqual(PerfilUsuario.objects.count(), 0)

    def test_solo_administrador_puede_crear(self):
        url = reverse('crear_cuenta')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.operador)
        for rol in ('trabajador', 'jefe'):
            PerfilUsuario.objects.update_or_create(usuario=self.operador, defaults={'rol': rol})
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.datos('prohibido', rol)).status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username='prohibido').exists())


    def test_fallo_mongo_no_deja_cuenta_ni_perfil(self):
        from pymongo.errors import ConnectionFailure
        self.client.force_login(self.admin)
        self.collection.insert_one.side_effect = ConnectionFailure('sin conexion')
        response = self.client.post(reverse('crear_cuenta'), self.datos('fallido', 'trabajador'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertFalse(get_user_model().objects.filter(username='fallido').exists())
        self.assertEqual(PerfilUsuario.objects.count(), 0)

    def test_rut_duplicado_no_crea_cuenta(self):
        self.client.force_login(self.admin)
        self.collection.find_one.return_value = {'rut': '12345678-5'}
        response = self.client.post(reverse('crear_cuenta'), self.datos('duplicado', 'trabajador'))
        self.assertTrue(response.context['form'].non_field_errors())
        self.collection.insert_one.assert_not_called()
        self.assertFalse(get_user_model().objects.filter(username='duplicado').exists())

    def test_rut_invalido_no_escribe(self):
        self.client.force_login(self.admin)
        datos = self.datos('invalido', 'trabajador')
        datos['rut'] = '12345678-0'
        response = self.client.post(reverse('crear_cuenta'), datos)
        self.assertIn('rut', response.context['form'].errors)
        self.collection.insert_one.assert_not_called()


class OperacionAgricolaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            'admin_operacion', password='Clave-Operacion-789!'
        )
        cls.jefe = get_user_model().objects.create_user('jefe_operacion')
        cls.trabajador = get_user_model().objects.create_user('trabajador_operacion')
        cls.jefe_id = ObjectId()
        cls.trabajador_id = ObjectId()
        PerfilUsuario.objects.create(
            usuario=cls.jefe, rol='jefe', trabajador_id=str(cls.jefe_id), cuadrilla_id='CUAD-01'
        )
        PerfilUsuario.objects.create(
            usuario=cls.trabajador, rol='trabajador', trabajador_id=str(cls.trabajador_id)
        )

    def test_administrador_forma_collera_de_dos_trabajadores(self):
        trabajador_2 = ObjectId()
        personal = [
            {'_id': self.trabajador_id, 'nombre': 'Ana', 'apellido': 'Pérez', 'rut': '12345678-5',
             'rol': 'Trabajador', 'cuadrilla_id': 'CUAD-01', 'collera_id': ''},
            {'_id': trabajador_2, 'nombre': 'Luis', 'apellido': 'Soto', 'rut': '11111111-1',
             'rol': 'Trabajador', 'cuadrilla_id': 'CUAD-01', 'collera_id': ''},
        ]
        self.client.force_login(self.admin)
        with patch('gestion.views.cuadrillas_collection') as cuadrillas, \
             patch('gestion.views.trabajadores_collection') as trabajadores, \
             patch('gestion.views.colleras_collection') as colleras:
            cuadrillas.find.return_value.sort.return_value = [
                {'_id': ObjectId(), 'codigo': 'CUAD-01', 'nombre': 'Cosecha Norte'}
            ]
            trabajadores.find.return_value.sort.return_value = personal
            colleras.find_one.return_value = None
            colleras.insert_one.return_value.inserted_id = ObjectId()
            response = self.client.post(reverse('colleras'), {
                'codigo': 'COL-01', 'cuadrilla_id': 'CUAD-01',
                'trabajadores': [str(self.trabajador_id), str(trabajador_2)], 'activa': 'on',
            })
            self.assertRedirects(response, reverse('colleras'), fetch_redirect_response=False)
            documento = colleras.insert_one.call_args.args[0]
            self.assertEqual(documento['codigo'], 'COL-01')
            self.assertEqual(len(documento['trabajadores_ids']), 2)
            trabajadores.update_many.assert_called_once()

    def test_trabajador_no_administra_colleras(self):
        self.client.force_login(self.trabajador)
        self.assertEqual(self.client.get(reverse('colleras')).status_code, 403)

    def test_jefe_registra_jornada_solo_para_su_cuadrilla(self):
        cuartel_id = ObjectId()
        personal = [{
            '_id': self.trabajador_id, 'nombre': 'Ana', 'apellido': 'Pérez',
            'rol': 'Trabajador', 'cuadrilla_id': 'CUAD-01', 'collera_id': 'COL-01',
        }]
        self.client.force_login(self.jefe)
        with patch('gestion.views.trabajadores_collection') as trabajadores, \
             patch('gestion.views.cuarteles_collection') as cuarteles, \
             patch('gestion.views.jornadas_collection') as jornadas:
            trabajadores.find.return_value.sort.return_value = personal
            cuarteles.find.return_value.sort.return_value = [{
                '_id': cuartel_id, 'codigo': 'CT-01', 'nombre': 'Norte', 'huerto_nombre': 'Cerezos',
            }]
            jornadas.find_one.return_value = None
            response = self.client.post(reverse('jornadas'), {
                'fecha': '2026-09-30', 'trabajador_id': str(self.trabajador_id),
                'cuartel_id': str(cuartel_id), 'asistencia': 'Presente',
                'hora_entrada': '08:00', 'hora_salida': '17:00', 'labor': 'Cosecha',
                'kilos': '125.50', 'calidad': 'Primera', 'perdidas_kg': '2.50',
                'observaciones': 'Jornada normal',
            })
            self.assertRedirects(response, reverse('jornadas'), fetch_redirect_response=False)
            documento = jornadas.insert_one.call_args.args[0]
            self.assertEqual(documento['cuadrilla_id'], 'CUAD-01')
            self.assertEqual(documento['collera_id'], 'COL-01')
            self.assertEqual(documento['horas_trabajadas'], 9)
            self.assertFalse(documento['validado'])

    def test_trabajador_consulta_solo_sus_jornadas(self):
        self.client.force_login(self.trabajador)
        jornada = {
            '_id': ObjectId(), 'fecha': '2026-09-30', 'trabajador_id': self.trabajador_id,
            'trabajador_nombre': 'Ana Pérez', 'cuadrilla_id': 'CUAD-01', 'collera_id': '',
            'cuartel_codigo': 'CT-01', 'labor': 'Cosecha', 'asistencia': 'Presente',
            'hora_entrada': '08:00', 'hora_salida': '17:00', 'horas_trabajadas': 9,
            'kilos': 100, 'perdidas_kg': 1, 'calidad': 'Primera', 'validado': True,
        }
        with patch('gestion.views.jornadas_collection') as jornadas, \
             patch('gestion.views.trabajadores_collection') as trabajadores:
            jornadas.find.return_value.sort.return_value = [jornada]
            trabajadores.find_one.return_value = {'_id': self.trabajador_id, 'collera_id': ''}
            response = self.client.get(reverse('jornadas'))
            self.assertContains(response, 'Ana Pérez')
            self.assertNotContains(response, 'Registrar jornada')
            jornadas.find.assert_called_once_with({'trabajador_id': self.trabajador_id})
