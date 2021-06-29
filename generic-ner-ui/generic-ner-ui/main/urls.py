from django.urls import path

from . import views

"""Register urls here
"""

urlpatterns = [
    path("", views.base_page, name="base"),
    path("upload", views.upload, name="upload"),
    path("admin", views.admin_page, name="admin"),
    path("view/<str:id>", views.details, name="details"),
    path("delete_paths", views.delete_files, name="delete_files"),
    path("delete/<str:id>", views.delete, name="delete"),
    path("view/<str:id>/<str:view>", views.details, name="details"),
    path("img/<str:id>/<int:page>.png", views.image, name="image"),
    path("ocr_data.zip", views.download_all, name="download_data"),
    path("<str:id>/result.pdf", views.download_pdf, name="download_pdf"),
    path("<str:id>/original", views.download_original, name="download_original"),
    path("uploads", views.upload_view, name="upload_view"),
    path("updates", views.check_status_updates, name="check_status_updates"),
    path("corrections", views.update_human_corrections, name="update_human_corrections"),
]
