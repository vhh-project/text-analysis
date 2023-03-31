from django.db import models


class Status(models.IntegerChoices):
    QUEUED = 0, "Queued"
    ERROR = 1, "Error"
    PROCESSING = 2, "Processing"
    FINISHED = 3, "Finished"


class RunResult(models.Model):
    data = models.JSONField()


class Run(models.Model):
    user_id = models.CharField(max_length=30)
    task_id = models.CharField(max_length=36)
    file_name = models.CharField(max_length=191)
    bucket = models.CharField(max_length=191, default="")
    minio_path = models.CharField(max_length=191)
    upload_date = models.DateTimeField(null=True)
    error = models.TextField(null=True)
    lang = models.TextField(null=True)
    page_count = models.IntegerField(null=True)
    review_complete = models.IntegerField(null=True, default=False)
    pdf_uptodate = models.IntegerField(null=True, default=True)
    latest_review_date = models.DateTimeField(null=True)
    finish_date = models.DateTimeField(null=True)
    marked_complete = models.IntegerField(null=True, default=False)
    has_tiff = models.IntegerField(null=True, default=False)
    folder_size = models.IntegerField(null=True, default=False)

    result_data = models.OneToOneField(
        RunResult,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='run'
    )
    status = models.IntegerField(
        null=False,
        default=Status.QUEUED,
        choices=Status.choices
    )
    result_prep = models.JSONField(null=True)


class PipelineRun(models.Model):
    correlation_id = models.CharField(max_length=36)
    run = models.ForeignKey(Run, on_delete=models.CASCADE)
    result = models.JSONField(null=True)
    error = models.TextField(null=True)
    page_num = models.IntegerField(null=True)
