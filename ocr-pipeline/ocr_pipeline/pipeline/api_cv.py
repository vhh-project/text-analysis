#!/usr/bin/env python
# coding: utf-8

from loguru import logger
import numpy as np
from PIL import Image
import pandas as pd
import itertools
from functools import partial
from tesserocr import PyTessBaseAPI, RIL, iterate_level
from tqdm import tqdm

from ocr_pipeline.pipeline.analysis_computer_vision import (adaptive_binary,
     return_best_binarization_parameters)
from ocr_pipeline.pipeline.analysis_rotation import filter_invalid_files
from ocr_pipeline.pipeline.helpers import (
     image_to_data_stats, determine_human_readable_rotation_from_df,
     calc_line_height, run_cached, get_list_column,
     create_dynamic_bin_size_range,
     resize_image, tesseract_api_extract
)


def x_rotate(rotations, api, img, max_size=3500):
    '''
    rotate img all x rotations (list rotations)
    return df of list results eg. [[90, 14, 43.5],[180, 55, 87.6]]
    '''
    data = []
    for r in rotations:
        img_rotated = img.rotate(r, expand=True)

        # extract
        pairs, lines = tesseract_api_extract(img_rotated, api)

        if not pairs and not lines:
            logger.info("original shape, invalid text - trying resized image")
            current_shape = max(*img_rotated.size)
            if current_shape >= max_size:
                new_shape = round(max_size / current_shape, 4)
                img_rotated = resize_image(img_rotated, new_shape)
            else:
                img_rotated = resize_image(img_rotated, 0.8)

            pairs, lines = tesseract_api_extract(img_rotated, api)

            if not pairs and not lines:
                logger.info("resize shape, invalid text - no text content")

        # mlc, length
        df_conf = pd.DataFrame(pairs, columns=['text', 'conf'])
        length, txt, mlc = image_to_data_stats(df_conf)
        if mlc is np.nan:
            mlc = np.nan
            length = np.nan
            human_readable_rotation = 0
            line_height_px = 0
        else:
            # line_height, human_readable_rotation
            only_lines = get_list_column(lines, 1)
            if len(only_lines) > 0:
                df_lines = pd.DataFrame(only_lines)
                df_lines = df_lines.rename(columns={'w': 'width', 'h': 'height'})
                human_readable_rotation = determine_human_readable_rotation_from_df(
                    df_lines)
                if human_readable_rotation == 90:
                    df_lines = df_lines.rename(
                        columns={'height': 'width', 'width': 'height'})
                _, line_height_px = calc_line_height(df_lines)
            else:
                human_readable_rotation = 0
                line_height_px = 0
        data.append([r, mlc, length, line_height_px, human_readable_rotation])

    return pd.DataFrame(data,
                        columns=['rotate', 'mlc', 'length', 'line_height_px',
                                 'human_readable_rotation'])


def get_change(a, b):
    '''
    return percentual change of b to a
    '''
    up = np.max([a, b])
    if np.isnan(up) or up == 0:
        return 0
    return round((abs(a - b) / up) * 100.0, 2)


def get_max_mlc(df):
    '''
    return max row of dataframe based on value in col
    '''
    try:
        logger.info(df)
        idx_max = df.mlc.idxmax()
        return df.loc[idx_max]
    except Exception as e:
        return df.loc[0]


def get_rotation_results_api(f, tess_lang='eng', tess_path='', max_size=3500,
                             diff_threshold=20):
    '''
    arg f single PIL Image object
    return to be corrected rotation information
    '''
    with PyTessBaseAPI(oem=1, path=tess_path, lang=tess_lang) as api:
        img = Image.open(f)

        # 2-rotate
        df = x_rotate([0, 180], api, img, max_size=max_size)

        # 4-rotate: if 2-rotate difference too low
        if get_change(df.mlc[0], df.mlc[1]) < diff_threshold:
            df = df.append(x_rotate([90, 270], api, img, max_size=max_size),
                           ignore_index=True)

        # evaluate best rotation
        best_rotation = get_max_mlc(df)
    return f, best_rotation.rotate + best_rotation.human_readable_rotation, best_rotation.mlc, best_rotation.length, best_rotation.line_height_px


def split_list(a, n):
    k, m = divmod(len(a), n)
    res = (a[i * k + min(i, m):(i + 1) * k + min(i + 1, m)] for i in range(n))
    res = [ele for ele in res if ele]
    return res


def pipeline_api_rotation_determination(files, ROTATION_RESULTS_PATH,
                                        ROTATION_RESULTS_INVALID_PATH, N_CPU,
                                        max_size=2500, diff_threshold=20,
                                        tess_lang='eng', tess_path=''):
    '''
    tesseocr api rotation determination
    '''
    col_names = ['file', 'rotate', 'mlc', 'length', 'line_height_px']

    fn = partial(get_rotation_results_api,
                 max_size=max_size,
                 diff_threshold=diff_threshold,
                 tess_lang=tess_lang,
                 tess_path=tess_path)

    results = run_cached(fn, "rotation determination", files, N_CPU,
                         col_names, cache_path=ROTATION_RESULTS_PATH)

    if ROTATION_RESULTS_PATH and ROTATION_RESULTS_INVALID_PATH:
        filter_invalid_files(ROTATION_RESULTS_PATH,
                             ROTATION_RESULTS_INVALID_PATH)

    return results


##########################
# - shape determination
##########################


def get_shape_accuracy_api(f, shapes, tess_lang='eng', tess_config='',
                           tess_oem=1):
    '''
    return results as list rows eg [file, shape, mlc, length, line_height_px]
    '''
    result = []

    with PyTessBaseAPI(oem=tess_oem, path=tess_config, lang=tess_lang) as api:
        orig_img = Image.open(f)
        for shape in tqdm(shapes):
            # resize
            img = resize_image(orig_img, shape)

            # extract
            pairs, lines = tesseract_api_extract(img, api)
            img.close()

            # mlc, length
            df_conf = pd.DataFrame(pairs, columns=['text', 'conf'])
            length, txt, mlc = image_to_data_stats(df_conf)

            if mlc is np.nan:
                mlc = 0
                length = 0
                line_height_px = 0
            else:
                # line_height, human_readable_rotation
                only_lines = get_list_column(lines, 1)
                if len(only_lines) > 0:
                    df_lines = pd.DataFrame(only_lines)
                    df_lines = df_lines.rename(
                        columns={'w': 'width', 'h': 'height'})
                    human_readable_rotation = determine_human_readable_rotation_from_df(
                        df_lines)
                    if human_readable_rotation == 90:
                        df_lines = df_lines.rename(
                            columns={'height': 'width', 'width': 'height'})
                    _, line_height_px = calc_line_height(df_lines)
                else:
                    line_height_px = 0
            result.append([f, shape, mlc, length, line_height_px])
        orig_img.close()
    return result


def pipeline_api_shape_determination(files, RESULTS_PATH, shapes, N_CPU,
                                     tess_lang='eng', tess_config=''):
    '''
    tesseocr api shape determination
    '''
    col_names = ['file', 'shape', 'mlc', 'length', 'line_height_px']

    fn = partial(get_shape_accuracy_api,
                 shapes=shapes,
                 tess_lang=tess_lang,
                 tess_oem=1,
                 tess_config=tess_config)

    return run_cached(fn, "shape determination", files, N_CPU,
                      col_names, cache_path=RESULTS_PATH, flatten=True)


##########################
# - binarization parameter determination
##########################


def get_adaptive_binarization_api(file, line_height, adaptive_cs,
                                  adaptive_methods, size_ranges,
                                  tess_lang='eng', tess_config='',
                                  tess_oem=1):
    '''
    data: list object of image paths, sizes, cs, method eg. [['car.png', 71, 10, 1],['car.png', 91, 10, 0]]
    return results as list rows eg. [file, size, c, method, cv_adaptive_sizes, line_height_px, mlc, length, time]
    '''

    data = []
    with PyTessBaseAPI(oem=tess_oem, path=tess_config,
                       lang=tess_lang) as api:
        bin_size = create_dynamic_bin_size_range(line_height, size_ranges)

        img = Image.open(file)

        for size, c, method in tqdm(
                itertools.product(bin_size, adaptive_cs, adaptive_methods)):
            # binarization
            curr_img = adaptive_binary(img, size, c, method)
            curr_img = Image.fromarray(curr_img)

            # extract
            pairs, lines = tesseract_api_extract(curr_img, api)
            curr_img.close()

            df_lines = pd.DataFrame([line[1] for line in lines])

            try:
                df_lines = df_lines.rename(columns={'w': 'width', 'h': 'height'})
                _, line_height_px = calc_line_height(df_lines)
            except Exception as e:
                line_height_px = np.nan

            # mlc, length
            df_conf = pd.DataFrame(pairs, columns=['text', 'conf'])
            length, txt, mlc = image_to_data_stats(df_conf)

            data.append([file, size, c, method, mlc, length, line_height_px])
        img.close()
    return data


def export_best_binarization_params(df, GS_PATH):
    '''
    return best binarization param row for each file
    '''
    df_groups = df.groupby(['file'])
    df_best_params = pd.DataFrame([
        return_best_binarization_parameters(df_group)[1]
        for _, df_group in df_groups
    ])
    df_best_params = df_best_params[['file', 'length', 'mlc', 'size', 'c', 'method', 'line_height_px']]
    df_best_params.rename(columns={"mlc": "measure"}, inplace=True)

    if GS_PATH:
        df_best_params.to_csv(GS_PATH, index=False)
    return df_best_params


def pipeline_api_binarization_gridsearch(valid_files_data,
                                         cv_dynamic_size_ranges, cv_adaptive_cs,
                                         cv_adaptive_methods, RESULTS_PATH,
                                         N_CPU, tess_lang='eng',
                                         tess_config=''):
    '''
    tesseocr api binarization params determination
    '''

    fn = partial(get_adaptive_binarization_api,
                 tess_lang=tess_lang,
                 tess_config=tess_config,
                 tess_oem=1,
                 adaptive_cs=cv_adaptive_cs,
                 adaptive_methods=cv_adaptive_methods,
                 size_ranges=cv_dynamic_size_ranges,
                 )
    col_names = ['file', 'size', 'c', 'method', 'mlc', 'length',
                 'line_height_px']
    files = list(valid_files_data.file)
    add_params = [list(valid_files_data.line_height_px)]

    return run_cached(fn, "binarization gridsearch", files, N_CPU,
                      col_names, cache_path=RESULTS_PATH,
                      additional_params=add_params, flatten=True)
