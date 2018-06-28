#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Tuning hyperparameters for the joint decoding of the hierarchical attention model."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
from distutils.util import strtobool

sys.path.append(abspath('../../../'))
from src.models.load_model import load
from src.dataset.loader_hierarchical import Dataset
from src.metrics.character import eval_char
from src.metrics.word import eval_word
from src.utils.config import load_config
from src.utils.evaluation.logging import set_logger

parser = argparse.ArgumentParser()
parser.add_argument('--corpus', type=str,
                    help='the name of corpus')
parser.add_argument('--eval_sets', type=str, nargs='+',
                    help='evaluation sets')
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--beam_width', type=int, default=1,
                    help='the size of beam in the main task')
parser.add_argument('--beam_width_sub', type=int, default=1,
                    help='the size of beam in the sub task')
parser.add_argument('--length_penalty', type=float, default=0,
                    help='length penalty')
parser.add_argument('--coverage_penalty', type=float, default=0,
                    help='coverage penalty')
parser.add_argument('--rnnlm_weight', type=float, default=0,
                    help='the weight of RNNLM score of the main task')
parser.add_argument('--rnnlm_weight_sub', type=float, default=0,
                    help='the weight of RNNLM score of the sub task')
parser.add_argument('--rnnlm_path', type=str, default=None, nargs='?',
                    help='path to the RMMLM of the main task')
parser.add_argument('--rnnlm_path_sub', type=str, default=None, nargs='?',
                    help='path to the RMMLM of the sub task')
parser.add_argument('--resolving_unk', type=strtobool, default=False)
parser.add_argument('--joint_decoding', type=strtobool, default=False)
args = parser.parse_args()

# corpus depending
if args.corpus == 'csj':
    MAX_DECODE_LEN_WORD = 100
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 200
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

    MAX_DECODE_LEN_PHONE = 200
    MIN_DECODE_LEN_PHONE = 1
    MAX_DECODE_LEN_RATIO_PHONE = 1
    MIN_DECODE_LEN_RATIO_PHONE = 0
elif args.corpus == 'swbd':
    MAX_DECODE_LEN_WORD = 100
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 300
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2

    MAX_DECODE_LEN_PHONE = 300
    MIN_DECODE_LEN_PHONE = 1
    MAX_DECODE_LEN_RATIO_PHONE = 1
    MIN_DECODE_LEN_RATIO_PHONE = 0
elif args.corpus == 'librispeech':
    MAX_DECODE_LEN_WORD = 200
    MIN_DECODE_LEN_WORD = 1
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 600
    MIN_DECODE_LEN_CHAR = 1
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2
elif args.corpus == 'wsj':
    MAX_DECODE_LEN_WORD = 32
    MIN_DECODE_LEN_WORD = 2
    MAX_DECODE_LEN_RATIO_WORD = 1
    MIN_DECODE_LEN_RATIO_WORD = 0

    MAX_DECODE_LEN_CHAR = 199
    MIN_DECODE_LEN_CHAR = 10
    MAX_DECODE_LEN_RATIO_CHAR = 1
    MIN_DECODE_LEN_RATIO_CHAR = 0.2
    # NOTE:
    # dev93 (char): 10-199
    # test_eval92 (char): 16-195
    # dev93 (word): 2-32
    # test_eval92 (word): 3-30
elif args.corpus == 'timit':
    MAX_DECODE_LEN_PHONE = 71
    MIN_DECODE_LEN_PHONE = 13
    MAX_DECODE_LEN_RATIO_PHONE = 1
    MIN_DECODE_LEN_RATIO_PHONE = 0
    # NOTE*
    # dev: 13-71
    # test: 13-69
else:
    raise ValueError(args.corpus)


def main():

    # Load a config file
    config = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Setting for logging
    logger = set_logger(args.model_path)

    # Load dataset
    if config['input_type'] == 'speech':
        eval_set = Dataset(
            corpus=args.corpus,
            data_save_path=args.data_save_path,
            input_freq=config['input_freq'],
            use_delta=config['use_delta'],
            use_double_delta=config['use_double_delta'],
            data_size=config['data_size'] if 'data_size' in config.keys(
            ) else '',
            data_type=args.eval_sets[0],
            label_type=config['label_type'],
            label_type_sub=config['label_type_sub'],
            batch_size=args.eval_batch_size,
            tool=config['tool'])
    elif config['input_type'] == 'text':
        raise NotImplementedError
    config['num_classes'] = eval_set.num_classes
    config['num_classes_sub'] = eval_set.num_classes_sub

    # Load model
    model = load(model_type=config['model_type'],
                 config=config,
                 backend=config['backend'])
    assert model.model_type == 'hierarchical_attention'

    # Restore the saved parameters
    epoch, _, _, _ = model.load_checkpoint(
        save_path=args.model_path, epoch=args.epoch)

    # For shallow fusion
    if not (config['rnnlm_fusion_type'] and config['rnnlm_path']) and args.rnnlm_path is not None and args.rnnlm_weight > 0:
        # Load a RNNLM config file
        config_rnnlm = load_config(
            join(args.rnnlm_path, 'config.yml'), is_eval=True)
        assert config['label_type'] == config_rnnlm['label_type']
        config_rnnlm['num_classes'] = eval_set.num_classes

        # Load the pre-trianed RNNLM
        rnnlm = load(model_type=config_rnnlm['model_type'],
                     config=config_rnnlm,
                     backend=config_rnnlm['backend'])
        rnnlm.load_checkpoint(save_path=args.rnnlm_path, epoch=-1)
        rnnlm.flatten_parameters()
        model.rnnlm_0_fwd = rnnlm
        logger.info('RNNLM path (main): %s' % args.rnnlm_path)
        logger.info('RNNLM weight (main): %.3f' % args.rnnlm_weight)

    if not (config['rnnlm_fusion_type'] and config['rnnlm_path_sub']) and args.rnnlm_path_sub is not None and args.rnnlm_weight_sub > 0:
        # Load a RNNLM config file
        config_rnnlm_sub = load_config(
            join(args.rnnlm_path_sub, 'config.yml'), is_eval=True)
        assert config['label_type_sub'] == config_rnnlm_sub['label_type']
        config_rnnlm_sub['num_classes'] = eval_set.num_classes_sub

        # Load the pre-trianed RNNLM
        rnnlm_sub = load(model_type=config_rnnlm_sub['model_type'],
                         config=config_rnnlm_sub,
                         backend=config_rnnlm_sub['backend'])
        rnnlm_sub.load_checkpoint(
            save_path=args.rnnlm_path_sub, epoch=-1)
        rnnlm_sub.flatten_parameters()
        model.rnnlm_1_fwd = rnnlm_sub
        logger.info('RNNLM path (sub): %s' % args.rnnlm_path_sub)
        logger.info('RNNLM weight (sub): %.3f' % args.rnnlm_weight_sub)

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    logger.info('beam width (main): %d' % args.beam_width)
    logger.info('beam width (sub) : %d' % args.beam_width_sub)
    logger.info('epoch: %d' % (epoch - 1))
    logger.info('resolving_unk: %s' % str(args.resolving_unk))
    logger.info('joint_decoding: %s' % str(args.joint_decoding))

    for score_sub_weight in [w * 0.1 for w in range(0, 10, 2)]:
        logger.info('\nscore_sub_weight : %f' % score_sub_weight)

        wer, df = eval_word(models=[model],
                            dataset=eval_set,
                            eval_batch_size=args.eval_batch_size,
                            beam_width=args.beam_width,
                            max_decode_len=MAX_DECODE_LEN_WORD,
                            min_decode_len=MIN_DECODE_LEN_WORD,
                            min_decode_len_ratio=MIN_DECODE_LEN_RATIO_WORD,
                            beam_width_sub=args.beam_width_sub,
                            max_decode_len_sub=MAX_DECODE_LEN_CHAR,
                            min_decode_len_sub=MIN_DECODE_LEN_CHAR,
                            length_penalty=args.length_penalty,
                            coverage_penalty=args.coverage_penalty,
                            rnnlm_weight=args.rnnlm_weight,
                            rnnlm_weight_sub=args.rnnlm_weight_sub,
                            progressbar=True,
                            resolving_unk=args.resolving_unk,
                            joint_decoding=args.joint_decoding,
                            score_sub_weight=score_sub_weight)
        logger.info('  WER (%s, main): %.3f %%' % (eval_set.data_type, wer))
        logger.info(df)


if __name__ == '__main__':
    main()
