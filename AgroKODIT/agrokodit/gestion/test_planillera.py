from unittest.mock import patch

from bson import ObjectId
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase, RequestFactory
from django.urls import reverse

from .backends import MongoTrabajadorBackend
from .models import PerfilUsuario
from .views import _jornada_permitida
from .forms import JornadaForm


class PlanilleraTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='planillera')
        PerfilUsuario.objects.create(usuario=self.user, rol='cuenta_plenillera')
        self.client.force_login(self.user)

    def test_panel_and_account_choices(self):
        response = self.client.get(reverse('inicio'))
        self.assertContains(response, 'Panel de Planillera')
        self.assertIn(('cuenta_plenillera', 'Planillera'), PerfilUsuario._meta.get_field('rol').choices)

    def test_cannot_create_accounts_or_assign_payments(self):
        self.assertEqual(self.client.get(reverse('crear_cuenta')).status_code, 403)
        self.assertEqual(self.client.post(reverse('trabajadores'), {}).status_code, 403)

    def test_can_manage_jornadas(self):
        request = RequestFactory().get('/')
        request.user = self.user
        self.assertTrue(_jornada_permitida(request, {'cuadrilla_id': 'otra'}))

    def harvest_form(self, **changes):
        self.worker_id, self.cuartel_id = ObjectId(), ObjectId()
        data = {
            'fecha': '2026-10-08', 'trabajador_id': str(self.worker_id),
            'cuartel_id': str(self.cuartel_id), 'asistencia': 'Presente',
            'hora_entrada': '08:00', 'hora_salida': '17:00', 'labor': 'Cosecha',
            'kilos': '120.50', 'capachos': '12', 'bines': '3',
            'bines_con_hojas': 'BIN-01, BIN-03', 'calidad': 'Primera', 'perdidas_kg': '0',
        }
        data.update(changes)
        self.personal = [{'_id': self.worker_id, 'nombre': 'Ana', 'rol': 'Trabajador'}]
        self.cuarteles = [{'_id': self.cuartel_id, 'codigo': 'CT-01'}]
        return JornadaForm(data, trabajadores=self.personal, cuarteles=self.cuarteles)

    def test_saves_and_displays_daily_harvest(self):
        form = self.harvest_form()
        with patch('gestion.views.trabajadores_collection') as workers, patch('gestion.views.cuarteles_collection') as cuarteles, patch('gestion.views.jornadas_collection') as jornadas:
            workers.find.return_value.sort.return_value = self.personal
            cuarteles.find.return_value.sort.return_value = self.cuarteles
            jornadas.find_one.return_value = None
            response = self.client.post(reverse('jornadas'), form.data)
            self.assertEqual(response.status_code, 302)
            doc = jornadas.insert_one.call_args.args[0]
            self.assertEqual(doc['kilos'], 120.5)
            self.assertEqual(doc['capachos'], 12)
            self.assertEqual(doc['bines'], 3)
            self.assertEqual(doc['bines_con_hojas'], ['BIN-01', 'BIN-03'])
            self.assertEqual(doc['asistencia'], 'Presente')
            jornadas.find.return_value.sort.return_value = [{'_id': ObjectId(), **doc}]
            response = self.client.get(reverse('jornadas'))
            self.assertContains(response, '12 capachos')
            self.assertContains(response, 'BIN-01, BIN-03')

    def test_rejects_invalid_counts_and_leaf_bins(self):
        for changes, field in [({'capachos': '-1'}, 'capachos'), ({'bines': '1.5'}, 'bines'), ({'bines': '1'}, 'bines_con_hojas'), ({'bines_con_hojas': 'B1,B1'}, 'bines_con_hojas'), ({'asistencia': 'Ausente'}, 'capachos')]:
            with self.subTest(changes=changes):
                form = self.harvest_form(**changes)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_legacy_submissions_default_new_counts_to_zero(self):
        form = self.harvest_form(capachos='', bines='', bines_con_hojas='')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['capachos'], 0)
        self.assertEqual(form.cleaned_data['bines'], 0)

    @patch('gestion.backends.usuarios_collection')
    def test_authenticates_database_role(self, collection):
        collection.find_one.return_value = {
            '_id': ObjectId(), 'rut': '12345678-5', 'rol': 'cuenta_plenillera',
            'password': make_password('ClaveDePrueba123!'), 'nombre': 'Ana',
        }
        user = MongoTrabajadorBackend().authenticate(None, username='12345678-5', password='ClaveDePrueba123!')
        self.assertIsNotNone(user)
        self.assertEqual(user.perfil_agricola.rol, 'cuenta_plenillera')
        self.assertFalse(user.is_superuser)
        self.assertIn('cuenta_plenillera', collection.find_one.call_args.args[0]['rol']['$in'])
