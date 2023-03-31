#!/usr/bin/env python
# coding: utf-8

from everett.component import RequiredConfigMixin, ConfigOptions
from everett.manager import ConfigManager


class PipelineConfig(RequiredConfigMixin):
    required_config = ConfigOptions()
    required_config.add_option(
        'DEV',
        parser=bool,
        default='False',
        doc=''
    )

    # CPU - batch size
    required_config.add_option(
        'N_CPU',
        parser=int,
        default="1",
        doc=''
    )
    required_config.add_option(
        'batch_size',
        parser=int,
        default='0',
        doc=''
    )

    # tesseract
    # plain paths to tesseract traindata
    required_config.add_option(
        'path_tess_data_fast',
        parser=str,
        doc='plain path to fast data',
        default='/home/work/tessdata_fast'
    )
    required_config.add_option(
        'path_tess_data_best',
        parser=str,
        doc='plain path to best data',
        default='/home/work/tessdata_best'
    )
    required_config.add_option(
        'path_tess_data_standard',
        parser=str,
        doc='plain path to default/standard data',
        default='/usr/local/share/tessdata'
    )

    # config & language
    required_config.add_option(
        'tess_config',
        parser=str,
        default=r"--oem 1 -c tessedit_char_blacklist='™©®œ}{<>Œ…~¥[]\\@ı_|æ»¢€«Æ>»«' ",
        doc=''
    )
    required_config.add_option(
        'tess_lang',
        parser=str,
        default='eng',
        doc=''
    )

    # 0.0 evaluation
    required_config.add_option(
        'measure_method',
        parser=str,
        default='mlc',  # wer
        doc=''
    )

    # 0.1 result director
    required_config.add_option(
        'RESULT_DIR',
        parser=str,
        default='../DATA_RESULTS/',
        doc=''
    )
    required_config.add_option(
        'DATA_DIR',
        parser=str,
        default='../DATA_INPUT/',
        doc=''
    )
    required_config.add_option(
        'og_directory',
        parser=str,
        default='',
        doc=''
    )
    required_config.add_option(
        'work_directory',
        parser=str,
        default='_WORK/',
        doc=''
    )
    required_config.add_option(
        'work_directory_original',
        parser=str,
        default='_work_original/',
        doc=''
    )

    # 0 raw scaling
    required_config.add_option(
        'RAW_SCALINGS_DIR',
        parser=str,
        default='RAW_SCALINGS/',
        doc=''
    )
    required_config.add_option(
        'SCALE_FILE_RAW',
        parser=str,
        default='0_scalings.csv',
        doc='store success of scaling transformation'
    )

    # 0 filetype
    required_config.add_option(
        'to_file_format',
        parser=str,
        default='png',
        doc='either png or jpg for base file format across the pipeline'
    )
    required_config.add_option(
        'dpi',
        parser=int,
        default='300',
        doc='dots per inch conversion value'
    )
    required_config.add_option(
        'TRANSFORM_FILE_PNG',
        parser=str,
        default='0_transform_png.csv',
        doc='store success of transformation'
    )
    required_config.add_option(
        'TRANSFORM_FILE_RAW',
        parser=str,
        default='0_transform_raw.csv',
        doc='store success of transformation'
    )
    required_config.add_option(
        'TRANSFORM_FILE_PDF',
        parser=str,
        default='0_transform_pdf.csv',
        doc='store success of transformation'
    )

    # 1 gray
    required_config.add_option(
        'GRAYSCALE_RESULTS_PATH',
        parser=str,
        default='1_grayscale.csv',
        doc='store success of grayscale'
    )

    # 2 Rotate 
    required_config.add_option(
        'ROTATION_RESULTS_PATH',
        parser=str,
        default='2_1_2_rotate_results.csv',
        doc='stores best rotation, benchmark mlc and human readable rotation for each image'
    )
    required_config.add_option(
        'ROTATION_RESULTS_PATH_ALL',
        parser=str,
        default='2_1_0_rotate_results.csv',
        doc='stores all rotations, benchmark mlc and human readable rotation for each image'
    )
    required_config.add_option(
        'ROTATION_RESULTS_INVALID_PATH',
        parser=str,
        default='2_1_1_rotate_results_invalid.csv',
        doc='stores invalid files that yielded a NaN result'
    )
    required_config.add_option(
        'APPLY_ROTATION_RESULTS_PATH',
        parser=str,
        default='2_2_rotate_apply_correction.csv',
        doc='avoid applying rotation twice if file exists'
    )

    # 2.1 Resize
    required_config.add_option(
        'RESIZE_SHAPES_PATH',
        parser=str,
        default='2_3_resize_all_shapes.csv',
        doc='stores all shape settings [m=6] plus mlc for each image (n rows * m shapes)'
    )
    required_config.add_option(
        'RESIZE_BEST_SHAPES_PATH',
        parser=str,
        default='2_4_resize_best_shapes.csv',
        doc='store best shape'
    )
    required_config.add_option(
        'APPLY_RESIZE_RESULTS_PATH',
        parser=str,
        default='2_5_resize_apply_shapes.csv',
        doc='avoid applying resize twice if file exists'
    )

    # 3 Binarization
    required_config.add_option(
        'GS_WER_RESULTS_PATH',
        parser=str,
        default='3_gs_results_wer.csv',
        doc=''
    )
    required_config.add_option(
        'GS_MLC_RESULTS_PATH',
        parser=str,
        default='3_gs_results_mlc.csv',
        doc='store best binarization results'
    )
    required_config.add_option(
        'GS_MLC_RESULTS_PATH_ALL',
        parser=str,
        default='3_gs_results_mlc_all.csv',
        doc='for API option to store all binarization results'
    )
    required_config.add_option(
        'GS_PATH',
        parser=str,
        doc=''
    )

    # 4 Export
    required_config.add_option(
        'EXPORT_RESULTS_PATH',
        parser=str,
        default='4_text_export.csv',
        doc=''
    )

    # 5 spelling
    required_config.add_option(
        'SPELLING_CORRECTION_PATH',
        parser=str,
        default='5_text_spelling_correction.csv',
        doc=''
    )

    # 6 hocr
    required_config.add_option(
        'HOCR_DIR',
        parser=str,
        default='HOCR/',
        doc=''
    )
    required_config.add_option(
        'HOCR_RESULTS_PATH',
        parser=str,
        default='6_hocr_export.csv',
        doc=''
    )

    # 7 json
    required_config.add_option(
        'JSON_DIR',
        parser=str,
        default='JSON/',
        doc=''
    )

    # 8
    required_config.add_option(
        'PDF_DIR',
        parser=str,
        default='PDF/',
        doc=''
    )
    required_config.add_option(
        'EXPORT_PDF_EXPORT_PATH',
        parser=str,
        default='8_pdf_export.csv',
        doc=''
    )

    # 9
    required_config.add_option(
        'TXT_DIR',
        parser=str,
        default='TXT/',
        doc=''
    )

    def __init__(self, config):
        self.config = config.with_options(self)

        self.DEV = self.config('DEV')

        # CPU
        self.N_CPU = self.config('N_CPU')
        self.batch_size = self.config('batch_size')

        # TESSERACT
        # tess paths
        self.path_tess_data_fast = self.config('path_tess_data_fast')
        self.path_tess_data_best = self.config('path_tess_data_best')
        self.path_tess_data_standard = self.config('path_tess_data_standard')
        # tess configs
        self.tess_config_fast = self.config(
            'tess_config') + " --tessdata-dir " + self.config(
            'path_tess_data_fast')
        self.tess_config_best = self.config(
            'tess_config') + " --tessdata-dir " + self.config(
            'path_tess_data_best')
        self.tess_config_standard = self.config(
            'tess_config') + " --tessdata-dir " + self.config(
            'path_tess_data_standard')
        # tess language
        self.tess_lang = self.config('tess_lang')

        # 0 directories RESULT
        self.RESULT_DIR = self.config('RESULT_DIR')

        # 0 directories DATA
        self.DATA_DIR = self.config('DATA_DIR')
        if self.DATA_DIR:
            self.og_directory = self.DATA_DIR
            self.work_directory = self.og_directory + self.config('work_directory') if self.config('work_directory') else None
            self.work_directory_original = self.og_directory + self.config('work_directory_original') if self.config('work_directory_original') else None
        else:
            self.og_directory = None
            self.work_directory = None
            self.work_directory_original = None

        # 0.1 evaluation
        self.measure_method = self.config('measure_method')

        # 0 file format
        self.to_file_format = self.config('to_file_format')
        self.dpi = self.config('dpi')

        if not self.RESULT_DIR:
            self.RESULT_DIR = None
            self.RAW_SCALINGS_DIR = None
            self.SCALE_FILE_RAW = None
            self.TRANSFORM_FILE_PNG = None
            self.TRANSFORM_FILE_RAW = None
            self.TRANSFORM_FILE_PDF = None
            self.GRAYSCALE_RESULTS_PATH = None
            self.ROTATION_RESULTS_PATH_ALL = None
            self.ROTATION_RESULTS_PATH = None
            self.ROTATION_RESULTS_INVALID_PATH = None
            self.APPLY_ROTATION_RESULTS_PATH = None
            self.RESIZE_SHAPES_PATH = None
            self.RESIZE_BEST_SHAPES_PATH = None
            self.APPLY_RESIZE_RESULTS_PATH = None
            self.GS_WER_RESULTS_PATH = None
            self.GS_MLC_RESULTS_PATH = None
            self.GS_MLC_RESULTS_PATH_ALL = None
            self.EXPORT_RESULTS_PATH = None
            self.SPELLING_CORRECTION_PATH = None
            self.HOCR_DIR = None
            self.HOCR_RESULTS_PATH = None
            self.JSON_DIR = None
            self.PDF_DIR = None
            self.EXPORT_PDF_EXPORT_PATH = None
            self.TXT_DIR = None
        else:
            # 0 raw scaling
            self.RAW_SCALINGS_DIR = self.config('RESULT_DIR') + self.config(
                'RAW_SCALINGS_DIR')
            self.SCALE_FILE_RAW = self.config('RESULT_DIR') + self.config(
                'SCALE_FILE_RAW')

            # 0 filetype
            self.TRANSFORM_FILE_PNG = self.config('RESULT_DIR') + self.config(
                'TRANSFORM_FILE_PNG')
            self.TRANSFORM_FILE_RAW = self.config('RESULT_DIR') + self.config(
                'TRANSFORM_FILE_RAW')
            self.TRANSFORM_FILE_PDF = self.config('RESULT_DIR') + self.config(
                'TRANSFORM_FILE_PDF')

            # 1 grayscale
            self.GRAYSCALE_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'GRAYSCALE_RESULTS_PATH')

            # 2.0 Rotate
            self.ROTATION_RESULTS_PATH_ALL = self.config(
                'RESULT_DIR') + self.config('ROTATION_RESULTS_PATH_ALL')
            self.ROTATION_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'ROTATION_RESULTS_PATH')
            self.ROTATION_RESULTS_INVALID_PATH = self.config(
                'RESULT_DIR') + self.config('ROTATION_RESULTS_INVALID_PATH')
            self.APPLY_ROTATION_RESULTS_PATH = self.config(
                'RESULT_DIR') + self.config('APPLY_ROTATION_RESULTS_PATH')
            # 2.1 Resize
            self.RESIZE_SHAPES_PATH = self.config('RESULT_DIR') + self.config(
                'RESIZE_SHAPES_PATH')
            self.RESIZE_BEST_SHAPES_PATH = self.config('RESULT_DIR') + self.config(
                'RESIZE_BEST_SHAPES_PATH')
            self.APPLY_RESIZE_RESULTS_PATH = self.config(
                'RESULT_DIR') + self.config('APPLY_RESIZE_RESULTS_PATH')

            # 3.0 Binarization
            self.GS_WER_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'GS_WER_RESULTS_PATH')
            self.GS_MLC_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'GS_MLC_RESULTS_PATH')
            self.GS_MLC_RESULTS_PATH_ALL = self.config('RESULT_DIR') + self.config(
                'GS_MLC_RESULTS_PATH_ALL')

            # 4 export csv
            self.EXPORT_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'EXPORT_RESULTS_PATH')

            # 5 export spelling correction
            self.SPELLING_CORRECTION_PATH = self.config('RESULT_DIR') + self.config(
                'SPELLING_CORRECTION_PATH')

            # 6
            self.HOCR_DIR = self.config('RESULT_DIR') + self.config('HOCR_DIR')
            self.HOCR_RESULTS_PATH = self.config('RESULT_DIR') + self.config(
                'HOCR_RESULTS_PATH')

            # 7
            self.JSON_DIR = self.config('RESULT_DIR') + self.config('JSON_DIR')

            # 8
            self.PDF_DIR = self.config('RESULT_DIR') + self.config('PDF_DIR')
            self.EXPORT_PDF_EXPORT_PATH = self.config('RESULT_DIR') + self.config(
                'EXPORT_PDF_EXPORT_PATH')

            # 9
            self.TXT_DIR = self.config('RESULT_DIR') + self.config('TXT_DIR')

        if self.config('measure_method') is 'wer':
            self.GS_PATH = self.GS_WER_RESULTS_PATH
        elif self.config('measure_method') is 'mlc':
            self.GS_PATH = self.GS_MLC_RESULTS_PATH
        else:
            self.measure_method = 'mlc'
            self.GS_PATH = self.GS_MLC_RESULTS_PATH


def init_config(path_to_config):
    config_dict = open(path_to_config, 'r').read()
    config_dict = eval(config_dict)
    config = ConfigManager.from_dict(config_dict)
    config = Config(config)
    return config
