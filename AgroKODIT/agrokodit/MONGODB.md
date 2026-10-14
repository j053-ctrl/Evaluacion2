# Conexión con MongoDB Atlas

La aplicación carga automáticamente `MONGO_URI` y `MONGO_DB_NAME` desde el archivo local `.env`. Este archivo está excluido por `.gitignore`: no lo subas al repositorio ni publiques sus credenciales.

Para preparar otro equipo, copia `.env.example` como `.env` y reemplaza los datos de ejemplo con la cadena entregada por Atlas.

También puedes usar variables de entorno. Estas tienen prioridad sobre el archivo `.env`:

```powershell
$mongoSecret = Read-Host 'Cadena de conexión de Atlas' -AsSecureString
$env:MONGO_URI = [System.Net.NetworkCredential]::new('', $mongoSecret).Password
$env:MONGO_DB_NAME = 'agrokodit'
python manage.py comprobar_mongodb
python manage.py runserver
```

Estas variables se aplican a esa terminal y al servidor que se inicie desde ella. El usuario de base de datos necesita permisos de lectura y escritura sobre `agrokodit`, y Atlas debe permitir la conexión desde la red del servidor.

## Estado real

- Las fichas creadas en Crear cuenta se guardan en la colección `trabajadores` mediante PyMongo y se vinculan al perfil de acceso.
- La estructura agrícola usa las colecciones `predios`, `huertos`, `cuarteles`, `cuadrillas` y `colleras`.
- La asistencia, labor, producción, calidad, pérdidas y validación diaria se guardan en `jornadas`.
- Todas las credenciales se guardan en una sola colección `usuarios`. Cada documento contiene RUT, contraseña cifrada, rol y estado. Las cuentas operativas mantienen además el `trabajador_id` que las vincula con su ficha agrícola.
- La cuenta, su hash de contraseña, el perfil y las sesiones todavía se guardan en SQLite mediante Django.
- La conexión con un clúster real requiere configurar MONGO_URI y ejecutar la comprobación. Las pruebas con MongoDB simulado no certifican acceso a Atlas.
- Esta configuración no migra ni borra datos existentes. La aplicación crea las colecciones operativas al guardar el primer documento.

## Unificar cuentas existentes

Las cuentas nuevas se guardan directamente en `usuarios`. Para copiar cuentas antiguas desde las colecciones anteriores, ejecuta:

```powershell
python manage.py migrar_usuarios
```

Los administradores antiguos que no tengan un RUT válido se omiten y deben recrearse desde el formulario de Administradores.
