#!/usr/bin/env python
# coding: utf-8

import warnings
import os
import hashlib
from loguru import logger
from pathlib import Path
import shutil
from typing import Sequence, Union
import pandas as pd
import pkg_resources
from pytorch_pretrained_bert import BertForMaskedLM
from symspellpy import SymSpell

#from sutime import SUTime

from ocr_pipeline.pipeline.analysis_computer_vision import \
    grayscale_valid_files, pipeline_hocr_extract, \
    pipeline_hocr_add_spellcorrection, create_single_pdf
from ocr_pipeline.pipeline.analysis_rotation import \
    apply_rotation_correction, export_best_shapes, apply_resize_correction
from ocr_pipeline.pipeline.api_cv import pipeline_api_rotation_determination, \
    pipeline_api_shape_determination, pipeline_api_binarization_gridsearch, \
    export_best_binarization_params
from ocr_pipeline.pipeline.file_preparation import create_data_work_directory,\
    paths_to_df, get_valid_files, pipeline_file_format_convert, \
    pipeline_transform_raw, pipeline_split_pdf, merge_df
from ocr_pipeline.pipeline.helpers import resolve_tesseract_lang
from ocr_pipeline.pipeline.time_entity_recognition import \
    pipeline_add_time_detection

warnings.simplefilter("ignore", UserWarning)

Paths = Sequence[Union[str, Path]]


class Pipeline:
    def __init__(self, config):
        self.config = config

    def setup(self):
        # 00 create results dir
        if self.config.RESULT_DIR:
            Path(self.config.RESULT_DIR).mkdir(parents=True, exist_ok=True)
        # 00 create work copy of original data
        if self.config.work_directory:
            create_data_work_directory(self.config.og_directory,
                                       self.config.work_directory,
                                       overwrite=False)
        # tesseract settings
        #tess_lang, ocr_correction, dict_symspell, dict_enchant = resolve_tesseract_lang(self.config.tess_lang)

        import nltk
        nltk.download('averaged_perceptron_tagger')
        nltk.download('maxent_ne_chunker')
        nltk.download('punkt')
        nltk.download('words')

        self.sym_spell = False
        self.bert_model = False

        # SUTIME_JAR_DIR = '/home/work/ocr/sutime_dependencies/'
        # logger.info("init sutime tagger")
        # jar_files = os.path.join(os.path.dirname(SUTIME_JAR_DIR), 'jars')
        # self.sutime = SUTime(jars=jar_files, mark_time_ranges=True)

        logger.info(f"tessdata_fast: {self.config.path_tess_data_fast}")
        logger.info(f"tessdata_best: {self.config.path_tess_data_best}")
        logger.info(f"config fast: {self.config.tess_config_fast}")
        logger.info(f"config best: {self.config.tess_config_best}")
        logger.info(f"config default: {self.config.tess_config_standard}")
        logger.info(f"N_CPU: {self.config.N_CPU}, batch_size: {self.config.batch_size}")

    def transform_filetypes(self, paths: Paths = None) -> Paths:
        # determine available file types
        if paths:
            df_files = paths_to_df(paths)
        else:
            df_files = get_valid_files(self.config.work_directory,
                                       filter_extensions=None,
                                       filter_trash=True)

        # jpg-png or png-jpg
        df_files = pipeline_file_format_convert(df_files,
                                                self.config.TRANSFORM_FILE_PNG,
                                                1, self.config.to_file_format)
        # transform RAW + scaling
        df_files = pipeline_transform_raw(df_files,
                                          self.config.TRANSFORM_FILE_RAW,
                                          self.config.N_CPU,
                                          self.config.to_file_format)
        # transform PDF
        df_files = pipeline_split_pdf(df_files, self.config.TRANSFORM_FILE_PDF,
                                      self.config.N_CPU,
                                      self.config.to_file_format,
                                      self.config.dpi)

        
        def flatten_capital_extensions(row, to_file_format):
            '''rename files with capitalized extension'''
            path, extension = os.path.splitext(row)
            if extension != to_file_format and str(extension).lower() == to_file_format:
                dest_path = f"{path}{to_file_format}"
                logger.info("correction:", row, dest_path)
                try:
                    os.rename(row, dest_path)
                    return dest_path
                except Exception as e:
                    logger.info(e)
                    pass
                    return row
            return row
        df_files.file = df_files.file.apply(lambda row: flatten_capital_extensions(row, f".{self.config.to_file_format}"))

        if self.config.work_directory and self.config.work_directory_original:
            df_files["file_original"] = df_files.file.str.replace(
                self.config.work_directory, self.config.work_directory_original,
                regex=False)
            # create copy of work data to preserve original data color - to NOT be modified
            create_data_work_directory(self.config.work_directory,
                                       self.config.work_directory_original,
                                       overwrite=False)
        else:
            df_files["file_original"] = df_files.file.str.replace(
                f".{self.config.to_file_format}", f"_og.{self.config.to_file_format}",
                regex=False)

            for _, row in df_files.iterrows():
                try:
                    shutil.copyfile(row.file, row.file_original)
                except shutil.SameFileError:
                    logger.info(row)
                    pass

        return df_files[["file", "extension", "file_original", 'master_copy',
                         'production_master',
                         'access_copy']].sort_values(
            by=["file"])

    def grayscale_images(self, data=None) -> Paths:

        if data is None:
            exts = ['.png', '.tiff', '.jpg']
            data = get_valid_files(
                self.config.work_directory,
                filter_extensions=exts,
                filter_trash=True
            )
        paths = list(data.file)
        df = grayscale_valid_files(
            paths,
            self.config.N_CPU,
            self.config.GRAYSCALE_RESULTS_PATH,
            self.config.dpi
        )
        return merge_df(data, df)

    def correct_rotation(self, data=None, tess_lang=None):

        if data is None:
            data = pd.read_csv(self.config.GRAYSCALE_RESULTS_PATH)
        files = data.file.to_list()

        # determine best rotation and filter invalid files
        rotation_results = pipeline_api_rotation_determination(
            files,
            self.config.ROTATION_RESULTS_PATH,
            self.config.ROTATION_RESULTS_INVALID_PATH,
            N_CPU=self.config.N_CPU,
            max_size=3500,
            diff_threshold=30,
            tess_lang=tess_lang,
            tess_path=self.config.path_tess_data_fast,
        )
        # apply rotation correction on best scaled images
        df = apply_rotation_correction(
            merge_df(data, rotation_results),
            self.config.APPLY_ROTATION_RESULTS_PATH,
            self.config.N_CPU
        )
        logger.debug(list(df.columns))
        return merge_df(data, df)

    def shape_determination(self, data=None, shapes=[0.4, 0.5, 0.8], tess_lang=None):
        # determine all shapes
        if data is None:
            data = pd.read_csv(self.config.APPLY_ROTATION_RESULTS_PATH)
        if tess_lang is None:
            tess_lang, _ = resolve_tesseract_lang(self.config.tess_lang)
        files = data.file.to_list()
        results = pipeline_api_shape_determination(
            files,
            self.config.RESIZE_SHAPES_PATH,
            shapes,
            self.config.N_CPU,
            tess_lang=tess_lang,
            tess_config=self.config.path_tess_data_fast
        )
        # group by file and determine best resize shape
        best_shapes = merge_df(data, export_best_shapes(results,
                                                        self.config.RESIZE_BEST_SHAPES_PATH))
        logger.debug(list(best_shapes.columns))

        # apply resize to work and original data
        return merge_df(data, apply_resize_correction(best_shapes,
                                                      self.config.APPLY_RESIZE_RESULTS_PATH,
                                                      self.config.N_CPU))

    def binarization(self, data=None, cv_dynamic_size_ranges=[0.5, 1, 1.5],
                     cv_adaptive_cs=[15, 25], cv_adaptive_methods=[0, 1],
                     tess_lang=None):
        if data is None:
            data = pd.read_csv(self.config.APPLY_RESIZE_RESULTS_PATH)

        results = pipeline_api_binarization_gridsearch(
            data,
            cv_dynamic_size_ranges,
            cv_adaptive_cs,
            cv_adaptive_methods,
            self.config.GS_MLC_RESULTS_PATH_ALL,
            self.config.N_CPU,
            tess_lang=tess_lang,
            tess_config=self.config.path_tess_data_fast)

        # add no-bin row to evaluate:
        results = results.append(data[['file', 'mlc',
                                       'length', 'line_height_px']],
                                 sort=False, ignore_index=True)
        results[['size', 'c', 'method']] = results[['size', 'c', 'method']].fillna(value=0)

        # export best results
        return merge_df(data, export_best_binarization_params(results,
                                                              self.config.GS_PATH))

    def init_correction_lib_bert(self):
        if self.bert_model:
            return True
        logger.info('init BERT model')
        bert_model = BertForMaskedLM.from_pretrained('bert-base-uncased')
        self.bert_model = bert_model
        return self.bert_model

    def init_correction_lib_symspell(self, dict_symspell):
        if self.sym_spell:
            return True
        logger.info('init symspell')
        sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        dictionary_path = f"/app/symspell_dictionaries/{dict_symspell}"
        sym_spell.load_dictionary(dictionary_path, term_index=0, count_index=1)
        self.sym_spell = sym_spell
        return self.sym_spell

    def export_hocr(self, data=None, tess_lang=None, ocr_correction=None, dict_enchant="en_US"):
        if ocr_correction is None or tess_lang is None:
            tess_lang, ocr_correction = resolve_tesseract_lang(self.config.tess_lang)

        if data is None:
            df_a = pd.read_csv(self.config.GS_PATH).fillna(0)
            df_b = pd.read_csv(self.config.ROTATION_RESULTS_PATH).fillna(0)
            data = merge_df(df_a, df_b)

        if self.config.HOCR_DIR:
            Path(self.config.HOCR_DIR).mkdir(parents=True, exist_ok=True)

        df = merge_df(data, pipeline_hocr_extract(
            data,
            self.config.HOCR_DIR,
            self.config.HOCR_RESULTS_PATH,
            self.config.N_CPU,
            tess_lang,
            self.config.tess_config_best))

        if ocr_correction:
            logger.info('hOCR spelling correction workflow')
            df = pipeline_hocr_add_spellcorrection(df,
                                                   sym_spell=self.sym_spell,
                                                   repeated_words_list=[],
                                                   bert_model=self.bert_model,
                                                   dict_enchant=dict_enchant)
            if self.config.HOCR_RESULTS_PATH is not None:
                df.to_csv(self.config.HOCR_RESULTS_PATH, index=False)
        return df

    def time_recognition(self, data):
        if data is None:
            data = pd.read_csv(self.config.HOCR_RESULTS_PATH)
        data = pipeline_add_time_detection(data, self.sutime, self.config.N_CPU)
        return data

    def export_single_pdf(self, data, out_path=None):
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        pdfmetrics.registerFont(TTFont('FreeSans', '/home/work/ocr/FreeSans.ttf', 'UTF-8'))

        if out_path is None:
            out_path = self.config.HOCR_DIR + "/out.pdf"

        create_single_pdf(data, out_path)
        return out_path

    def convert_page(self, row, correction_included):
        entries = pd.DataFrame.from_dict(row.entries)
        converted_entries = [
            {
                "top": entry.top,
                "conf": entry.conf,
                "left": entry.left,
                "text": entry.text,
                "width": entry.width,
                "height": entry.height,
                "time": None,  # entry.time,
                "correction": entry.corrections if correction_included and entry.corrections != '[UNK]' else ""
            }
            for _, entry in entries.iterrows()
        ]

        entities = []
        start = 0
        for entry in converted_entries:
            end = start + len(entry["text"])
            if entry["time"]:
                entities.append({
                    "start": start,
                    "end": end,
                    "score": 1.0,
                    "type": "time",
                    "value": entry["time"],
                })

            start = end + 1

        text = " ".join(entry["text"] for entry in converted_entries)

        return {
            "ner": {
                "entries": converted_entries,
                "intents": [],
                "text": text,
                "entities": entities
            },
            "ocr": {
                "text": text,
                "entries": converted_entries,
                "languages": []
            },
            "preprocessing": {
                "minio": Path(row.file_original),
                'master_copy': row.master_copy,
                'production_master': row.production_master,
                'access_copy': row.access_copy,
                "orig": Path(row.file),
                "width": row.width_resized,
                "height": row.height_resized,
                "original_width": row.width_original,
                "original_height": row.height_original,
                "rotation": row.was_rotated,
                "human_readable_rotation": row.human_readable_rotation,
            }
        }

    def convert_processing_output(self, data, pdf_file, ocr_correction):
        return {
            "output": pdf_file,
            "pages": [
                self.convert_page(row, ocr_correction)
                for _, row in data.iterrows()
            ]
        }

    def process_single(self, file: Path, lang: str = None):
        if lang is None:
            lang = self.config.tess_lang

        tess_lang, ocr_correction, dict_symspell, dict_enchant = resolve_tesseract_lang(lang)
        logger.info(f"Language Config: {lang} {tess_lang}, {ocr_correction}, {dict_symspell}, {dict_enchant}")

        if file.suffix.upper() not in ['.PNG', '.JPG', '.PDF', '.ARW', '.DNG', '.JPEG']:
            raise Exception(f"The file type {file.suffix} is not supported")

        logger.info(self.config.to_file_format)
        if str(file.suffix.upper()) == '.JPEG':
            base, _ = os.path.splitext(str(file))
            os.rename(str(file), f"{base}.jpg")
            file = Path(f"{base}.jpg")

        data = self.transform_filetypes([file])
        data = self.grayscale_images(data)
        data = self.correct_rotation(data, tess_lang=tess_lang)
        data = self.shape_determination(data,
                                        shapes=[0.2, 0.3, 0.4, 0.5, 0.8, 1],
                                        tess_lang=tess_lang)
        data = self.binarization(data,
                                 cv_dynamic_size_ranges=[0.5, 1, 1.5],
                                 cv_adaptive_cs=[15, 25],
                                 cv_adaptive_methods=[0, 1],
                                 tess_lang=tess_lang)
        self.sym_spell = False
        self.init_correction_lib_symspell(dict_symspell)
        data = self.export_hocr(data, tess_lang, ocr_correction, dict_enchant)
        # data = self.time_recognition(data)
        pdf_file = file.parent / f"{file.stem}_result.pdf"
        self.export_single_pdf(data, pdf_file)

        return self.convert_processing_output(data, pdf_file, ocr_correction)

    def hash_output(self):
        BLOCK_SIZE = 65536
        file_hash = hashlib.sha256()
        results_path = Path(self.config.RESULT_DIR)

        for path in sorted(results_path.glob("*.csv")):
            with path.open("rb") as f:
                fb = f.read(BLOCK_SIZE)
                while len(fb) > 0:
                    file_hash.update(fb)
                    fb = f.read(BLOCK_SIZE)
        with (results_path / "output_hash.txt").open("w", encoding="utf8") as f:
            f.write(file_hash.hexdigest())
