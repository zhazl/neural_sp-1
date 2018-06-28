#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Training loop."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import logging
logger = logging.getLogger('training')

import torch

try:
    import cupy
except:
    logger.warning('Install cupy.')
try:
    import chainer
except:
    logger.warning('Install chainer.')

INF = float("inf")


class Updater(object):
    """
    Args:
        clip_grad_norm (float):
        backend (string): pytorch or chainer
    """

    def __init__(self, clip_grad_norm, backend):
        self.clip_grad_norm = clip_grad_norm
        self.backend = backend

    def __call__(self, model, batch, is_eval=False):
        """
        Args:
            model (torch.nn.Module or chainer.Chain):
            batch (tuple):
            is_eval (bool):
        Returns:
            model (torch.nn.Module or chainer.Chain):
            loss_val (float):
            acc (float): Token-level accuracy in teacher-forcing
        """
        try:
            # Step for parameter update
            if self.backend == 'pytorch':
                if is_eval:
                    loss, acc = model(batch['xs'], batch['ys'], is_eval=True)
                else:
                    model.module.optimizer.zero_grad()
                    if len(model.device_ids) >= 1:
                        torch.cuda.empty_cache()
                    loss, acc = model(batch['xs'], batch['ys'])
                    if len(model.device_ids) > 1:
                        loss.backward(torch.ones(len(model.device_ids)))
                    else:
                        loss.backward()
                    loss.detach()  # Trancate the graph
                    if self.clip_grad_norm > 0:
                        if model.module.torch_version < 0.4:
                            torch.nn.utils.clip_grad_norm(
                                model.module.parameters(), self.clip_grad_norm)
                        else:
                            torch.nn.utils.clip_grad_norm_(
                                model.module.parameters(), self.clip_grad_norm)
                    model.module.optimizer.step()
                    # TODO: Add scheduler

                if model.module.torch_version < 0.4:
                    loss_val = loss.data[0]
                else:
                    loss_val = loss.item()

            elif self.backend == 'chainer':
                if is_eval:
                    model.optimizer.target.cleargrads()
                    loss, acc = model(batch['xs'], batch['ys'])
                    loss.backward()
                    loss.unchain_backward()
                    model.optimizer.update()
                else:
                    loss, acc = model(batch['xs'], batch['ys'], is_eval=True)
                loss_val = loss.data

            del loss

        except RuntimeError as e:
            logger.warning('!!!Skip mini-batch!!! (max_frame_num: %d, batch: %d)' %
                           (max(len(x) for x in batch['xs']), len(batch['xs'])))
            if self.backend == 'pytorch':
                model.module.optimizer.zero_grad()
                if len(model.device_ids) >= 1:
                    torch.cuda.empty_cache()
            elif self.backend == 'chainer':
                model.optimizer.target.cleargrads()
            loss_val = 0.
            acc = 0.

        if loss_val == INF or loss_val == -INF:
            logger.warning("WARNING: received an inf loss.")

        # Delete features
        del batch

        return model, loss_val, acc
