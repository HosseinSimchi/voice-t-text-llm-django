from django.urls import path

from . import api

urlpatterns = [
    path("jobs/", api.JobCreateView.as_view(), name="api-job-create"),
    path("jobs/<str:job_id>/", api.JobStatusView.as_view(), name="api-job-status"),
    path("jobs/<str:job_id>/results/", api.JobResultsView.as_view(), name="api-job-results"),
    path("jobs/<str:job_id>/download/", api.JobResultsZipView.as_view(), name="api-job-download"),
    path("results/<str:result_id>/download/", api.ResultDownloadView.as_view(), name="api-result-download"),
]
