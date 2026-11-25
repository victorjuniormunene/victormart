from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.customer_dashboard_view, name='customer_dashboard'),
    path('supplier/', views.supplier_dashboard_view, name='supplier_dashboard'),
    path('order-history/', views.order_history_view, name='order_history'),
    path('download-customer-report/', views.download_customer_report, name='download_customer_report'),
    path('download-supplier-report/', views.download_supplier_report, name='download_supplier_report'),
]
