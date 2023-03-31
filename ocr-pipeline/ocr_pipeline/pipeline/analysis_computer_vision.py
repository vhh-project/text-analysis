#!/usr/bin/env python
# coding: utf-8

from functools import partial
import json
import os
import time
import subprocess
import cv2
import fitz
from loguru import logger
import numpy as np
import pandas as pd
from PIL import Image
from pytesseract import pytesseract
from scipy import stats
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.rl_config import defaultPageSize
from reportlab.pdfgen import canvas

from ocr_pipeline.pipeline.graph_plot import plot_img
from ocr_pipeline.pipeline.helpers import (
    tesseract_extract_dataframe,
    image_to_data_stats, word_error_rate,
    create_dynamic_bin_size_range,
    transform_to_bitmap, run_cached
)
from ocr_pipeline.pipeline.spelling_correction import (
    get_spelling_correction,
    get_word_segmentation,
    add_spelling_correction_to_dataframe
)
from ocr_pipeline.pipeline.file_preparation import (
    open_pil_image,
    save_pil_image
)


def save_bytes_image(bytes_img, to_path):
    img = Image.fromarray(bytes_img)
    img.save(to_path)


def img_to_grayscale(img_path, dpi=300):
    try:
        img = Image.open(img_path).convert('L')
        img.save(img_path, dpi=(dpi, dpi))
        return [img_path, True]
    except Exception as e:
        logger.warning(
            f"Cannot transform '{img_path}' to grayscale. Error: {e}")
        return [img_path, False]


def grayscale_to_binary(gray_img_path, thresh=127):
    gray_img = cv2.imread(gray_img_path, 0)
    (thresh, binary_img) = cv2.threshold(gray_img, thresh, 255,
                                         cv2.THRESH_BINARY)
    return binary_img


def adaptive_binary(img_src, size, c, adaptiveMethod=0):
    if isinstance(img_src, Image.Image):
        gray_img = np.array(img_src)[:, :, None]
    else:
        gray_img = cv2.imread(img_src, 0)

    return adaptive_binary_gray(gray_img, size, c, adaptiveMethod)


def adaptive_binary_gray(gray_img, size, c, adaptiveMethod=0):
    if adaptiveMethod == 0:
        method = cv2.ADAPTIVE_THRESH_MEAN_C
    elif adaptiveMethod == 1:
        method = cv2.ADAPTIVE_THRESH_GAUSSIAN_C
    else:
        raise Exception("Invalid adaptive method")

    img_binary = cv2.adaptiveThreshold(gray_img, 255, method, cv2.THRESH_BINARY,
                                       size, c)
    return img_binary


def return_best_binarization_parameters(gridsearch_result, plot=False):
    '''
    how do we chose the best option from a set of binarization results with different params?
    # 1. filter low length results by setting a limit
    # low length count often result in high mlc but misses content
    # lower_limit = mean - std
    # 2. chose the best mlc result among all options that are left

    # after GridSearch data has been collected
    # chose best params by - cutoff negative length outliers -- chose best mlc within the std range
    '''
    df = pd.DataFrame(gridsearch_result)

    # page is not extractable with any binarization config
    if (df.mlc.isin([0, np.nan])).all():
        tmp = df.iloc[0]
        tmp.at["size"] = False
        return False, tmp

    mean = np.mean(df['length'])
    std = np.std(df['length']) + 1e-5
    lower_limit = mean - std

    if plot:
        import matplotlib.pyplot as plt
        plt.hist(df[df['length'] > lower_limit].length)
        plt.hist(df[df['length'] < lower_limit].length, color="red")
        plt.show()
    df_filter = df[df['length'] > lower_limit]

    try:
        best_idx = pd.to_numeric(df_filter.mlc).idxmax()
        best_params = df_filter.loc[best_idx]
        return best_idx, best_params
    except Exception as e:
        logger.info(f"no candidates left: {e}")
        tmp = df.iloc[0]
        tmp.at["size"] = False
        return False, tmp


# def grid_search_adaptive_binarization(img_path, cv_adaptive_sizes=[15, 25],
#                                       cv_adaptive_cs=[10],
#                                       cv_adaptive_methods=[0], output=False,
#                                       eval_method='mlc', ground_truth_path=None,
#                                       tess_lang='eng', tess_config=''):
#     '''
#     try each size and C value to find best adaptive binarization params
#     eval_method = [mlc, wer]
#     evaluation measurement = WORD ERROR RATE
#     return dict of results
#     '''
#     eval_methods = ['mlc', 'wer']
#     if eval_method not in eval_methods:
#         raise Exception(
#             f"Invalid eval_method: {eval_method}. Must be one of {eval_methods}")
#     if ground_truth_path is None and eval_method == 'wer':
#         raise Exception(
#             'Please provide a gound truth text if evaluation method == wer')
#     if eval_method == 'wer':
#         ground_truth = open(ground_truth_path, 'r').read()
#     else:
#         ground_truth = None

#     '''gridsearch & evaluation data collection'''
#     log_once = True  # only log the time once to estimate the runtime time
#     gridsearch_result = []
#     for method in cv_adaptive_methods:
#         for c in cv_adaptive_cs:
#             for size in cv_adaptive_sizes:
#                 start_time = time.time()
#                 img_bin_adapt = adaptive_binary(img_path, size, c, method)
#                 df_data = tesseract_extract_dataframe(img_bin_adapt,
#                                                       lang=tess_lang,
#                                                       config=tess_config)

#                 if eval_method == 'mlc':
#                     length, text, measure = image_to_data_stats(df_data,
#                                                                 output=False)
#                 elif eval_method == 'wer':
#                     hypothesis = ' '.join(
#                         df_data[df_data['text'].notnull()].text.to_list())
#                     length, _, _ = image_to_data_stats(df_data, output=False)
#                     measure = word_error_rate(ground_truth, hypothesis)
#                 else:
#                     assert False

#                 gridsearch_result.append({'length': length,
#                                           eval_method: measure,
#                                           'size': size,
#                                           'c': c,
#                                           'method': method})

#                 time_end = round((time.time() - start_time), 2)
#                 if log_once:
#                     cv_iterations = len(cv_adaptive_sizes) * len(
#                         cv_adaptive_cs) * len(cv_adaptive_methods)
#                     time_estimation = cv_iterations * time_end / 60
#                     logger.info(
#                         f"eval_method: {eval_method}, iterations: {cv_iterations}, est. time(min): {time_estimation:.2f}")
#                     log_once = False
#                 if output:
#                     logger.info(
#                         f"Method: {method}, size: {size}, c: {c}, {eval_method}: {measure}, time: {time_end}")

#     '''evaluate and return dict, best_index, best params'''
#     if eval_method == 'mlc':
#         best_idx, best_params = return_best_binarization_parameters(gridsearch_result)
#         if not best_idx:
#             best_idx, best_params = max(enumerate(gridsearch_result),
#                                         key=lambda item: item[1][eval_method])
#     elif eval_method == 'wer':
#         best_idx, best_params = min(enumerate(gridsearch_result),
#                                     key=lambda item: item[1][eval_method])
#     else:
#         assert False

#     return gridsearch_result, best_idx, best_params


# def collect_binarization_gs_data(file_path, line_height_px, cv_adaptive_cs,
#                                  cv_adaptive_methods, cv_dynamic_size_ranges,
#                                  eval_method='mlc', ground_truth_path=None,
#                                  tess_lang='eng', tess_config=''):
#     '''
#     collect & format data from for adaptive binarization
#     file_path - path to file
#     bin parameters
#         line_height_px: determines gridsizes
#         cv_adaptive_cs
#         cv_adaptive_methods
#     return list results
#         all results (optional)
#         best adaptive binarization settings
#     '''
#     try:
#         output = False
#         cv_adaptive_sizes = create_dynamic_bin_size_range(line_height_px,
#                                                           ranges=cv_dynamic_size_ranges)
#         gs_result, best_idx, best_params = grid_search_adaptive_binarization(
#             file_path,
#             cv_adaptive_sizes,
#             cv_adaptive_cs,
#             cv_adaptive_methods,
#             output=output,
#             eval_method=eval_method,
#             ground_truth_path=ground_truth_path,
#             tess_lang=tess_lang, tess_config=tess_config)
#         result_row = [file_path]
#         result_row.extend(list(best_params.values()))
#         result_row.extend([cv_adaptive_sizes, line_height_px])

#     except Exception as e:
#         logger.warning(f"error collecting gs-data: {e}")
#         result_row = [file_path] + [np.nan] * 7
#     return result_row


# def get_best_gs(gs_result_dict):
#     '''
#     param = return-data[0] from grid_search_adaptive_binarization function
#     new metric: length x mlc as best index
#     '''
#     tmp = pd.DataFrame(gs_result_dict)
#     tmp['mlcXlen'] = tmp.mlc * tmp.length
#     max_index = tmp['mlcXlen'].idxmax()
#     best_row = tmp[tmp.index == max_index]
#     return best_row


def extract_text_from_image(file, size, c, method, sym_spell=False,
                            tess_config='',
                            tess_lang='eng', safe_temp=None, add_filename=True,
                            plot=False, rotate=0, use_binarize=True):
    if use_binarize:
        img_binary = adaptive_binary(file, size, c, method)
        img_binary = Image.fromarray(img_binary)
    elif isinstance(file, Image):
        img_binary = file
    else:
        img_binary = cv2.imread(file, 0)
        img_binary = Image.fromarray(img_binary)

    if rotate != 0:
        img_binary = img_binary.rotate(rotate, expand=True)

    if safe_temp is not None:
        save_pil_image(img_binary, safe_temp)

    if plot:
        plot_img(img_binary)

    df_data = tesseract_extract_dataframe(img_binary, lang=tess_lang,
                                          config=tess_config)
    df_data['text'] = df_data['text'].astype(str)

    if sym_spell:
        df_data['text_low'] = df_data['text'].str.lower()
        df_data['symspell_sc'] = df_data.apply(
            lambda row: get_spelling_correction(row.text_low, 4, sym_spell),
            axis=1)
        df_data['symspell_ws'] = df_data[df_data['symspell_sc'].isnull()].apply(
            lambda row: get_word_segmentation(row.text_low, sym_spell), axis=1)
    else:
        df_data['text_low'] = ''
        df_data['symspell_sc'] = ''
        df_data['symspell_ws'] = ''

    if add_filename:
        df_data['file'] = file
    return df_data


def show_human_viewable(file_path):
    '''
    return corrected PIL img and rotation angle
    '''
    im = Image.open(file_path)
    width, height = im.size
    if width > height:
        logger.debug("flipped 90° right")
        im = im.rotate(90, expand=1)
        rotate = 90
    else:
        logger.debug("straight 0°")
        rotate = 0
    return im, rotate


# # Multiprocessing Computer Vision Task
#  1. grayscaling
#  3. binarization gridsearch
#  4. export
#  6. hocr extract
#  8. pdf extract 9. txt


def convert_orignal_files_bmp(valid_files_list_original, dpi):
    '''
    convert list of paths to bmp
    '''
    for f in valid_files_list_original:
        file_out = os.path.splitext(f)[0] + '.' + 'bmp'
        transform_to_bitmap(f, file_out, dpi)


def grayscale_valid_files(files, N_CPU, GRAYSCALE_RESULTS_PATH, dpi):
    '''1. grayscaling'''

    col_names = ['file', 'gray_status']
    fn = partial(img_to_grayscale, dpi=dpi)

    return run_cached(fn, "grayscaling", files, N_CPU,
                      col_names, cache_path=GRAYSCALE_RESULTS_PATH)


def pipeline_filter_quality(SHAPE_ROTATION_RESULTS_PATH, MLC_THRESHOLD):
    ''' 3.0 filter before gridsearch '''
    # read correction results
    df = pd.read_csv(SHAPE_ROTATION_RESULTS_PATH, header=0)

    # filter low mlc's files
    df_below = df[df.mlc < MLC_THRESHOLD]

    # valid files
    df_valid_files = df.drop(df_below.index)
    filtered_valid_files_list = list(df_valid_files.file)
    logger.info(f'filter valid files: {df_valid_files.shape[0]}'
                f'filter below threshold: {df_below.shape[0]} (irrelevant)')

    return filtered_valid_files_list


def extract_pdf_content(file_path):
    '''
    open and read pdf
    return list of pages of string content
    '''
    import PyPDF2
    content = []

    try:
        pdf_file = open(file_path, 'rb')
        read_pdf = PyPDF2.PdfFileReader(pdf_file)
        pages = read_pdf.getNumPages()

        for i in range(pages):
            page = read_pdf.getPage(i)
            page_content = page.extractText()
            content.append(page_content)

        return file_path, content

    except Exception as e:
        logger.error(f"Unable to read pdf {file_path} due to {e}")
        return file_path, [False]


def tesseract_extract_cli(img_path, outfile_basename, outputbase='tsv pdf',
                          lang='eng', config=''):
    # cmd build and run
    if config:
        cmd = f'tesseract {config} {img_path} {outfile_basename} -l {lang} {outputbase}'
    else:
        cmd = f'tesseract --oem 1 {img_path} {outfile_basename} -l {lang} {outputbase}'
    out = subprocess.run(cmd.split(), capture_output=True)

    # error investigation
    break_indicators = ['failed', 'error']
    p_output = out.stderr.decode().lower()
    errors = any(ele in p_output for ele in break_indicators)
    if errors:
        logger.info(p_output)
        return False
    return True


def filter_phantom_boxes(df, document_height, z_threshold=6):
    '''
    level == 5: only select text boxes
    document height threshold
    '''
    df_filtered = df[(df.level == 5) &
                     (df.height > 0) &
                     (df.height < document_height * 0.8) &
                     (df.width > 0) &
                     (df.top > 0) &
                     (df.left > 0) &
                     (df.text.notnull()) &
                     (df.text.str.strip() != "")]
    return df_filtered


def replace_pdf_background(pdf_path, img, out_path):
    try:
        temporary_image = f"{os.path.splitext(out_path)[0]}_tmp_.jpg"

        if isinstance(img, Image.Image):
            img.convert('RGB').save(temporary_image)
        if isinstance(img, str):
            Image.open(img).convert('RGB').save(temporary_image)

        document = fitz.open(pdf_path)
        img_rect = fitz.Rect(2, 2, 1, 1)
        document[0].insertImage(img_rect, filename=temporary_image)
        os.remove(temporary_image)
        document.save(out_path)
        document.close()
    except Exception as e:
        logger.info(f"background {e}")


def single_hocr_extract(file, bin_size, bin_c, bin_method,
                        width_resized, height_resized, original=None,
                        straight_angle=0, HOCR_DIR=None,
                        tess_lang='eng', tess_config=''):
    '''
    file: path to img
    temp save with unique filenames - multiproc may overwrite otherwise
    '''
    if not HOCR_DIR:
        HOCR_DIR = ""

    FILE = os.path.splitext(original.lstrip(".").split("/")[-1])[0]
    outfile_basename = f"{HOCR_DIR}{FILE}_tmp"
    to_img_path_bin = f"{outfile_basename}_bin.png"

    # resize
    logger.info(f"resize parameters: width {width_resized}, height {height_resized}")
    img = open_pil_image(original).convert('L').resize((width_resized, height_resized))

    # rotate
    if straight_angle != 0:
        img = img.rotate(straight_angle, expand=True)

    # binarize
    if bin_size:
        logger.info(f"binarization parameters: {bin_size}, {bin_c}, {bin_method}")
        img_bin = adaptive_binary(img, bin_size, bin_c, bin_method)
        img = Image.fromarray(img_bin)
    # save
    save_pil_image(img, to_img_path_bin)

    # extract from bin
    try:
        ocr_data = tesseract_extract_dataframe(img,
                                               lang=tess_lang,
                                               config=tess_config)
    except Exception as e:
        logger.info(f"no extraction possible: {e}, {to_img_path_bin}")
        return file, None, straight_angle, None

    # filter dataframe
    try:
        ocr_data = filter_phantom_boxes(ocr_data, height_resized)
    except Exception as e:
        logger.info("error tsv parse:", e)

    if tess_lang == "Fraktur":
        ocr_data.text = ocr_data[ocr_data.text.notnull()].text.apply(lambda row: row.replace('ſ', 's'))

    # remove temporary files
    try:
        os.remove(to_img_path_bin)
    except Exception as e:
        logger.info(f"error: remove temporary files, {e}")

    # return hocr-data
    return file, None, straight_angle, ocr_data.to_dict()


def pipeline_hocr_extract(data, HOCR_DIR, HOCR_RESULTS_PATH, N_CPU,
                          tess_lang='eng', tess_config=''):
    '''
    5. showcaser data extract
    df_gs - input dataframe from gridsearch
    '''
    logger.debug(list(data.columns))
    col_names = ['file', 'name', 'human_readable_rotation', 'entries']
    fn = partial(single_hocr_extract,
                 HOCR_DIR=HOCR_DIR,
                 tess_lang=tess_lang,
                 tess_config=tess_config)

    files = list(data.file)
    add_params = [
        list(data["size"]),
        list(data.c),
        list(data.method),
        list(data.width_resized),
        list(data.height_resized),
        list(data.file_original)
    ]

    data = run_cached(fn, "ocr_extract", files, N_CPU,
                      col_names, cache_path=HOCR_RESULTS_PATH,
                      additional_params=add_params)
    if HOCR_DIR is not None:
        filename_path = HOCR_DIR + 'filenames_index.csv'
        files = [
            f.split('/')[-1]
            for f in data.name
        ]
        pd.DataFrame({'filename': files}).to_csv(filename_path, index=False)
    return data


def pipeline_hocr_add_spellcorrection(data, 
                                      sym_spell, 
                                      repeated_words_list=[], 
                                      dict_enchant="en_US"):
    '''add spell correction to each ocr entry page'''
    def convert_single(row):
        if row.entries is None:
            return {}
        try:
            entries = pd.DataFrame.from_dict(row.entries)
            entries = add_spelling_correction_to_dataframe(entries, sym_spell,
                                                           repeated_words_list,
                                                           dict_enchant)
            return entries.to_dict()
        except Exception as e:
            logger.info(e)
            return {}

    data["entries"] = data[["entries"]].apply(convert_single, axis=1)
    return data


def dataframe_to_structured_data(df_ocr, out_file_path_json, out_file_path_txt,
                                 correction_included=True):
    '''
    7. JSON - TXT
    export pandas dataframe returned by tess
        to json
        to txt
    df_ocr: tess dataframe output
    out_file_path_json: destination json
    out_file_path_txt: destination txt
    correction_included: additional column with corrections to be exported
    '''
    relevant_columns = ['text']
    out_columns = ['ocrText']
    df_ocr["text"] = df_ocr["text"].astype(str)
    logger.debug(list(df_ocr.columns))

    if correction_included:
        relevant_columns.append("text_corrected")
        df_ocr["corrections"] = df_ocr["corrections"].astype(str)
        df_ocr['text_corrected'] = df_ocr['corrections'].fillna(df_ocr['text'])
        df_ocr = df_ocr[df_ocr['text_corrected'] != '[UNK]']
        out_columns.append("ocrTextWithCorrections")
    df_ocr = df_ocr[relevant_columns]
    df_ocr.columns = out_columns
    data = ({'ocrText': ' '.join(df_ocr['ocrText'])})

    df_ocr = df_ocr[df_ocr['ocrText'].notnull()]

    if correction_included:
        data["ocrTextWithCorrections"] = ' '.join(
            df_ocr['ocrTextWithCorrections'])

        # TXT corrected
        content = ' '.join(df_ocr['ocrTextWithCorrections'].tolist())
        with open(os.path.splitext(out_file_path_txt)[0] + "_corrected.txt",
                  "w") as text_file:
            text_file.write(content)

    # JSON
    with open(out_file_path_json, 'w') as fp:
        json.dump(data, fp)

    # TXT
    content = ' '.join(df_ocr['ocrText'].tolist())
    with open(out_file_path_txt, "w") as text_file:
        text_file.write(content)


def pipeline_export_standard_formats(data, JSON_DIR, TXT_DIR,
                                     correction_included=True):
    '''
    7. JSON - TXT
    '''
    for name, df in zip(data.entries_file, data.entries):
        out_file_path_json = JSON_DIR + os.path.splitext(name.split('/')[-1])[
            0] + '.json'
        out_file_path_txt = TXT_DIR + os.path.splitext(name.split('/')[-1])[
            0] + '.txt'
        dataframe_to_structured_data(pd.DataFrame.from_dict(df),
                                     out_file_path_json, out_file_path_txt,
                                     correction_included)


def image_to_pdf(img_row, PDF_DIR, rotate=0, tess_lang='eng', tess_config=''):
    '''
    8. extract single document to .pdf facsimile
    img_row - path to image and array of binarization parameters
    binarize and export to annotated pdf
    '''
    img_path = img_row[len(img_row) - 1]  # og img path, img_row[0] = re-shaped

    try:
        img_binary = adaptive_binary(img_path, img_row[3],
                                     img_row[4], img_row[5])
        img_binary = Image.fromarray(img_binary)
        img_binary = img_binary.rotate(rotate, expand=True)
        pdf = pytesseract.image_to_pdf_or_hocr(img_binary, lang=tess_lang,
                                               config=tess_config,
                                               extension='pdf')

        # export binarized annotated image as pdf
        FILE = os.path.splitext(img_path.split('/')[-1])[0]
        outfile_path = f"{PDF_DIR}{FILE}_bin.pdf"
        with open(outfile_path, 'w+b') as f:
            f.write(pdf)

        # replace background with original image and export to pdf
        tmp_img_filename = f"{PDF_DIR}tmp_original_img_{FILE}.jpg"
        img_path_original = img_path.replace('_WORK', '_work_original')
        original_image = Image.open(img_path_original).rotate(rotate,
                                                              expand=True)
        original_image.save(tmp_img_filename)

        # load binarized annotated image as pdf
        img_rect = fitz.Rect(2, 2, 1, 1)
        document = fitz.open(outfile_path)
        # replace background
        outfile_path_faksimile = f"{PDF_DIR}{FILE.replace('_og', '')}.pdf"
        page = document[0]
        page.insertImage(img_rect, filename=tmp_img_filename)
        document.save(outfile_path_faksimile)
        document.close()

        try:
            os.remove(outfile_path)
            os.remove(tmp_img_filename)
        except Exception as e:
            logger.warning(f"conversion img to pdf: {e}")
            return [img_path, False]

        return [img_path, True]
    except Exception as e:
        logger.warning(f"conversion img to pdf: {e}")
        return [img_path, False]


def merge_multiple_pdf(files_to_merge: list, out_file: str):
    try:
        from PyPDF2 import PdfFileMerger, PdfFileReader
        merger = PdfFileMerger()

        for filename in files_to_merge:
            merger.append(PdfFileReader(open(filename, 'rb')))

        merger.write(out_file)
        return True

    except Exception as e:
        logger.info(e)
        return False


def merge_multiple_pdf_fitz(files_to_merge: list, out_file):
    '''
    in memory merging pdf documents
    '''
    from fitz.__main__ import main as fitz_command
    import sys

    cmd = f"join {' '.join(files_to_merge)} -output {out_file}".split()
    saved_parms = sys.argv[1:]
    sys.argv[1:] = cmd
    fitz_command()
    sys.argv[1:] = saved_parms  # restore original parameters


def create_single_pdf(data, out_path,title=None):
    # create output file
    pdf = canvas.Canvas(str(out_path))
    if title == None:
        title = os.path.splitext(os.path.split(str(out_path))[1])[0]
    pdf.setTitle(title)
    pdf.setAuthor("BOW - Batch OCR Webservice")
    pdf.setSubject("Created by BOW - Batch OCR Webservice")

    font_name = 'FreeSans'  # 'Times-Roman'
    padding = 20

    for i, row in data.iterrows():
        logger.info(f"Creating pdf page {i} width: {row.width_resized}, height: {row.height_resized}")

        # insert document background
        pdf.setPageSize((row.width_resized, row.height_resized))
        pdf.drawImage(row.file_original, 0, 0, width=row.width_resized, height=row.height_resized)

        entries = pd.DataFrame.from_dict(row.entries)

        # font settings
        try:
            meadian_fontsize = entries.height.median()
        except Exception as e:
            logger.info(f"using default fontsize due to: {e}")
            meadian_fontsize = 10

        # insert text data
        for j, entry_row in entries.iterrows():
            if entry_row.height > meadian_fontsize + padding or entry_row.height < meadian_fontsize - padding:
                font_size = meadian_fontsize + padding
            else:
                font_size = entry_row.height

            font_width = pdf.stringWidth(entry_row.text, font_name, font_size)
            text = pdf.beginText()
            text.setTextRenderMode(3)
            text.setFont(font_name, font_size)
            text.setTextOrigin(entry_row.left, row.height_resized - entry_row.top - entry_row.height)
            box_width = (entry_row.width)
            text.setHorizScale(100.0 * box_width / font_width)
            text.textLine(entry_row.text)
            pdf.drawText(text)
        pdf.showPage()

    pdf.save()
