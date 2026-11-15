from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="web-index"),
    path("upload/", views.UiUploadView.as_view(), name="web-upload"),
    path("jobs/<str:job_id>/", views.job_page, name="web-job"),
]
