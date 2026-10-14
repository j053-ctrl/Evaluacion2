# Perfiles de AgroKODIT

Adaptación de los permisos del informe, secciones 5, 6 y HU-03.

- Administrador: cuenta almacenada en la colección `administradores` de MongoDB Atlas, separada de `trabajadores`. Conserva la gestión de trabajadores y el acceso a estructura y reportes. La aplicación mantiene un usuario Django interno sin contraseña utilizable para las sesiones y el acceso a `/admin/`.
- Administrador, trabajador, jefe de cuadrilla, Recursos Humanos y Gerencia: sus credenciales cifradas se almacenan en la colección `usuarios`, diferenciadas por el campo `rol`. La colección `trabajadores` conserva la ficha agrícola común del personal, vinculada mediante `trabajador_id`. Django mantiene únicamente el usuario interno y el perfil necesarios para la sesión y los permisos.
- Jefe de cuadrilla: perfil con rol Jefe de cuadrilla y código de cuadrilla a cargo. Consulta exclusivamente las fichas de esa cuadrilla. No modifica personal ni estructura territorial.
- Trabajador: perfil vinculado al ID de su ficha MongoDB. Solo consulta su ficha personal. No accede al listado general ni a la estructura territorial.
- Una cuenta sin perfil o asignación no obtiene acceso a datos ajenos. Es staff no concede permisos de administrador agrícola.

## Configuración

1. Ingresar como administrador y crear las cuentas desde Usuarios. Las cuentas operativas no deben ser staff ni superusuarios ni recibir permisos de gestión de usuarios.
2. Crear o editar la ficha del trabajador. El ID se muestra en la columna Acciones. Asignar códigos de cuadrilla y collera según corresponda.
3. Abrir Perfiles y asignaciones y seleccionar la cuenta, el rol y su ID de trabajador. Para un jefe, indicar el mismo código de cuadrilla utilizado en las fichas del equipo.
4. El rol laboral de la ficha MongoDB es descriptivo: no otorga privilegios de acceso.

Las cuentas y perfiles de autenticación se guardan en la base Django existente (SQLite); las fichas del personal permanecen en MongoDB. No se migraron todos los datos a Atlas.

## Alcance operativo

El proyecto cuenta con CRUD territorial para predios, huertos y cuarteles, organización de cuadrillas, validación de colleras de dos trabajadores y registro de jornadas. Cada jornada relaciona fecha, trabajador, cuadrilla, collera, cuartel, asistencia, horario, labor, kilos, calidad, pérdidas, observaciones y cierre validado.

- El trabajador consulta sus jornadas completas y el total producido por su collera, sin exponer la ficha personal de su pareja.
- El jefe registra, consulta, valida y elimina únicamente jornadas de su cuadrilla.
- El administrador gestiona todas las jornadas y obtiene reportes filtrables y exportables por trabajador, collera, cuadrilla, cuartel o día.
- Gerencia y Recursos Humanos mantienen acceso de consulta, sin permisos para modificar registros operativos.

Una aplicación móvil, una API HTTP y la sincronización offline no forman parte del prototipo web actual.
