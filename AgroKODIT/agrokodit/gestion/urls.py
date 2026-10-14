from django.urls import path
from django.contrib.auth.views import LoginView
from . import views
from .reportes_enviados import reportes_enviados

urlpatterns = [
    path('reportes/enviados/', reportes_enviados, name='reportes_enviados'),
    path('recuperar-cuenta/', views.recuperar_cuenta, name='recuperar_cuenta'),
    path('administradores/', views.administradores, name='administradores'),
    path('cuentas/crear/', views.crear_cuenta, name='crear_cuenta'),
    path('login/', LoginView.as_view(template_name='gestion/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', views.cerrar_sesion, name='logout'),
    path('', views.inicio, name='inicio'),
    path('trabajadores/', views.trabajadores, name='trabajadores'),
    path('predios/', views.predios, name='predios'),
    path('predios/<str:id>/editar/', views.editar_predio, name='editar_predio'),
    path('predios/<str:id>/eliminar/', views.eliminar_predio, name='eliminar_predio'),
    path('huertos/', views.huertos, name='huertos'),
    path('huertos/<str:id>/editar/', views.editar_huerto, name='editar_huerto'),
    path('huertos/<str:id>/eliminar/', views.eliminar_huerto, name='eliminar_huerto'),
    path('cuarteles/', views.cuarteles, name='cuarteles'),
    path('cuarteles/<str:id>/editar/', views.editar_cuartel, name='editar_cuartel'),
    path('cuarteles/<str:id>/eliminar/', views.eliminar_cuartel, name='eliminar_cuartel'),
    path('cuadrillas/', views.cuadrillas, name='cuadrillas'),
    path('cuadrillas/<str:id>/editar/', views.editar_cuadrilla, name='editar_cuadrilla'),
    path('cuadrillas/<str:id>/eliminar/', views.eliminar_cuadrilla, name='eliminar_cuadrilla'),
    path('colleras/', views.colleras, name='colleras'),
    path('colleras/<str:id>/editar/', views.editar_collera, name='editar_collera'),
    path('colleras/<str:id>/eliminar/', views.eliminar_collera, name='eliminar_collera'),
    path('jornadas/', views.jornadas, name='jornadas'),
    path('jornadas/<str:id>/validar/', views.validar_jornada, name='validar_jornada'),
    path('jornadas/<str:id>/eliminar/', views.eliminar_jornada, name='eliminar_jornada'),
    path('reportes/', views.reportes, name='reportes'),
    path('trabajadores/agregar/', views.agregar_trabajador, name='agregar_trabajador'),
    path('trabajadores/<str:id>/editar/', views.editar_trabajador, name='editar_trabajador'),
    path('trabajadores/<str:id>/eliminar/', views.eliminar_trabajador, name='eliminar_trabajador'),
]
