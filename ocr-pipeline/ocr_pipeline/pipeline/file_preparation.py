#!/usr/bin/env python
# coding: utf-8

from functools import partial
import shutil
import os

import imageio
import numpy as np
import pandas as pd
from PIL import Image
from loguru import logger
from pathlib import Path
import rawpy
from tqdm import tqdm
import fitz
from pdf2image import convert_from_path, pdfinfo_from_path


def open_pil_image(img_path):
    return Image.open(img_path)


def save_pil_image(pil_img, to_path):
    pil_img.save(to_path)
    #logger.info(os.path.getsize(to_path))


def save_bytes_image(bytes_img, to_path):
    img = Image.fromarray(bytes_img)
    img.save(to_path)


def delete_image(img_path):
    os.remove(img_path)


def get_filename(path, with_extension=False):
    if with_extension:
        return os.path.basename(path)
    else:
        return os.path.splitext(os.path.basename(path))[0]


def create_data_work_directory(og, work, overwrite=False):
    '''
    create working data directory
    to preserve the og data
    '''
    if overwrite and os.path.exists(work):
        shutil.rmtree(work)
    if not os.path.exists(work):
        shutil.copytree(og, work)


def paths_to_df(paths, filter_extensions=None):
    df = pd.DataFrame(
        [(str(path), path.suffix.lower(), None, None, None) for path in paths],
        columns=['file',
                 'extension',
                 'master_copy',
                 'production_master',
                 'access_copy'])
    logger.info(f"all unique extensions: {df.extension.unique()}")

    # filter extensions
    if filter_extensions:
        df = df[df.extension.isin(filter_extensions)]
    logger.info(f"valid unique extensions: {df.extension.unique()}")

    logger.info(f"shape: {df.shape}")
    return df


def get_valid_files(DIR, filter_extensions=None, filter_trash=False):
    '''
    faster version
    return valid files of dir
    filter - file extensions
    filter - trash folder
    '''
    # get directory file-structure
    file_list_data = []
    for root, dir_name, files in os.walk(DIR):
        files = [f for f in files if not f[0] == '.']
        dir_name[:] = [d for d in dir_name if not d[0] == '.']

        for f in files:
            filename, file_extension = os.path.splitext(f)
            file_list_data.append([os.path.join(root, f), file_extension])

    df = pd.DataFrame(file_list_data, columns=['file', 'extension'])
    logger.info(f"all unique extensions: {df.extension.unique()}")

    # filter out Trash files
    if filter_trash:
        df = df[~df.file.str.contains('Trash')]

    # filter extensions
    if filter_extensions:
        df = df[df.extension.isin(filter_extensions)]
    logger.info(f"valid unique extensions: {df.extension.unique()}")

    logger.info(f"shape: {df.shape}")
    return df


def valid_files_df_to_dict(df_files):
    '''
    return dict without names of a get_valid_files() pandas df
    key = file, value = extension column
    '''
    keys = df_files.file.values
    values = df_files.extension.values
    files_d = dict(zip(keys, values))
    return files_d


def list_files_in_dir(path, extensions=None):
    '''
    return list of all files of a directory recursivels and with a file-extension
    specify None to get all files non filtered (with any extension)
    '''
    file_dict = {}
    for obj in os.listdir(path):
        if os.path.isfile(os.path.join(path, obj)):
            if extensions is None:
                file_dict[os.path.join(path, obj)] = os.path.splitext(obj)[1][
                                                     1:]
            elif os.path.splitext(obj)[1][1:] in extensions:
                file_dict[os.path.join(path, obj)] = os.path.splitext(obj)[1][
                                                     1:]
        elif os.path.isdir(os.path.join(path, obj)):
            sub_file_dict = list_files_in_dir(str(os.path.join(path, obj)),
                                              extensions)
            file_dict.update(sub_file_dict)
    return file_dict


def convert_file_format(transform_fn, df_files, selector, file_type_name,
                        to_format, n_cpu, out_file=None, ignore_errors=False,
                        pages=False):
    df_filter = df_files[selector]
    df_files = df_files[~selector]

    files = list(df_filter.file)
    if len(files) > 0:
        logger.info(f"{len(files)} {file_type_name} files were found "
                    f"& to be converted to .{to_format}")
        if n_cpu > len(files):
            n_cpu = len(files)

        fn = partial(transform_fn, to_format=to_format)

        logger.info(f"transforming {file_type_name} files: {len(files)}, ")
                    #f"cpus: {n_cpu}")
        #with get_context("spawn").Pool(processes=n_cpu) as pool:
        #    res = pool.map_async(fn, files)
        #    results = res.get()
        #pool.close()
        #pool.terminate()
        results = [fn(f) for f in files]
        logger.debug(results)
        logger.debug(files)
        # save results
        if not pages:
            file_transform_res = list(zip(files, *zip(*results)))
        else:
            file_transform_res = [
                [file, *row]
                for file, rows in zip(files, results)
                for row in rows
            ]
        df_transform_results = pd.DataFrame(file_transform_res,
                                            columns=['file', 'success',
                                                     'out_file',
                                                     'master_copy',
                                                     'production_master',
                                                     'access_copy'])

        if out_file:
            df_transform_results[[
                'file',
                'success',
                'master_copy',
                'production_master',
                'access_copy'
            ]].to_csv(out_file, index=False)

        # select only successfully transformed and remove original file
        df_success = df_transform_results[df_transform_results.success]
        to_remove = df_success.file.to_list()

        df_files = df_files.append(
            pd.DataFrame([
                (row.out_file, os.path.splitext(row.out_file)[1], row.master_copy,
                 row.production_master, row.access_copy)
                for _, row in df_success.iterrows()
            ], columns=[
                'file',
                'extension',
                'master_copy',
                'production_master',
                'access_copy'
            ]
            ), ignore_index=True)

        failed_transformations = df_transform_results[
            ~df_transform_results.success].file.to_list()
        for f in to_remove:
            if os.path.exists(f):
                os.remove(f)

        for f in failed_transformations[:]:
            if os.path.exists(f):
                os.remove(f)
        if failed_transformations and not ignore_errors:
            raise Exception(f"Error converting files "
                            f"{failed_transformations} to {to_format}")
    return df_files


def split_pdf_into_images(path, to_format="png", dpi=300):
    '''
    given any pdf file (multi or single page) to be split
    into single images (png or pdf if to_pdf=True)
    saves into the same directory
    '''
    if os.path.splitext(os.path.basename(path))[1][1:] == 'pdf':
        f_path = os.path.split(path)[0]
        f_name = os.path.splitext(os.path.basename(path))[0]
        result_pages = []

        info = pdfinfo_from_path(path)
        max_pages = info['Pages']
        logger.info(f"pdf pages to be split: {max_pages}")

        step = 10
        for page in range(0, max_pages + 1, step):
            files = convert_from_path(path,
                                      dpi=dpi,
                                      first_page=page,
                                      last_page=min(page + step - 1, max_pages),
                                      thread_count=step - 1,
                                      output_folder=f_path,
                                      fmt=to_format,
                                      output_file=f"{f_name}_",
                                      paths_only=True)

            for index, file in enumerate(files):
                parts = file.rsplit("_", 1)
                output_filename = f"{parts[0]}-{parts[1].split('-')[1]}"
                os.rename(file, output_filename)
                result_pages.append((True, output_filename, None, None, None))

        return result_pages
    else:
        raise Exception(f"file {path} is not a .pdf")


def raw_transform(img_path, to_format='png'):
    '''
    > export ARW, DNG file as to_format
    *can adapt code to export other raw extensions
    '''
    f_name = get_filename(img_path)
    f_path, extension = os.path.split(img_path)
    extension = extension[-4:]
    output_filename = f"{f_path}/{f_name}.{to_format}"
    try:
        with rawpy.imread(img_path) as raw:
            # load as 8 bit
            img_converted_8bit = raw.postprocess(half_size=True,
                                                 output_color=rawpy.ColorSpace(0),
                                                 no_auto_bright=False,
                                                 use_camera_wb=True,
                                                 use_auto_wb=False,
                                                 user_wb=None,
                                                 output_bps=8,
                                                 bright=1.0,
                                                 dcb_enhance=False,
                                                 four_color_rgb=False
                                                 )
            # load as 16 bit
            img_converted_16bit = raw.postprocess(half_size=False,
                                                  output_color=rawpy.ColorSpace(0),
                                                  no_auto_bright=False,
                                                  use_camera_wb=True,
                                                  use_auto_wb=False,
                                                  user_wb=None,
                                                  output_bps=16,
                                                  bright=1.0,
                                                  dcb_enhance=False,
                                                  four_color_rgb=False
                                                  )

        imageio.imsave(output_filename, img_converted_8bit, compress_level=9)

    except Exception as e:
        logger.warning(
            f"Could not convert file {img_path} to {to_format} due to {e}")
        return False, output_filename, None, None, None

    scaling_extensions = ['.arw']  # raw-scaling for selected raw types
    if extension.lower() not in scaling_extensions:
        logger.info(f"skipping raw scaling for extension {extension}")
        return True, output_filename, None, None, None

    # raw-scaleing
    scale_success, scale_jpg, scale_tiff, scale_tiff = create_raw_scaling(
        img_path,
        img_converted_8bit,
        img_converted_16bit,
        None)
    return scale_success, output_filename, scale_jpg, scale_tiff, scale_tiff


def pipeline_split_pdf(df_files, TRANSFORM_FILE_PDF, N_CPU,
                       to_format='png', dpi=300):
    '''
    df_files - get_valid_files pd dataframe only_pdf_files
    TRANSFORM_FILE_PDF - export
    '''
    # filter pdf files

    return convert_file_format(partial(split_pdf_into_images, dpi=dpi),
                               df_files, df_files.extension == '.pdf',
                               ".pdf", to_format, N_CPU,
                               out_file=TRANSFORM_FILE_PDF,
                               ignore_errors=True,
                               pages=True)


def pipeline_transform_raw(df_files, TRANSFORM_FILE_RAW, N_CPU,
                           to_format='png'):
    '''
    df_files - get_valid_files pd dataframe
    TRANSFORM_FILE_RAW - export success
    '''
    raw_extensions = ['.arw', '.dng']

    return convert_file_format(raw_transform, df_files,
                               df_files.extension.isin(raw_extensions),
                               ".RAW",
                               to_format, N_CPU, out_file=TRANSFORM_FILE_RAW,
                               ignore_errors=True)


def file_format_convert(img_path, to_format, dpi=300):
    f_name = os.path.splitext(os.path.basename(img_path))[0]
    f_path = os.path.split(img_path)[0]
    output_filename = f"{f_path}/{f_name}.{to_format}"

    try:
        img = Image.open(img_path)

        if os.path.splitext(os.path.basename(img_path))[1].lower() in ['.tif', '.tiff']:
            new_size = (int(img.size[0] * 0.5), int(img.size[1] * 0.5))
            img = img.resize(new_size)

        img.save(output_filename, dpi=(dpi, dpi))
        return True, output_filename, None, None, None
    except Exception as e:
        logger.warning(
            f"Could not convert file {img_path} to {to_format} due to {e}")
        return False, output_filename, None, None, None


def pipeline_file_format_convert(df_files, TRANSFORM_FILE_PNG, N_CPU,
                                 to_format):
    '''
    convert_formats to png conversion
    '''
    convert_formats = ['.tiff', '.tif', '.jpg']
    if to_format not in ["png"]:
        raise Exception(
            f"Invalid format '{to_format}' needs to be 'png'")

    return convert_file_format(file_format_convert,
                               df_files,
                               df_files.extension.isin(convert_formats),
                               convert_formats,
                               to_format, N_CPU, out_file=TRANSFORM_FILE_PNG,
                               ignore_errors=True)


def merge_df(left, right):
    columns = left.columns.difference(right.columns).tolist()
    columns.append("file")
    return left[columns].merge(right, on="file", how="inner")


def create_raw_scaling(file_path, img_converted_8bit,
                       img_converted_16bit, RAW_SCALINGS_DIR=None):
    '''
    raw file scaling
    arg img_converted_8bit - cached raw file
    arg img_converted_16bit - cached raw file
    given raw file from arg file_path
        .TIFF 2x
        .JPG 1x
    to directory arg RAW_SCALINGS_DIR
    '''
    try:
        filename_wo_extension = os.path.splitext(
            str(os.path.split(file_path)[-1]))[0]
        if RAW_SCALINGS_DIR is None:
            RAW_SCALINGS_DIR = f"{os.path.split(file_path)[0]}/"

        to_format = 'tiff'
        master_copy = f"{RAW_SCALINGS_DIR}{filename_wo_extension}_MC.{to_format}"
        production_master = f"{RAW_SCALINGS_DIR}{filename_wo_extension}_PM.{to_format}"
        imageio.imsave(master_copy, img_converted_16bit)
        imageio.imsave(production_master, img_converted_16bit)

        to_format = 'jpg'
        access_copy = f"{RAW_SCALINGS_DIR}{filename_wo_extension}_AC.{to_format}"
        imageio.imsave(access_copy, img_converted_8bit)

        return True, Path(master_copy), Path(production_master), Path(
            access_copy)
    except Exception as e:
        logger.warning(f"Could not convert file {file_path} due to {e}")
        return False, None, None, None
