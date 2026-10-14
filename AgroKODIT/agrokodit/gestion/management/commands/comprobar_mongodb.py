import os

from django.core.management.base import BaseCommand, CommandError
from pymongo import MongoClient
from pymongo.errors import PyMongoError


class Command(BaseCommand):
    help = 'Comprueba la conexión configurada con MongoDB sin modificar datos.'

    def handle(self, *args, **options):
        uri = os.environ.get('MONGO_URI')
        if not uri:
            raise CommandError('Falta configurar MONGO_URI en el entorno que inicia Django.')
        try:
            with MongoClient(uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000) as client:
                client.admin.command('ping')
                client[os.environ.get('MONGO_DB_NAME', 'agrokodit')]['trabajadores'].find_one({}, {'_id': 1})
        except (PyMongoError, ValueError):
            raise CommandError('No se pudo acceder a MongoDB. Revisa la URI, las credenciales, los permisos y el acceso de red.') from None
        self.stdout.write(self.style.SUCCESS('Conexión y lectura de trabajadores verificadas. No se modificaron datos.'))
