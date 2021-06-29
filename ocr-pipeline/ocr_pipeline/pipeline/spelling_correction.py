#!/usr/bin/env python
# coding: utf-8

from loguru import logger
import numpy as np
import pandas as pd
import nltk
import torch
from pytorch_pretrained_bert import BertTokenizer, BertForMaskedLM
import re
from tqdm import tqdm
from enchant.checker import SpellChecker
from difflib import SequenceMatcher
import jellyfish


def get_spelling_correction(word, n_best, sym_spell):
    try:
        if (type(word) == str) and word != '':
            from symspellpy import Verbosity
            # spelling suggestions
            suggestions = sym_spell.lookup(word, Verbosity.CLOSEST, max_edit_distance=2)
            suggestions = suggestions[:n_best]
            all_suggestions = [s.term for s in suggestions]
            if len(all_suggestions) == 0:
                return "[NONE]"
            return all_suggestions
        else:
            return False
    except Exception as e:
        logger.info(e)
        return False


def get_word_segmentation(word, sym_spell):
    try:
        if (type(word) == str) and word != '':
            # word segmentation
            all_segmentation = sym_spell.word_segmentation(word)
            all_segmentation = all_segmentation.corrected_string.split(' ')
            return all_segmentation
        else:
            return False
    except Exception as e:
        logger.info(e)
        return False


def count_vectorize_documents(documents):
    '''
    documents list of words (df[col].tolist())
    return df with 1 whenever word occurs
    '''
    from sklearn.feature_extraction.text import CountVectorizer
    cv = CountVectorizer()
    word_count_vector = cv.fit_transform(documents)
    X_features = word_count_vector.todense()
    df = pd.DataFrame(X_features, columns=cv.get_feature_names())
    return df


def get_personslist(text):
    return list(set([
        chunk.leaves()[0][0]
        for sent in nltk.sent_tokenize(text)
        for chunk in nltk.ne_chunk(nltk.pos_tag(nltk.word_tokenize(sent)))
        if isinstance(chunk, nltk.tree.Tree) and chunk.label() == 'PERSON'
    ]))


def build_repeated_words_list(EXPORT_RESULTS_PATH, occur_threshold=3):
    df_export = pd.read_csv(EXPORT_RESULTS_PATH)

    ''' data preparation '''
    replace_empty = '[UNK]'
    df_export = data_clean_for_spelling_correction(df_export, replace_empty)

    ''' build wordcount dictionary of all n images '''
    documents = df_export['text_clean'].fillna("").to_list()
    df_counts = count_vectorize_documents(documents)
    mask = df_counts.sum(axis=0) >= occur_threshold
    repeated_words_list = mask[mask].index.tolist()
    repeated_words_list = [replace_empty] + repeated_words_list

    logger.info(f"unique words: {len(np.unique(documents))}/{len(documents)}")
    logger.info(f"minimum required word occurrence: {occur_threshold},"
                f"filtered words: {len(repeated_words_list)}/{len(df_counts)}")
    return repeated_words_list


def error_detection(text, repeated_words_list, sym_spell, dict_enchant="en_US"):
    # building list of ignore words
    persons_list = get_personslist(text)
    punctuation = list(r"!,.?!({[]})_-–+*/\%$¥€'")
    ignorewords = persons_list + list(punctuation) + repeated_words_list

    # using enchant.checker.SpellChecker -> detect incorrect words
    d = SpellChecker(dict_enchant)
    words = text.split()

    # check each word
    incorrectwords = [w for w in words if not d.check(w) and w not in ignorewords]

    # using enchant.checker.SpellChecker -> get suggestions
    enchant_suggestedwords = [d.suggest(w) for w in incorrectwords]
    symspell_segmentation = [get_word_segmentation(w, sym_spell) for w in incorrectwords]
    symspell_suggestedwords = [get_spelling_correction(w, 200, sym_spell) for w in incorrectwords]

    # replace incorrect with [MASK] -> only whole word not substring of word
    text = text.split()  # word_tokenize(text)

    for i in incorrectwords:
        for idx, w in enumerate(text):
            if w == i:
                text[idx] = '[MASK]'

    masked_text = ' '.join(text)
    return masked_text, enchant_suggestedwords, symspell_suggestedwords, symspell_segmentation, incorrectwords


def predict_words(text, predictions, maskids, all_suggestions, symspell_segmentation, incorrectwords, tokenizer, similarity_thresh=0.75, n=3):
    for i in range(len(maskids)):
        simmax = 0
        list2 = all_suggestions[i]
        list4 = symspell_segmentation[i]
        predicted_token = []

        if predictions is not None:
            preds = torch.topk(predictions[0, maskids[i]], k=80)
            indices = preds.indices.tolist()
            bert_suggestedwords = tokenizer.convert_ids_to_tokens(indices)

            # compare similarity of top bert words to incorrect_word
            predicted_token = ''
            for bert_word in bert_suggestedwords:
                s = SequenceMatcher(None, bert_word, incorrectwords[i]).ratio()
                if s is not None and s > simmax:
                    simmax = s
                    predicted_token = [bert_word]

        # if bert similarity too low take words from symspell and enchant
        if simmax < similarity_thresh:
            final = list2[:n]
            # segmentations
            if len(list4) > 1:
                final = final + [list4]
            predicted_token = final

        # filter same as incorrect word suggestions
        if len(predicted_token) > 0:
            if incorrectwords[i] == predicted_token[0]:
                text = text.replace('[MASK]', "[MASK_SAME]", 1)
            else:
                text = text.replace('[MASK]', str(predicted_token).replace(' ', ''), 1)
        else:
            text = text.replace('[MASK]', "[MASK_SAME]", 1)
    return text


def apply_correction_workflow(txt, repeated_words_list, tokenizer, sym_spell, bert_model, dict_enchant):
    '''
    detect and mask errors
     symspell and enchant suggestions
     BERT suggestions
    return final decision
    '''
    all_suggestions = []

    # error detection and suggestions
    txt_masked, enchant_suggestedwords, symspell_suggestedwords, symspell_segmentation, incorrectwords = error_detection(txt, repeated_words_list, sym_spell, dict_enchant)

    # suggestion ranking
    for i in range(len(enchant_suggestedwords)):
        enchant_suggestedwords[i] = [txt.lower() for txt in enchant_suggestedwords[i]]
        symspell_segmentation[i] = [txt.lower() for txt in symspell_segmentation[i]]
        symspell_suggestedwords[i] = [txt.lower() for txt in symspell_suggestedwords[i]]

        # merge all suggestions
        suggestions = list(dict.fromkeys(symspell_suggestedwords[i] + enchant_suggestedwords[i]))
        # rank suggestions by distance
        distances = [jellyfish.levenshtein_distance(w, incorrectwords[i]) for w in suggestions]
        # sort with max distance threshold
        distance_threshold = int(len(incorrectwords[i]) / 2)
        suggestions = [x for dist, x in sorted(zip(distances, suggestions)) if (dist < distance_threshold)]
        all_suggestions.append(suggestions)

    # bert suggestions
    tokenized_text = tokenizer.tokenize(txt_masked)
    indexed_tokens = tokenizer.convert_tokens_to_ids(tokenized_text)
    MASKIDS = [i for i, e in enumerate(tokenized_text) if e == '[MASK]']

    if bert_model:
        # prepare Torch inputs
        tokens_tensor = torch.tensor([indexed_tokens])

        # Predict all tokens
        with torch.no_grad():
            predictions = bert_model(tokens_tensor)
    else:
        predictions = None

    # final prediction
    text_corrected = predict_words(txt_masked, predictions, MASKIDS, all_suggestions, symspell_segmentation, incorrectwords, tokenizer)
    return text_corrected


def split_digit_string(s):
    '''add whitespace between digits and charcters in a string'''
    s_fixed = s
    count = 0
    try:
        for idx, c in enumerate(s):
            if c.isdigit():
                if (idx != 0) and (not s[idx - 1].isdigit()) and (s[idx - 1] != " "):
                    s_fixed = s_fixed[:idx + count] + " " + s_fixed[idx + count:]
                    count += 1
                if (idx != len(s) - 1) and (not s[idx + 1].isdigit()) and (s[idx + 1] != " "):
                    s_fixed = s_fixed[:idx + count + 1] + " " + s_fixed[idx + count + 1:]
                    count += 1
        return s_fixed
    except Exception as e:
        logger.info(e)
        return s


def mark_empty_string(s, replace_whitespace='[EMPTY]'):
    if len(s.replace(" ", "")) <= 2:
        return replace_whitespace
    return s


def data_clean_for_spelling_correction(df, replace_empty):
    # punctuation removal
    df['text_clean'] = df['text'].str.replace(r'[^\w\s]', '')
    # nan values
    df['text_clean'] = df['text_clean'].replace(np.nan, "", regex=False)
    # extract digits
    df['digit_content'] = df['text_clean'].apply(lambda text: [s for s in re.findall(r'-?\d+\.?\d*', text)])
    # remove digits
    df['text_clean'] = df['text_clean'].apply(lambda text: re.sub(r'[0-9]', '', text))
    # text lowercase
    df['text_clean'] = df['text_clean'].str.lower()
    # mark empty string
    df['text_clean'] = df['text_clean'].apply(lambda text: mark_empty_string(text, replace_empty))
    return df


def add_spelling_correction_to_dataframe(df_data, sym_spell,
                                         repeated_words_list=[],
                                         bert_model=False,
                                         dict_enchant="en_US"):
    # text preprocessing
    replace_empty = '[UNK]'
    repeated_words_list.append(replace_empty)
    df_data = data_clean_for_spelling_correction(df_data, replace_empty)

    n = 300
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

    # process each dataframe chunk of size n
    for g, df in df_data.groupby(np.arange(len(df_data)) // n):
        txt = ' '.join(df['text_clean'])
        text_corrected = apply_correction_workflow(txt, repeated_words_list, tokenizer, sym_spell, bert_model, dict_enchant)
        df_data.loc[df.index, 'corrections'] = text_corrected.split()

    df_data.loc[df_data['corrections'] == df_data['text_clean'], 'corrections'] = ''
    df_data.loc[df_data['corrections'].str.contains("[MASK_SAME]"), 'corrections'] = ''
    return df_data


# TODO: not in use - RM
def pipeline_spelling_correction(PATH, EXPORT_RESULTS_PATH, bert_model, sym_spell):
    df_export = pd.read_csv(PATH)
    df_export['corrections'] = ''

    ''' data preparation '''
    replace_empty = '[UNK]'
    df_export = data_clean_for_spelling_correction(df_export, replace_empty)

    ''' build wordcount dictionary of all n images '''
    repeated_words_list = build_repeated_words_list(PATH)

    dfs = dict(tuple(df_export.groupby('file')))
    relevant_columns = ['text', 'conf', 'text_clean']
    all_files = list(dfs.keys())
    n = 300
    tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')

    for idx in tqdm(all_files):
        tmp_df = dfs[idx][relevant_columns]

        # process each dataframe chunk of size n
        for g, df in tmp_df.groupby(np.arange(len(tmp_df)) // n):
            txt = ' '.join(df['text_clean'])
            txt = str(txt)
            text_corrected = apply_correction_workflow(txt, repeated_words_list, tokenizer, sym_spell, bert_model)
            df_export.loc[df.index, 'corrections'] = text_corrected.split()

        df_export.loc[df_export['corrections'] == df_export['text_clean'], 'corrections'] = ''

    # safe and return results
    try:
        df_export.drop(['text_low', 'symspell_sc', 'symspell_ws', 'text_clean'], axis=1, inplace=True)
        df_export.to_csv(EXPORT_RESULTS_PATH, index=False)
    except Exception as e:
        logger.error(f"Could not save {EXPORT_RESULTS_PATH} due to {e}, trying again")
        df_export.to_csv(EXPORT_RESULTS_PATH, index=False)
    return df_export
