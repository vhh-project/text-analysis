#!/usr/bin/env python
# coding: utf-8

from functools import partial
from loguru import logger
from scipy import stats
import numpy as np
import pytesseract
from PIL import Image
import os
import pandas as pd

from ocr_pipeline.pipeline.file_preparation import save_pil_image
from ocr_pipeline.pipeline.helpers import tesseract_extract_dataframe, \
    image_to_data_stats, determine_human_readable_rotation_from_df, \
    calc_line_height, run_cached


def correct_img_rotation(file, rotation):
    '''
    rotate file and safe replace to original path
    '''
    logger.info(f"Rotate file {file} by {rotation}°")
    rotated_img = rotate_image(file, rotation)
    save_pil_image(rotated_img, file)
    return [file, rotation, True]


def rotate_image(img_path, angle, expand=True):
    '''
    return rotated PIL image
    '''
    from PIL import Image
    img = Image.open(img_path).rotate(angle, expand=expand)
    return img


def get_osd_info(img_path):
    '''
    parse tesseract osd output string to a dict
    for easier variable reading.
    Info:
        int Page_number
        int Orientation_in_degrees
        int rotate
        float  Orientation_confidence
        string Script
        float  Script_confidence
    '''
    img = Image.open(img_path)
    osd_info = pytesseract.image_to_osd(img)
    info = {}
    try:
        for i in osd_info.split('\n'):
            index = str(i.split(':')[0].replace(' ', '_'))
            value = i.split(':')[1].strip()
            try:
                if '.' in value:
                    info[index] = float(value)
                else:
                    info[index] = int(value)
            except Exception as e:
                logger.info(e)
                info[index] = value
        return info
    except Exception as e:
        logger.warning(f"{e}")
        return osd_info


def build_data_get_osd_info(img_path):
    try:
        info = get_osd_info(img_path)
        info['file'] = img_path
        info['correction'] = 0
        next_res = info.values()
        return list(next_res)
    except Exception as e:
        next_res = list(np.full([8 - 2], np.nan))
        next_res.append(img_path)
        next_res.append(0)
        logger.debug(f"try rescale img - narrow down shape ratio: {img_path} {e}")
        return list(next_res)


def similarity(a, b):
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()


def calc_box_similarities(box_data, sim_threshold=0.8, reference_words=['declassified', 'authority']):
    '''
    return
    Fale if similarity is low - rotation is wrong
    True if rotation correct because reference words been detected within the defined threshold
    '''
    reference_words = reference_words
    top_references = {}
    box_data_low = [x.lower().strip() for x in box_data]

    for ref in reference_words:
        top_sim = 0
        top_word = ''
        for word in box_data_low:
            if word.strip():
                if similarity(ref, word) > top_sim:
                    top_sim = similarity(ref, word)
                    top_word = word
        top_references[top_word] = top_sim

    for f in list(top_references.items())[:]:
        if (f[1]) > sim_threshold:
            return True, top_references

    return False, top_references


def word_error_rate(ground_truth, hypothesis):
    from jiwer import wer
    error = wer(ground_truth, hypothesis)
    return error


def get_shape_accuracy(file_path, shapes=[], tess_lang='eng', tess_config=''):
    orig_img = Image.open(file_path)

    def _process(shape, image):
        img = image.copy()
        new_size = (int(img.size[0] * shape), int(img.size[1] * shape))
        img = img.resize(new_size)
        df_data = tesseract_extract_dataframe(img, tess_lang, tess_config)
        img.close()
        length, _, mlc = image_to_data_stats(df_data)
        _, line_height_px = calc_line_height(df_data)
        return [file_path, shape, mlc, length, line_height_px]

    results = list(map(partial(_process, image=orig_img), shapes))
    df = pd.DataFrame(results,
                      columns=['file', 'shape', 'mlc',
                               'length', 'line_height_px'])
    return return_best_shape(df)


def return_best_shape(df, thresh_len=1.5, thresh_line_height=18):
    """
    1. remove mlc outliers from distribution - negative std as lower boundary
    2. remove length outliers from distribution (zscore)
    3. filter low line height / font size
    4. select & return lowest shape/time from remaining
    """
    df["shape"] = df["shape"].astype(float)
    df["length"] = df["length"].astype(float)
    benchmark_idx = df['shape'].idxmax()
    benchmark_row = df.loc[benchmark_idx]
    
    try:
        mlc_mean = np.mean(df.mlc)  # 1.
        mlc_std = np.std(df.mlc)
        mlc_lower_limit = mlc_mean - mlc_std
        df = df[(df.mlc > mlc_lower_limit)]
        if df.empty:
            return benchmark_row

        len_zscore = np.abs(stats.zscore(df.length))  # 2.
        df = df[len_zscore < thresh_len]
        if df.empty:
            return benchmark_row

        df = df[df.line_height_px >= thresh_line_height]  # 3.
        if df.empty:
            return benchmark_row

        min_time_idx = df['shape'].idxmin()  # 4.
        best_row = df.loc[min_time_idx]

        logger.info(f"best-shape: {best_row}")
        return best_row
    except Exception as e:
        logger.info(f"default-shape: {best_row}")
        return benchmark_row


def export_best_shapes(df_res, BEST_SHAPES_PATH):
    """
    > 2.4
    SHAPES_PATH - source
    BEST_SHAPES_PATH - export results
    return best resize within group
    """
    best_shapes = pd.DataFrame([
        return_best_shape(df_group, 1.2)
        for group_name, df_group in df_res.groupby(['file'])
    ])
    if BEST_SHAPES_PATH:
        best_shapes.to_csv(BEST_SHAPES_PATH, index=False)
    return best_shapes


def apply_rotation_correction(df_corrections, APPLY_ROTATION_RESULTS_PATH,
                              N_CPU):
    '''
    > 2.2
    ROTATION_RESULTS_PATH - source
    APPLY_ROTATION_RESULTS_PATH - export
    apply rotation to files in _work and _original dir
    '''
    fn = correct_img_rotation
    files = list(df_corrections.file)
    original_files = list(df_corrections.file_original)
    add_params = [list(df_corrections.rotate)]
    # get new files
    col_names = ['file', 'was_rotated', 'outcome']

    results = run_cached(fn, "rotation correction", files, N_CPU,
                         col_names, cache_path=APPLY_ROTATION_RESULTS_PATH,
                         additional_params=add_params)

    results_original = run_cached(fn, "rotation org correction", original_files,
                                  N_CPU, col_names, cache_path=None,
                                  additional_params=add_params)

    return results


def filter_invalid_files(ROTATION_RESULTS_PATH, ROTATION_RESULTS_INVALID_PATH):
    if not os.path.exists(ROTATION_RESULTS_INVALID_PATH):
        # filter 0 mlc - to not be excluded from the subsequent pipeline
        df = pd.read_csv(ROTATION_RESULTS_PATH)
        df = df.fillna(0)
        df_invalid = df[df.mlc == 0]
        df_invalid.to_csv(ROTATION_RESULTS_INVALID_PATH, index=False)

        df_valid = df[df.mlc != 0]
        df_valid.to_csv(ROTATION_RESULTS_PATH, index=False)
    else:
        logger.info("Filter invalid files is already applied")


def correct_img_resize(file_path, resize_p, mlc, line_height_px, length):
    '''
    resize_p - percentage of img size
    save resized img next to original loc
    '''

    img = Image.open(file_path)
    width_original, height_original = img.size
    new_size = (int(img.size[0] * resize_p), int(img.size[1] * resize_p))
    img = img.resize(new_size)
    width_resized, height_resized = img.size
    img.save(file_path)
    return [file_path, width_original, height_original, width_resized, height_resized, True, mlc, line_height_px, length]


def apply_resize_correction(df_corrections, APPLY_RESIZE_RESULTS_PATH, N_CPU):

    fn = correct_img_resize
    files = list(df_corrections.file)
    original_files = list(df_corrections.file_original)
    add_params = [df_corrections['shape'].to_list(), df_corrections.mlc, df_corrections.line_height_px, df_corrections['length']]
    # get new files
    col_names = ['file', 'width_original', 'height_original', 'width_resized', 'height_resized', 'success', 'mlc', 'line_height_px', 'length']

    results = run_cached(fn, "shape correction", files, N_CPU,
                         col_names, cache_path=APPLY_RESIZE_RESULTS_PATH,
                         additional_params=add_params)

    results_original = run_cached(fn, "shape org correction", original_files,
                                  N_CPU, col_names, cache_path=None,
                                  additional_params=add_params)
    return results
