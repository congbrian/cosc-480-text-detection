# -*- coding: utf-8 -*-
"""480_ensemble

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/151miMRFdMYQ6ULrxGKsWzWy6inSPZdj7
"""

# A dependency of the preprocessing for BERT inputs
# !pip install -U "tensorflow-text==2.13.*"

# !pip install "tf-models-official==2.13.*"

from sklearn.datasets import make_classification
from sklearn.model_selection import train_test_split
import numpy as np
import pandas as pd
import os
import shutil

import tensorflow as tf
import tensorflow_hub as hub
import tensorflow_text as text
from official.nlp import optimization  # to create AdamW optimizer

import matplotlib.pyplot as plt
import requests as rq

from io import BytesIO


tf.get_logger().setLevel('ERROR')

print("Downloading datasets...")

url1 = "https://github.com/Taichi22/CollegeCode/raw/main/CSE480/NIHMS1911044-supplement-1%20(2).xlsx"
data = rq.get(url1).content
df_1 = pd.read_excel(BytesIO(data), header=1)
url2 = "https://github.com/Taichi22/CollegeCode/raw/main/CSE480/NIHMS1911044-supplement-2.csv"
data = rq.get(url2).content
ai_generated = pd.read_csv(BytesIO(data))
df_1.head(5)

url3 = "https://github.com/Taichi22/CollegeCode/blob/aed0d810fb7c6b1a9d360f3840fd6e084e4c7418/CSE480/responses.csv"
data = rq.get(url3).content
data_aug = pd.read_csv(BytesIO(data))

data_aug = pd.concat([data_aug['prompt'], data_aug['value'], data_aug['value'].str.split('\n\n', expand=True)], axis=1).copy()
data_aug.columns = data_aug.columns.map(str)
data_aug['Label'] = 1
data_aug.head(1)

original_papers = pd.concat([df_1['Number'],df_1['File Name'], df_1['Column1'].str.split('\n', expand=True)], axis=1).copy()
original_papers.columns = original_papers.columns.map(str)
original_papers['Label'] = 0
original_papers.head(1)

to_melt = pd.concat([original_papers, data_aug])
to_melt.tail(1)
print("Processing data...")
# Melt the DataFrame to stack all paragraph columns into single column rows
values = [str(i) for i in range(0,17)]
print(values)
melted_df = pd.melt(to_melt, id_vars=['File Name', 'Label'], value_vars=values)
melted_df = melted_df[melted_df['value'].notna()]
# melted_df.sort_values(by=["Unnamed: 0", 'variable'], inplace=True)
# melted_df['Label'] = 0

# Split the paragraph text into words and expand to columns
words_df = melted_df['value'].str.split(' ', expand=True)
melted_df = pd.concat([melted_df, words_df], axis=1)

melted_df.columns = melted_df.columns.map(str)

melted_df = melted_df.reindex(axis='index')

melted_df.tail(5)

ai_generated.head(20)
ai_generated['value'] = pd.Series(ai_generated[[str(i) for i in range(1,300)]].fillna('').values.tolist()).str.join(' ')
ai_generated["Label"] = 1
ai_generated.head(20)

ai_text = ai_generated[["Label", "value"]]
ai_text = tf.data.Dataset.from_tensor_slices(dict(ai_text))
for feature_batch in ai_text.take(1):
  for key, value in feature_batch.items():
    print("  {!r:20s}: {}".format(key, value))

ai_concat_list = [str(i) for i in range(1,301)]
ai_concat_list.append("Label")
ai_concat_list.append("value")
ai_concat_df = ai_generated[ai_concat_list]

human_concat_list = [str(i) for i in range(1,730)]
human_concat_list.append("Label")
human_concat_list.append("value")
melted_concat_df = melted_df[human_concat_list]

melted_concat_df.head(5)

all_text = pd.concat([ai_concat_df, melted_concat_df])
all_text.head(20)

all_text['Label']

import re

# Helper function to count occurrences
def count_occurrences(pattern, row, fixed=False, matchCase=True, verbose = False):
    if matchCase:
      if fixed:
        if verbose:
          print(row.str.count(re.escape(pattern)))
        return row.str.count(re.escape(pattern))
      else:
        if verbose:
          print(row.str.count(pattern))
        return row.str.count(pattern)
    else:
      lcase = pattern.lower()
      lseries = row.str.lower()
      if fixed:
          return lseries.str.count(re.escape(lcase))
      else:
          return lseries.str.count(lcase)

wordindex = [str(i) for i in range(1, 301)]

# V1: Count of "."
V1 = np.asarray([np.sum(count_occurrences(".", row[wordindex], fixed=True)) for index, row in all_text.iterrows()])

# V2: Count of non-NA entries
V2 = all_text.notna().sum(axis=1)

# V3: Presence of ")"
V3 = np.asarray([np.sum(count_occurrences(")", row[wordindex], fixed=True)) > 0 for index, row in all_text.iterrows()]).astype(int)

# V4: Presence of "-"
V4 = np.asarray([np.sum(count_occurrences("-", row[wordindex])) > 0 for index, row in all_text.iterrows()]).astype(int)

# V5: Presence of ";" or ":"
V5 = np.asarray([np.sum(count_occurrences(";", row[wordindex]) + count_occurrences(":", row[wordindex])) > 0 for index, row in all_text.iterrows()]).astype(int)

# V6: Presence of "?"
V6 = np.asarray([np.sum(count_occurrences("\\?", row[wordindex])) > 0 for index, row in all_text.iterrows()]).astype(int)

# V7: Presence of "'"
V7 = np.asarray([np.sum(count_occurrences("'", row[wordindex])) > 0 for index, row in all_text.iterrows()]).astype(int)

sentence_lengths = []
sentence_diffs = []
sentences11 = []
sentences34 = []

# Iterate over each row in the DataFrame
for index, row in all_text.iterrows():
  sentence_length = 0
  rowlengths = []
  rowdiffs = []
  previous_sentence_end = -1
  count11 = 0
  count34 = 0
  # Iterate over each word in the row
  for col, word in enumerate(row[wordindex]):
      if pd.notna(word):  # Check if the word cell is not NaN
          sentence_length += 1
          if '.' in word:
              # Sentence ended, process the sentence length
              rowlengths.append(sentence_length)

              # Calculate the difference in length with the previous sentence
              if previous_sentence_end != -1:
                  sentence_diff = sentence_length - previous_sentence_end
                  rowdiffs.append(sentence_diff)
              previous_sentence_end = sentence_length

              # Check if the sentence length is less than 11 or greater than 34
              if sentence_length < 11:
                  count11 += 1
              elif sentence_length > 34:
                  count34 += 1
              # Reset the sentence length for the next sentence
              sentence_length = 0
  sentences11.append(count11)
  sentences34.append(count34)
  sentence_lengths.append(rowlengths)
  sentence_diffs.append(rowdiffs)

# Calculate V8, V9, V10, V11 based on the lists generated above
V8 = np.array([np.std(x) for x in sentence_lengths])  # Standard deviation in sentence length
V9 = np.array([np.mean(x) for x in sentence_diffs]) # Mean of length differences for consecutive sentences
V10 = sentences11    # Number of sentences with <11 words
V11 = sentences34     # Number of sentences with >34 words

V8[np.isnan(V8)] = 0
V9[np.isnan(V9)] = 0

# V12 to V18: Specific word and pattern counts
words_to_count = ["although", "However", "but", "because", "this"]
V12 = np.asarray([np.sum(count_occurrences("although", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V13 = np.asarray([np.sum(count_occurrences("However", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V14 = np.asarray([np.sum(count_occurrences("but", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V15 = np.asarray([np.sum(count_occurrences("because", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V16 = np.asarray([np.sum(count_occurrences("this", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V17 = np.asarray([np.sum(count_occurrences("others", row[wordindex], matchCase=False)) + np.sum(count_occurrences("researchers", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)
V18 = np.asarray([np.sum(count_occurrences("[0-9]", row[wordindex])) > 0 for index, row in all_text.iterrows()]).astype(int)


# V19: Proportion of capitalized words
capitals = np.asarray([np.sum(count_occurrences("[A-Z]", row[wordindex])) for index, row in all_text.iterrows()]).astype(int)

V19 = np.asarray([np.sum(count_occurrences("[A-Z]", row[wordindex])) for index, row in all_text.iterrows()]).astype(int) >= V1 * 2

# V20: Presence of "et"
V20 = np.asarray([np.sum(count_occurrences("et", row[wordindex], matchCase=False)) > 0 for index, row in all_text.iterrows()]).astype(int)

# Combine all features into a DataFrame
feature_df = pd.DataFrame({
    'V1': V1,
    'V2': V2,
    'V3': V3,
    'V4': V4,
    'V5': V5,
    'V6': V6,
    'V7': V7,
    'V8': V8,
    'V9': V9,
    'V10': V10,
    'V11': V11,
    'V12': V12,
    'V13': V13,
    'V14': V14,
    'V15': V15,
    'V16': V16,
    'V17': V17,
    'V18': V18,
    'V19': V19,
    'V20': V20
})
pd.options.display.max_columns = None
pd.options.display.max_rows = None
feature_df.head(15)
df = pd.concat([feature_df, all_text[['value', 'Label']]], axis=1)
df['V19'] = df['V19'].astype(int)
df.head(15)

train, test = train_test_split(df, stratify = df["Label"], test_size=0.2, random_state=42)
train, val = train_test_split(df, stratify = df["Label"], test_size=0.1, random_state=42)

AUTOTUNE = tf.data.AUTOTUNE
batch_size = 4
seed = 12

generated_vars = ['V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10', 'V19']

train_text_ds = tf.data.Dataset.from_tensor_slices(train[["value"]])
train_meta_ds = tf.data.Dataset.from_tensor_slices(train[generated_vars])
train_labels_ds = tf.data.Dataset.from_tensor_slices(train[['Label']])
combined_train_ds = tf.data.Dataset.zip(((train_text_ds, train_meta_ds), train_labels_ds))

combined_train_ds = combined_train_ds.batch(batch_size).cache().prefetch(buffer_size=AUTOTUNE)

test_text_ds = tf.data.Dataset.from_tensor_slices(test[["value"]])
test_meta_ds = tf.data.Dataset.from_tensor_slices(test[generated_vars])
test_labels_ds = tf.data.Dataset.from_tensor_slices(test[['Label']])
combined_test_ds = tf.data.Dataset.zip(((test_text_ds, test_meta_ds), test_labels_ds))

combined_test_ds = combined_test_ds.batch(batch_size).cache().prefetch(buffer_size=AUTOTUNE)


val_text_ds = tf.data.Dataset.from_tensor_slices(val[["value"]])
val_meta_ds = tf.data.Dataset.from_tensor_slices(val[generated_vars])
val_labels_ds = tf.data.Dataset.from_tensor_slices(val[['Label']])
combined_val_ds = tf.data.Dataset.zip(((val_text_ds, val_meta_ds), val_labels_ds))

combined_val_ds = combined_val_ds.batch(batch_size).cache().prefetch(buffer_size=AUTOTUNE)

# for data, labels in combined_train_ds.take(1):
#     print("Labels:", labels)

#@title Choose a BERT model to fine-tune

print("Loading BERT Model...")

bert_model_name = 'small_bert/bert_en_uncased_L-4_H-512_A-8'  #@param ["bert_en_uncased_L-12_H-768_A-12", "bert_en_cased_L-12_H-768_A-12", "bert_multi_cased_L-12_H-768_A-12", "small_bert/bert_en_uncased_L-2_H-128_A-2", "small_bert/bert_en_uncased_L-2_H-256_A-4", "small_bert/bert_en_uncased_L-2_H-512_A-8", "small_bert/bert_en_uncased_L-2_H-768_A-12", "small_bert/bert_en_uncased_L-4_H-128_A-2", "small_bert/bert_en_uncased_L-4_H-256_A-4", "small_bert/bert_en_uncased_L-4_H-512_A-8", "small_bert/bert_en_uncased_L-4_H-768_A-12", "small_bert/bert_en_uncased_L-6_H-128_A-2", "small_bert/bert_en_uncased_L-6_H-256_A-4", "small_bert/bert_en_uncased_L-6_H-512_A-8", "small_bert/bert_en_uncased_L-6_H-768_A-12", "small_bert/bert_en_uncased_L-8_H-128_A-2", "small_bert/bert_en_uncased_L-8_H-256_A-4", "small_bert/bert_en_uncased_L-8_H-512_A-8", "small_bert/bert_en_uncased_L-8_H-768_A-12", "small_bert/bert_en_uncased_L-10_H-128_A-2", "small_bert/bert_en_uncased_L-10_H-256_A-4", "small_bert/bert_en_uncased_L-10_H-512_A-8", "small_bert/bert_en_uncased_L-10_H-768_A-12", "small_bert/bert_en_uncased_L-12_H-128_A-2", "small_bert/bert_en_uncased_L-12_H-256_A-4", "small_bert/bert_en_uncased_L-12_H-512_A-8", "small_bert/bert_en_uncased_L-12_H-768_A-12", "albert_en_base", "electra_small", "electra_base", "experts_pubmed", "experts_wiki_books", "talking-heads_base"]

map_name_to_handle = {
    'bert_en_uncased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_L-12_H-768_A-12/3',
    'bert_en_cased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_cased_L-12_H-768_A-12/3',
    'bert_multi_cased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_multi_cased_L-12_H-768_A-12/3',
    'small_bert/bert_en_uncased_L-2_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-2_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-2_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-2_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-2_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-2_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-2_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-2_H-768_A-12/1',
    'small_bert/bert_en_uncased_L-4_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-4_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-4_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-4_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-4_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-4_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-4_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-4_H-768_A-12/1',
    'small_bert/bert_en_uncased_L-6_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-6_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-6_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-6_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-6_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-6_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-6_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-6_H-768_A-12/1',
    'small_bert/bert_en_uncased_L-8_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-8_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-8_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-8_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-8_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-8_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-8_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-8_H-768_A-12/1',
    'small_bert/bert_en_uncased_L-10_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-10_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-10_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-10_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-10_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-10_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-10_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-10_H-768_A-12/1',
    'small_bert/bert_en_uncased_L-12_H-128_A-2':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-12_H-128_A-2/1',
    'small_bert/bert_en_uncased_L-12_H-256_A-4':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-12_H-256_A-4/1',
    'small_bert/bert_en_uncased_L-12_H-512_A-8':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-12_H-512_A-8/1',
    'small_bert/bert_en_uncased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/small_bert/bert_en_uncased_L-12_H-768_A-12/1',
    'albert_en_base':
        'https://tfhub.dev/tensorflow/albert_en_base/2',
    'electra_small':
        'https://tfhub.dev/google/electra_small/2',
    'electra_base':
        'https://tfhub.dev/google/electra_base/2',
    'experts_pubmed':
        'https://tfhub.dev/google/experts/bert/pubmed/2',
    'experts_wiki_books':
        'https://tfhub.dev/google/experts/bert/wiki_books/2',
    'talking-heads_base':
        'https://tfhub.dev/tensorflow/talkheads_ggelu_bert_en_base/1',
}

map_model_to_preprocess = {
    'bert_en_uncased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'bert_en_cased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_cased_preprocess/3',
    'small_bert/bert_en_uncased_L-2_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-2_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-2_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-2_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-4_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-4_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-4_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-4_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-6_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-6_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-6_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-6_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-8_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-8_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-8_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-8_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-10_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-10_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-10_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-10_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-12_H-128_A-2':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-12_H-256_A-4':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-12_H-512_A-8':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'small_bert/bert_en_uncased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'bert_multi_cased_L-12_H-768_A-12':
        'https://tfhub.dev/tensorflow/bert_multi_cased_preprocess/3',
    'albert_en_base':
        'https://tfhub.dev/tensorflow/albert_en_preprocess/3',
    'electra_small':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'electra_base':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'experts_pubmed':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'experts_wiki_books':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
    'talking-heads_base':
        'https://tfhub.dev/tensorflow/bert_en_uncased_preprocess/3',
}

tfhub_handle_encoder = map_name_to_handle[bert_model_name]
tfhub_handle_preprocess = map_model_to_preprocess[bert_model_name]

print(f'BERT model selected           : {tfhub_handle_encoder}')
print(f'Preprocess model auto-selected: {tfhub_handle_preprocess}')

import tensorflow as tf
import tensorflow_hub as hub

def build_classifier_model_with_metadata(metadata_shape):
    # Text input (as before)
    text_input = tf.keras.layers.Input(shape=(), dtype=tf.string, name='text')

    # BERT preprocessing and encoder layers (as before)
    preprocessing_layer = hub.KerasLayer(tfhub_handle_preprocess, name='preprocessing')
    encoder = hub.KerasLayer(tfhub_handle_encoder, trainable=True, name='BERT_encoder')
    encoder_inputs = preprocessing_layer(text_input)
    outputs = encoder(encoder_inputs)

    # BERT pooled output
    net = outputs['pooled_output']
    net = tf.keras.layers.Dropout(0.1)(net)
    # net = tf.keras.layers.Flatten()(net)
    # Additional input for metadata
    metadata_input = tf.keras.layers.Input(shape=metadata_shape, name='metadata')

    # Optionally, add a layer to process metadata
    metadata_processed = tf.keras.layers.Dense(16, activation='relu')(metadata_input)
    metadata_processed = tf.keras.layers.Flatten()(metadata_processed)

    # Combine BERT output with metadata
    combined = tf.keras.layers.Concatenate()([net, metadata_processed])
    # Final classifier layer
    net = tf.keras.layers.Dense(1, activation='sigmoid', name='classifier')(combined)
    print("Shape after Dense layer:", net.shape)
    # Create the model
    return tf.keras.Model(inputs=[text_input, metadata_input], outputs=net)

# Example usage

model = build_classifier_model_with_metadata(train[['V2', 'V3', 'V4', 'V5', 'V6', 'V7', 'V8', 'V9', 'V10', 'V19']].shape[1])
model.summary()

epochs = 5
steps_per_epoch = tf.data.experimental.cardinality(combined_train_ds).numpy()
num_train_steps = steps_per_epoch * epochs
num_warmup_steps = int(0.1*num_train_steps)

init_lr = 3e-5
optimizer = optimization.create_optimizer(init_lr=init_lr,
                                          num_train_steps=num_train_steps,
                                          num_warmup_steps=num_warmup_steps,
                                          optimizer_type='adamw')
loss = tf.keras.losses.BinaryCrossentropy(from_logits=True)
metrics = tf.metrics.BinaryAccuracy()

model.compile(optimizer=optimizer,
                         loss=loss,
                         metrics=metrics)
tf.keras.utils.plot_model(model)

history = model.fit(x=combined_train_ds, validation_data=combined_val_ds, epochs=5)

loss, accuracy = model.evaluate(combined_test_ds)
print(f"Test Loss: {loss}")
print(f"Test Accuracy: {accuracy}")

y_pred = ((model.predict(combined_test_ds)) > 0.5).astype('int32')

y_true = np.concatenate([y for x, y in combined_test_ds], axis=0)

from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix
cm = confusion_matrix(y_true, y_pred)

cm_display = ConfusionMatrixDisplay(cm).plot()

import json
import time
# Get the dictionary containing each metric and the loss for each epoch
history_dict = history.history
# Save it under the form of a json file
str(time.time)
json.dump(history_dict, open('ensemble_history_' + time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime()) + '.json', 'w'))

BERT_history = json.load(open('BERT_history.json', 'r'))



history_dict = history.history
BERT_dict = BERT_history
print(history_dict.keys())
print(BERT_dict.keys())

acc = history_dict['binary_accuracy']
val_acc = history_dict['val_binary_accuracy']
loss = history_dict['loss']
val_loss = history_dict['val_loss']

BERT_acc = BERT_dict['binary_accuracy']
BERT_val_acc = BERT_dict['val_binary_accuracy']
BERT_loss = BERT_dict['loss']
BERT_val_loss = BERT_dict['val_loss']


epochs = range(1, len(acc) + 1)
fig = plt.figure(figsize=(10, 6))
fig.tight_layout()

plt.subplot(2, 1, 1)

plt.plot(epochs, loss, 'r', label='Training loss')
plt.plot(epochs, BERT_loss, 'r--', label='Training loss (BERT)')

plt.plot(epochs, val_loss, 'b', label='Validation loss')
plt.plot(epochs, BERT_val_loss, 'b--', label='Validation loss (BERT)')
plt.title('Training and validation loss')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()

plt.subplot(2, 1, 2)
plt.plot(epochs, acc, 'r', label='Training acc')
plt.plot(epochs, BERT_acc, 'r--', label='Training acc (BERT)')
plt.plot(epochs, val_acc, 'b', label='Validation acc')
plt.plot(epochs, BERT_val_acc, 'b--', label='Validation acc (BERT)')
plt.title('Training and validation accuracy')
plt.xlabel('Epochs')
plt.ylabel('Accuracy')
plt.legend(loc='lower right')

plt.savefig("training_plot" +  time.strftime("%a, %d %b %Y %H:%M:%S", time.gmtime()) + ".png")