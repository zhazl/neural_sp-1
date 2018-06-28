#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Plot the hierarchical CTC posteriors."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath, isdir
import sys
import argparse
import shutil

sys.path.append(abspath('../../../'))
from srcs.models.load_model import load
from src.dataset.loader import Dataset as Dataset_asr
from src.dataset.loader_hierarchical_p2w import Dataset as Dataset_p2w
from src.utils.directory import mkdir_join, mkdir
from src.bin.visualization.utils.visualization.ctc import plot_hierarchical_ctc_probs
from src.utils.config import load_config

parser = argparse.ArgumentParser()
parser.add_argument('--corpus', type=str,
                    help='the name of corpus')
parser.add_argument('--data_type', type=str,
                    help='the type of data (ex. train, dev etc.)')
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
args = parser.parse_args()


def main():

    # Load a config file
    config = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Load dataset
    if config['input_type'] == 'speech':
        dataset = Dataset_asr(
            corpus=args.corpus,
            data_save_path=args.data_save_path,
            input_freq=config['input_freq'],
            use_delta=config['use_delta'],
            use_double_delta=config['use_double_delta'],
            data_size=config['data_size'] if 'data_size' in config.keys(
            ) else '',
            data_type=args.data_type,
            label_type=config['label_type'],
            label_type_sub=config['label_type_sub'],
            batch_size=args.eval_batch_size,
            sort_utt=False, reverse=False, tool=config['tool'])
    elif config['input_type'] == 'text':
        dataset = Dataset_p2w(
            corpus=args.corpus,
            data_save_path=args.data_save_path,
            data_type=args.data_type,
            data_size=config['data_size'],
            label_type_in=config['label_type_in'],
            label_type=config['label_type'],
            label_type_sub=config['label_type_sub'],
            batch_size=args.eval_batch_size,
            sort_utt=False, reverse=False, tool=config['tool'],
            vocab=config['vocab'],
            use_ctc=config['model_type'] == 'hierarchical_ctc',
            subsampling_factor=2 ** sum(config['subsample_list']),
            use_ctc_sub=config['model_type'] == 'hierarchical_ctc' or (
                config['model_type'] == 'hierarchical_attention' and config['ctc_loss_weight_sub'] > 0),
            subsampling_factor_sub=2 ** sum(config['subsample_list'][:config['encoder_num_layers_sub'] - 1]))
        config['num_classes_input'] = dataset.num_classes_in

    config['num_classes'] = dataset.num_classes
    config['num_classes_sub'] = dataset.num_classes_sub

    # Load model
    model = load(model_type=config['model_type'],
                 config=config,
                 backend=config['backend'])

    # Restore the saved parameters
    model.load_checkpoint(save_path=args.model_path, epoch=args.epoch)

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    save_path = mkdir_join(args.model_path, 'ctc_probs')

    # Clean directory
    if save_path is not None and isdir(save_path):
        shutil.rmtree(save_path)
        mkdir(save_path)

    for batch, is_new_epoch in dataset:
        # Get CTC probs
        probs = model.posteriors(batch['xs'], batch['x_lens'],
                                 temperature=1)
        probs_sub = model.posteriors(batch['xs'], batch['x_lens'], task_index=1,
                                     temperature=1)
        # NOTE: probs: '[B, T, num_classes]'
        # NOTE: probs_sub: '[B, T, num_classes_sub]'

        # Visualize
        for b in range(len(batch['xs'])):
            if args.corpus == 'csj':
                speaker = batch['input_names'][b].split('_')[0]
            elif args.corpus == 'swbd':
                speaker = '_'.join(batch['input_names'][b].split('_')[:2])
            elif args.corpus == 'librispeech':
                speaker = '-'.join(batch['input_names'][b].split('-')[:2])
            else:
                speaker = ''

            plot_hierarchical_ctc_probs(
                probs[b, :batch['x_lens'][b], :],
                probs_sub[b, :batch['x_lens'][b], :],
                frame_num=batch['x_lens'][b],
                num_stack=dataset.num_stack,
                spectrogram=batch['xs'][b, :,
                                        :dataset.input_freq] if config['input_type'] == 'speech' else None,
                save_path=mkdir_join(save_path, speaker,
                                     batch['input_names'][b] + '.png'),
                figsize=(40, 8))

        if is_new_epoch:
            break


if __name__ == '__main__':
    main()
