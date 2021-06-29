#!/usr/bin/env python
# coding: utf-8

from functools import partial
from ast import literal_eval
from loguru import logger
import pandas as pd

from ocr_pipeline.pipeline.helpers import run_cached


def return_first_list_element(x):
    '''
    string to list and return first element
    if last element is a list then return all elements of last element (word segmented)
    if not a list return the same input value x
    '''
    try:
        words = literal_eval(x)
        try:
            if isinstance(words[-1], list):
                return '-'.join(words[-1])
        except Exception:
            return words[0]
        return words[0]
    except Exception:
        return x

# -


def apply_time_tags(df, text_join, results):
    '''
    map time tags from list to pd dataframe positions
    '''
    if not results:
        return df
    else:
        for r in results:
            search = text_join[r['start']:r['end']].split(" ")
            found = r['text']

            # search for starting index in df
            start_idx = df[df['text_clean'] == search[0]].index

            # if one found
            if len(start_idx) == 1:
                for i in range(len(search)):
                    df.loc[start_idx + i, 'time'] = str(r['value'])

            # if more than one found 
            elif len(start_idx) > 1:
                for j in range(len(start_idx)):
                    idx = start_idx[j]
                    text_length = len(search) - 1
                    text_selection = list(df.loc[idx : idx+text_length].text_clean.values)

                    if text_selection == search:
                        df.loc[idx:idx+text_length, 'time'] = str(r['value'])
                        break

            # if none found
            else:
                logger.warning(f"index {found} not found")
        return df

# -


def apply_time_entity_detection(df, sutime):
    if not sutime:
        raise Exception("sutime not initialized")

    # merge corrections into text_clean by taking first element of corrections or word segmentation
    df['corrections'] = df['corrections'].apply(lambda x: return_first_list_element(x))
    df['text_clean'] = df['corrections'].fillna(df['text_clean'])

    text = ' '.join(df.text_clean)

    # time entity detection
    results = sutime.parse(text, reference_date='XXXX-XX-XX')

    logger.info(f'time entities found: {len(results)}')

    # write entities to csv
    df['time'] = ''
    df = apply_time_tags(df, text, results)
    return df.to_dict(),



def pipeline_add_time_detection(data, sutime, n_cpu):
    ''' 
    5.2 add time detection (for any language) 
    apply to each file in csv_files
    '''

    fn = partial(apply_time_entity_detection, sutime=sutime)

    new_entries = list(run_cached(
        fn,
        "time entity detection",
        [
            pd.DataFrame.from_dict(entries)
            for entries in data.entries
        ],
        n_cpu,
        ["entries"],
        cache_path=None
    ).entries)
    data.entries = new_entries
    return data