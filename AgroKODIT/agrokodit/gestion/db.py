import os

from pymongo import MongoClient

from agrokodit.environment import load_environment


load_environment()

MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    raise RuntimeError(
        'Falta MONGO_URI. Copia .env.example como .env y configura tu conexion de MongoDB Atlas.'
    )

cliente = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    connect=False,
    appname='AgroKODIT',
)

db = cliente[os.environ.get('MONGO_DB_NAME', 'agrokodit')]

trabajadores_collection = db["trabajadores"]
administradores_collection = db["administradores"]
predios_collection = db["predios"]
huertos_collection = db["huertos"]
cuarteles_collection = db["cuarteles"]
cuadrillas_collection = db["cuadrillas"]
colleras_collection = db["colleras"]
jornadas_collection = db["jornadas"]
usuarios_collection = db["usuarios"]
reportes_collection = db["reportes"]


