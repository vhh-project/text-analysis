#!/usr/bin/env python
# coding: utf-8

import subprocess
import os.path
import sys
import shutil
import csv
import os
import itertools
import multiprocessing

import cv2
from loguru import logger
import numpy as np
import pandas as pd
import pytesseract
from multiprocessing import get_context


def resize_image(img, shape):
    new_size = (int(img.size[0] * shape), int(img.size[1] * shape))
    img = img.resize(new_size)
    return img


def tesseract_api_extract(img, api) -> (list, list):
    try:
        api.SetImage(img)  # PIL img
        api.GetUTF8Text()
        api.AllWordConfidences()
        pairs = api.MapWordConfidences()
        lines = api.GetTextlines()
        return pairs, lines
    except Exception as e:
        #logger.info(e)
        return [], []


def tesseract_extract_dataframe(img_binary, lang='eng', config=''):
    return pytesseract.image_to_data(img_binary, lang=lang, config=config,
                                     output_type='data.frame')


def get_new_files_to_be_processed(path, col_names, index_col, all_files):
    '''
    path (str) - to datafile
    col_names (list) - of datafile if not existent
    index_col (str) - unique identifier
    all_files (list) - list of all files
    RETURN files that are not processed yet
    '''

    if os.path.exists(path):
        already_processed_files = pd.read_csv(path, header=0)
        already_processed_files = list(already_processed_files[index_col])
        all_files = all_files
        new_files = list(set(all_files) - set(already_processed_files))
        logger.info('load existing data..')
        logger.info(f"new: {len(new_files)}, total: {len(all_files)}, existing: {len(already_processed_files)}")
    else:
        with open(path, 'w', newline='') as outcsv:
            writer = csv.writer(outcsv)
            writer.writerow(col_names)
        new_files = all_files
        logger.info(f"new: {len(new_files)}, total: {len(all_files)}")
    return new_files


def resolve_tesseract_lang(user_input):
    try:
        user_input = user_input.lower()
        lang_select = {"eng": ["eng", True, "frequency_dictionary_en_82_765.txt", "en_US"],
                       "deu": ["deu", True, "de-100k.txt", "de_DE"],
                       "deu_fraktur": ["deu", True, "de-100k.txt", "de_DE"],
                       "fra": ["fra", True, "fr-100k.txt", "fr_FR"],
                       "rus": ["rus+ukr", True, "ru-100k.txt", "ru_RU"],
                       "ru": ["rus+ukr", True, "ru-100k.txt", "ru_RU"],
                       "fraktur": ["deu", True, "de-100k.txt", "de_DE"]}
        # tess_lang, correction, dict_symspell, dict_enchant
        return lang_select[user_input][0], lang_select[user_input][1], lang_select[user_input][2], lang_select[user_input][3]
    except KeyError:
        return "eng+deu+fra", False, None, None


def get_first_index(row):
    '''
    get first index of list in pandas column
    '''
    from ast import literal_eval
    try:
        return literal_eval(row)[0]
    except Exception as e:
        logger.info(e)
        return ''
    return row


def check_if_file_in_list(file_path, gs_list):
    if os.path.exists(file_path):
        return file_path not in gs_list
    else:
        raise Exception(f"File '{file_path}' does not exist or invalid path")


def job(path, arg_2, arg_3, arg_4):
    logger.debug(f"{arg_2[0]}, {arg_3[0]}, {arg_4}")

    img_bin_adapt = cv2.imread(path, 0)
    if arg_4[0] == 0:
        logger.debug("threshold mode 'y'")
        img_bin_adapt = cv2.adaptiveThreshold(img_bin_adapt,255,cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 15, 15)
        return img_bin_adapt
    elif arg_4[0] == 1:
        logger.debug("threshold mode 'yyy'")
        img_bin_adapt = cv2.adaptiveThreshold(img_bin_adapt,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 15)
        return img_bin_adapt

    return path


def divide_chunks(l, n):
    '''
    split list l into n batches and put the rest in n-1
    '''
    for i in range(0, len(l), n):
        yield l[i:i + n]


def get_list_column(data, col):
    return [item[col] for item in data]


def run_cached(fn, name, files, n_cpu, col_names, additional_params=[],
               cache_path=None, flatten=False):

    if cache_path is not None and os.path.exists(cache_path):
        data = pd.read_csv(cache_path, header=0)
        cached_files = set(data['file'])
        indices = [i for i, f in enumerate(files)  if f not in cached_files]
        files = [files[i] for i in indices]
        additional_params = [[data[i] for i in indices]
                             for data in additional_params]
        logger.info('load existing data..')
    else:
        data = pd.DataFrame(columns=col_names)

    #if len(files) > n_cpu:
    #n_cpu = min(len(files), n_cpu)

    logger.info(f'{name} files: {len(files)}, cpus: {n_cpu}')
    if len(files) > 0:
        #if n_cpu > 1:
        #    pool = multiprocessing.Pool(processes=n_cpu)
        #    mapper = pool.starmap
        #else:
        #    mapper = itertools.starmap
        #    pool = None

        with get_context("spawn").Pool(processes=n_cpu) as pool:
            results = pool.starmap(fn, zip(files, *additional_params))

            logger.debug(f"{name}: {col_names}")
            if flatten:
                results = itertools.chain.from_iterable(results)
            data = data.append(pd.DataFrame(results, columns=col_names),
                               ignore_index=True)

            cv2.destroyAllWindows()

        #if pool:
        #    pool.close()
        #    pool.terminate()

        if cache_path is not None:
            data.to_csv(cache_path, index=False)

    return data


def utilize_multiprocessing(func, zipped_args, OUT_FILE_PATH, N_CPU, concat_results=False, flatten_list=False):
    pool = multiprocessing.Pool(processes=N_CPU)
    results = pool.starmap(func, zipped_args)

    if concat_results:
        results = pd.concat(results).to_records()
    if flatten_list:
        results = [item for sublist in results for item in sublist]

    with open(OUT_FILE_PATH, 'a', newline='') as outcsv:
        writer = csv.writer(outcsv)
        writer.writerows(results)

    cv2.destroyAllWindows()
    pool.close()
    pool.terminate()

# -

def determine_human_readable_rotation_from_df(df_data, ignore_conf=False):
    '''
    from the tess readable rotation (straight or 90 to right) -> best mlc
    determine the human readable rotation (straight) -> by returning 0 or 90 to left
    '''
    if ignore_conf:
        lines = df_data[df_data.conf == -1][1:]
    else:
        lines = df_data
    all_lines = lines.shape[0]
    threshold = 0.75
    threshold_value = int(all_lines * threshold)

    rotation_straight = lines[lines.width >= lines.height].shape[0]
    rotation_right = lines[lines.width <= lines.height].shape[0]

    if rotation_straight > rotation_right and rotation_straight > threshold_value:
        return 0 # img is 0° straight

    elif rotation_right > rotation_straight and rotation_right > threshold_value:
        return 90 # img is 90° right clockwise
    else:
        return 0 # roation of img could not be determined, assuming 0° straight


def calc_mean_line_confidence(df_data):
    '''
    return mean line confidence of lines that are not NaN or empty
    '''
    try:
        if df_data.shape[0] > 1:
            mean_confidence = df_data[(df_data.text.notnull()) & (df_data.text.str.strip() != '')].conf.mean()
            return mean_confidence
        else:
            return np.nan
    except Exception as e:
        logger.warning(f"Could not determine mean line confidence due to {e}.")
        return np.nan


def image_to_data_stats(df_data, output=False):
    '''
    df_data = output from tesseract function image_to_data
    return result stats from image_to_data
    '''
    try:
        length = len(list(df_data[df_data.text.notnull()].text))
        text = list(df_data[df_data.text.notnull()].text)
        mlc = calc_mean_line_confidence(df_data)
        if output:
            logger.info(f"result length: {length}, MLC: {mlc}\n{text}")
        return length, text, mlc
    except Exception:
        return np.nan, np.nan, np.nan


def calc_line_height(df_data, ignore_conf=False, plot=False):
    '''
    data dataframe from tess output
    '''
    if ignore_conf:
        lines = df_data[df_data.conf != -1]
    else:
        lines = df_data
    mean = np.mean(lines.height)
    std = np.std(lines.height)
    lower_limit = mean - std
    upper_limit = mean + std
    line_height_px = lines[(lines['height'] > lower_limit) & (lines['height'] < upper_limit)].height.mean()

    if plot:
        import matplotlib.pyplot as plt
        plt.hist(lines[(lines.height > lower_limit) & (lines['height'] < upper_limit)].height)
        plt.hist(lines[lines['height'] < lower_limit].height, color="red")
        plt.hist(lines[lines['height'] > upper_limit].height, color="red")
        plt.show()
    return lines, line_height_px


def word_error_rate(ground_truth, hypothesis):
    from jiwer import wer
    error = wer(ground_truth, hypothesis)
    return error


def create_dynamic_bin_size_range(line_height_px, ranges=[0.5,1,1.5], default=20):
    '''
    return dynamic list of grid size values for adaprive binarization based on line height (px)
    '''
    try:
        if int(line_height_px) < 10:
            return create_dynamic_bin_size_range(default)

        # ensure odd numbers
        sizes = [int(s*line_height_px) for s in ranges]
        sizes = [s + (1 - s%2) for s in sizes]
        return sizes
    except:
        # on except eg. nan input
        return create_dynamic_bin_size_range(default)


def transform_to_bitmap(file_in, file_out, dpi):
    img = Image.open(file_in)
    img = img.convert("RGB")
    img.save(file_out, dpi=(dpi, dpi))


def compress(input_file_path, output_file_path, power=0):
    """Function to compress PDF via Ghostscript command line interface"""
    quality = {
        0: '/default',
        1: '/prepress',
        2: '/printer',
        3: '/ebook',
        4: '/screen'
    }
    try:
        if not os.path.isfile(input_file_path):
            logger.info(f"Error: invalid path for input PDF file")
            return False

        if input_file_path.split('.')[-1].lower() != 'pdf':
            logger.info(f"Error: input file is not a PDF")
            return False

        gs = get_ghostscript_path()
        initial_size = os.path.getsize(input_file_path)
        subprocess.call([gs, '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
                        '-dPDFSETTINGS={}'.format(quality[power]),
                        '-dNOPAUSE', '-dQUIET', '-dBATCH',
                        '-sOutputFile={}'.format(output_file_path),
                         input_file_path])
        final_size = os.path.getsize(output_file_path)
        ratio = 1 - (final_size / initial_size)
        logger.info("Compression by {0:.0%}.".format(ratio))
        logger.info("Final file size is {0:.1f}MB".format(final_size / 1000000))
        return True

    except Exception as e:
        logger.info(f"Error compress: {e}")
        return False


def get_ghostscript_path():
    gs_names = ['gs', 'gswin32', 'gswin64']
    for name in gs_names:
        if shutil.which(name):
            return shutil.which(name)
    raise FileNotFoundError(f'No GhostScript executable was found on path ({"/".join(gs_names)})')