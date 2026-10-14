from unittest.mock import patch
from bson import ObjectId
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import PerfilUsuario


class ReportesEnviadosTests(TestCase):
    def setUp(self):
        self.planillera = get_user_model().objects.create_user('planillera')
        PerfilUsuario.objects.create(usuario=self.planillera, rol='cuenta_plenillera')
        self.admin = get_user_model().objects.create_superuser('admin', password='Prueba123!')
        self.worker = get_user_model().objects.create_user('trabajador')
        self.client.force_login(self.planillera)
        self.url = reverse('reportes_enviados')
        self.data = {'titulo': 'Cosecha diaria', 'fecha': '2026-10-08', 'contenido': '120 kilos, 12 capachos, 3 bines. BIN-01 con hojas.', 'accion': 'enviar'}

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_planillera_sends_report(self, collection):
        response = self.client.post(self.url, self.data)
        self.assertEqual(response.status_code, 302)
        doc = collection.insert_one.call_args.args[0]
        self.assertEqual(doc['estado'], 'enviado')
        self.assertEqual(doc['autor'], 'planillera')
        self.assertIn('BIN-01', doc['contenido'])

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_edit_draft_and_block_edit_after_send(self, collection):
        oid = ObjectId()
        for estado, expected in [('borrador', 302), ('devuelto', 302), ('enviado', 403), ('publicado', 403)]:
            with self.subTest(estado=estado):
                collection.find_one.return_value = {'_id': oid, 'autor': 'planillera', 'estado': estado}
                response = self.client.post(self.url, {**self.data, 'id': str(oid), 'accion': 'guardar'})
                self.assertEqual(response.status_code, expected)
        self.assertEqual(collection.update_one.call_count, 2)

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_only_admin_can_publish(self, collection):
        oid = ObjectId()
        collection.find_one.return_value = {'_id': oid, 'estado': 'enviado', 'autor': 'planillera'}
        data = {'id': str(oid), 'accion': 'publicar'}
        self.assertEqual(self.client.post(self.url, data).status_code, 403)
        collection.update_one.assert_not_called()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        self.assertEqual(collection.update_one.call_args.args[1]['$set']['estado'], 'publicado')

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_admin_returns_for_correction(self, collection):
        self.client.force_login(self.admin)
        oid=ObjectId()
        collection.find_one.return_value={'_id':oid, 'estado':'enviado', 'autor':'planillera'}
        self.client.post(self.url, {'id':str(oid), 'accion':'devolver', 'comentario_admin':'Revisar kilos'})
        saved=collection.update_one.call_args.args[1]['$set']
        self.assertEqual(saved['estado'], 'devuelto')
        self.assertEqual(saved['comentario_admin'], 'Revisar kilos')

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_worker_only_sees_published_and_cannot_write(self, collection):
        self.client.force_login(self.worker)
        collection.find.return_value.sort.return_value=[]
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(collection.find.call_args_list[0].args[0], {'estado':'publicado'})
        self.assertEqual(self.client.post(self.url,self.data).status_code,403)

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_cannot_open_another_authors_draft(self, collection):
        collection.find_one.return_value=None
        oid=ObjectId()
        self.assertEqual(self.client.get(self.url, {'editar':str(oid)}).status_code,404)
        self.assertEqual(collection.find_one.call_args.args[0]['autor'], 'planillera')

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_admin_can_publish_all_sent_reports(self, collection):
        self.client.force_login(self.admin)
        collection.update_many.return_value.modified_count = 3
        response = self.client.post(self.url, {'accion': 'publicar_todos'})
        self.assertEqual(response.status_code, 302)
        filters, update = collection.update_many.call_args.args
        self.assertEqual(filters, {'estado': 'enviado'})
        self.assertEqual(update['$set']['estado'], 'publicado')
        self.assertEqual(update['$set']['revisado_por'], 'admin')
        self.assertIn('publicado_en', update['$set'])

    @patch('gestion.reportes_enviados.reportes_collection')
    def test_planillera_cannot_publish_all(self, collection):
        self.assertEqual(self.client.post(self.url, {'accion': 'publicar_todos'}).status_code, 403)
        collection.update_many.assert_not_called()
