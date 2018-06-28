#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Base class for loading dataset for language models.
   In this class, all data will be loaded at each step.
   You can use the multi-GPU version.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import basename, isfile, join
import numpy as np
import pandas as pd
import codecs
import logging
from tqdm import tqdm
logger = logging.getLogger('training')

from src.dataset.base import Base
from src.utils.io.labels.word import Idx2word, Word2idx
from src.utils.io.labels.character import Idx2char, Char2idx
from src.utils.directory import mkdir_join


class Dataset(Base):

    def __init__(self, corpus, data_save_path,
                 data_size, data_type, label_type,
                 batch_size, max_epoch=None,
                 shuffle=False, sort_utt=False, reverse=False,
                 sort_stop_epoch=None, tool='htk',
                 num_enque=None, dynamic_batching=False, vocab=False):
        """A class for loading dataset.
        Args:
            data_save_path (string): path to saved data
            data_size (string):
            data_type (string):
            label_type (string):
            batch_size (int): the size of mini-batch
            max_epoch (int): the max epoch. None means infinite loop.
            shuffle (bool): if True, shuffle utterances.
                This is disabled when sort_utt is True.
            sort_utt (bool): if True, sort all utterances in the ascending order
            reverse (bool): if True, sort utteraces in the descending order
            sort_stop_epoch (int): After sort_stop_epoch, training will revert
                back to a random order
            tool (string): htk or librosa or python_speech_features
            num_enque (int): the number of elements to enqueue
            dynamic_batching (bool): if True, batch size will be chainged
                dynamically in training
            vocab (bool or string):
        """
        self.corpus = corpus
        self.data_type = data_type
        self.data_size = data_size
        self.label_type = label_type
        self.batch_size = batch_size
        self.max_epoch = max_epoch
        self.shuffle = shuffle
        self.sort_utt = sort_utt
        self.sort_stop_epoch = sort_stop_epoch
        self.tool = tool
        self.num_enque = num_enque
        self.dynamic_batching = dynamic_batching

        # Corpus depending
        if corpus in ['csj', 'swbd', 'wsj']:
            self.is_test = True if 'eval' in data_type else False
        elif corpus in['librispeech', 'timit']:
            self.is_test = True if 'test' in data_type else False
        else:
            raise NotImplementedError

        # TODO: fix this
        if corpus == 'librispeech':
            if data_type == 'train':
                data_type += '_' + data_size

        if vocab and data_size != '' and data_size != vocab:
            self.vocab_file_path = join(
                data_save_path, 'vocab', vocab, label_type + '.txt')
            vocab_file_path_org = join(
                data_save_path, 'vocab', data_size, label_type + '.txt')
        else:
            self.vocab_file_path = join(
                data_save_path, 'vocab', data_size, label_type + '.txt')

        if label_type == 'word':
            self.idx2word = Idx2word(self.vocab_file_path)
            self.word2idx = Word2idx(self.vocab_file_path)
        elif 'character' in label_type:
            self.idx2char = Idx2char(self.vocab_file_path)
            self.char2idx = Char2idx(self.vocab_file_path)
        else:
            raise ValueError(label_type)

        super(Dataset, self).__init__(vocab_file_path=self.vocab_file_path)

        # Load dataset file
        if vocab and data_size != '' and data_size != vocab and not self.is_test:
            dataset_path = mkdir_join(
                data_save_path, 'dataset', tool, data_size + '_' + vocab, data_type, label_type + '.csv')

            # Change token indices
            if not isfile(dataset_path):
                dataset_path_org = join(
                    data_save_path, 'dataset', tool, data_size, data_type, label_type + '.csv')
                df = pd.read_csv(dataset_path_org, encoding='utf-8')
                df = df.loc[:, ['frame_num', 'input_path', 'transcript']]

                # Change vocabulary
                org2new = {}
                str2idx_org = {}
                str2idx_new = {}
                # new vocab
                with codecs.open(self.vocab_file_path, 'r', 'utf-8') as f:
                    vocab_count = 0
                    for line in f:
                        if line.strip() != '':
                            str2idx_new[line.strip()] = vocab_count
                            vocab_count += 1
                # original vocab
                with codecs.open(vocab_file_path_org, 'r', 'utf-8') as f:
                    vocab_count = 0
                    for line in f:
                        if line.strip() != '':
                            str2idx_org[line.strip()] = vocab_count
                            vocab_count += 1
                for k, v in str2idx_org.items():
                    if k in str2idx_new.keys():
                        org2new[v] = str2idx_new[k]
                    else:
                        org2new[v] = str2idx_new['OOV']

                # Update the transcript
                for i in tqdm(df['transcript'].index):
                    df['transcript'][i] = ' '.join(
                        list(map(lambda x: str(org2new[int(x)]), df['transcript'][i].split(' '))))

                # Save as a new file
                df.to_csv(dataset_path, encoding='utf-8')
            else:
                df = pd.read_csv(dataset_path, encoding='utf-8')
                df = df.loc[:, ['frame_num', 'input_path', 'transcript']]
        else:
            dataset_path = join(
                data_save_path, 'dataset', tool, data_size, data_type, label_type + '.csv')
            df = pd.read_csv(dataset_path, encoding='utf-8')
            df = df.loc[:, ['frame_num', 'input_path', 'transcript']]

        # Sort paths to input & label
        if sort_utt:
            df = df.sort_values(by='frame_num', ascending=not reverse)
        else:
            df = df.sort_values(by='input_path', ascending=True)

        self.df = df
        self.rest = set(list(df.index))

    def select_batch_size(self, batch_size, min_frame_num_batch):
        return batch_size

    def make_batch(self, data_indices):
        """Create mini-batch per step.
        Args:
            data_indices (np.ndarray):
        Returns:
            batch (dict):
                ys (list): target labels in the main task of size `[B, L]`
                input_names (list): file names of input data of size `[B]`
        """
        # Load dataset in mini-batch
        transcripts = np.array(self.df['transcript'][data_indices])

        if self.is_test:
            ys = [self.df['transcript'][data_indices[b]]
                  for b in range(len(data_indices))]
            # NOTE: transcript is not tokenized
        else:
            ys = [list(map(int, transcripts[b].split(' ')))
                  for b in range(len(data_indices))]

        # TODO: fix later
        # input_names = list(
        #     map(lambda path: basename(path).split('.')[0],
        #         self.df['input_path'][data_indices]))
        input_names = self.df.index.values.tolist()

        return {'ys': ys, 'input_names': input_names}
