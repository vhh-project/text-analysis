from pathlib import Path
import tempfile

from loguru import logger

from ocr_pipeline.pipeline.pipeline import Pipeline
from ocr_pipeline.service.config import Config
from ocr_pipeline.service.filestorage import FileStorage


class Processor:
    def __init__(self, config: Config, fs: FileStorage):
        self.config = config
        self.fs = fs
        self.pipeline = Pipeline(config.pipeline)
        self.pipeline.setup()
        # TODO: do everything that should be initialized once (e.g. bert model)

    def run(self, body: dict) -> dict:
        logger.info("Processing message {}", body)
        lang = body.get("lang", self.pipeline.config.tess_lang)
        file = body["minio"]

        with tempfile.TemporaryDirectory(prefix="preprocessing") as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            tmp_file = tmp_dir_path / file
            case_folder = tmp_file.parent
            case_folder.mkdir(parents=True, exist_ok=True)
            self.fs.get(file, tmp_file)
            results = self.pipeline.process_single(tmp_file, lang)

            return self.upload_files(tmp_dir_path, results)

    def upload_files(self, case_folder: Path, d: dict) -> dict:
        for key in d.keys():
            if isinstance(d[key], Path):
                logger.info(f" [{case_folder}] - {key}: {d[key]}")
                d[key] = self.upload_file(case_folder, d[key])
            elif isinstance(d[key], list):
                d[key] = self.upload_files_list(case_folder, d[key])
            elif isinstance(d[key], dict):
                d[key] = self.upload_files(case_folder, d[key])
        return d

    def upload_files_list(self, case_folder: Path, l: list) -> list:
        return [
            self.upload_files(case_folder, d)
            for d in l
        ]

    def upload_file(self, case_folder: Path, file: Path):

        relative_path = f"{file.relative_to(case_folder)}"
        self.fs.put(file, relative_path)
        return relative_path