"""Utilities for loading and processing GLUE datasets for BERT rank experiments"""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/01_data.ipynb.

# %% auto 0
__all__ = ['F1Score', 'accuracy', 'GLUEDataManager', 'TextGetter']

# %% ../../nbs/01_data.ipynb 5
import os
import torch
import numpy as np
import pandas as pd
import copy

from fastai.text.all import *
from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from sklearn.metrics import accuracy_score, f1_score

from .transforms import TransTensorText, Undict, TokBatchTransform
from torch.utils.data._utils.collate import default_collate

# %% ../../nbs/01_data.ipynb 7
class F1Score:
    "Custom F1 Score metric for fastai"
    def __init__(self, average='binary'):
        self.average = average

    def __call__(self, preds, targets):
        preds = torch.argmax(preds, dim=1)
        return f1_score(targets.cpu().numpy(), preds.cpu().numpy(), average=self.average)

    def __repr__(self):
        return f"F1Score(average={self.average})"

# %% ../../nbs/01_data.ipynb 8
def accuracy(preds, targets):
    "Accuracy metric for fastai"
    preds = torch.argmax(preds, dim=1)
    return (preds == targets).float().mean()

# %% ../../nbs/01_data.ipynb 9
class GLUEDataManager:
    """Manager for GLUE dataset loading and processing."""

    def __init__(self, task_name, model_name, max_length=512, bs=32, val_bs=None, cache_dir=None):
        self.task_name = task_name.lower()
        self.model_name = model_name
        self.max_length = max_length
        self.bs = bs
        self.val_bs = val_bs or 2*bs
        self.cache_dir = cache_dir

        if self.task_name not in ['sst2', 'mrpc', 'rte']:
            raise ValueError(f"Task {self.task_name} not supported. Use one of: sst2, mrpc, rte")

        self.text_fields = {
            'sst2': ['sentence', None],
            'mrpc': ['sentence1', 'sentence2'],
            'rte': ['sentence1', 'sentence2']
        }

        self.metrics = {
            'sst2': [accuracy],
            'mrpc': [F1Score(), accuracy],
            'rte': [accuracy]
        }

        self.num_labels = {
            'sst2': 2,
            'mrpc': 2,
            'rte': 2
        }

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

    def load_datasets(self, custom_datasets=None, max_samples=None):
        print(f"Loading datasets for {self.task_name}...")

        if custom_datasets is not None:
            datasets = custom_datasets
        else:
            datasets = load_dataset('glue', self.task_name, cache_dir=self.cache_dir)

        if max_samples is not None:
            for split in datasets.keys():
                if split != 'test':
                    datasets[split] = datasets[split].select(range(min(max_samples, len(datasets[split]))))

        print(f"Dataset sizes: {', '.join([f'{k}: {len(v)}' for k, v in datasets.items()])}")
        self.datasets = datasets
        return datasets

    def _prepare_fastai_data(self, datasets):
        text_field1, text_field2 = self.text_fields[self.task_name]

        train_texts, train_labels = [], []
        for item in datasets['train']:
            if text_field2 is not None:
                train_texts.append((item[text_field1], item[text_field2]))
            else:
                train_texts.append(item[text_field1])
            train_labels.append(item['label'])

        val_texts, val_labels = [], []
        for item in datasets['validation']:
            if text_field2 is not None:
                val_texts.append((item[text_field1], item[text_field2]))
            else:
                val_texts.append(item[text_field1])
            val_labels.append(item['label'])

        return train_texts, train_labels, val_texts, val_labels

    def create_dataloaders(self, custom_datasets=None, max_samples=None):
        if not hasattr(self, 'datasets') or custom_datasets is not None:
            self.load_datasets(custom_datasets, max_samples)

        train_texts, train_labels, val_texts, val_labels = self._prepare_fastai_data(self.datasets)

        # Combine train and validation data for DataBlock
        all_texts = train_texts + val_texts
        all_labels = train_labels + val_labels
        df = pd.DataFrame({'text': all_texts, 'label': all_labels})

        # Calculate sequence lengths for sorting (optional, but helpful for efficiency)
        train_lens = [len(str(t)) for t in train_texts]
        val_lens = [len(str(t)) for t in val_texts]

        # Use the reference code pattern for the DataBlock setup
        dls_kwargs = {
            'before_batch': TokBatchTransform(
                pretrained_model_name=self.model_name,
                max_length=self.max_length,
                padding='max_length',
                truncation=True
            ),
            'create_batch': fa_convert  # Use fastai's standard batch creation
        }

        # Define the text block with the same structure as reference
        text_block = TransformBlock(
            dl_type=SortedDL,  # Use SortedDL to enable length-based sorting
            dls_kwargs=dls_kwargs,
            batch_tfms=Undict()  # Add Undict for decoding
        )

        # Create DataBlock
        glue_block = DataBlock(
            blocks=[text_block, CategoryBlock()],
            get_x=ColReader('text'),
            get_y=ColReader('label'),
            splitter=IndexSplitter(range(len(train_texts), len(train_texts) + len(val_labels)))
        )

        # Create DataLoaders with length-based resources for efficiency
        dl_kwargs = [{'res': train_lens}, {'val_res': val_lens}]
        dls = glue_block.dataloaders(
            df,
            bs=self.bs,
            val_bs=self.val_bs,
            dl_kwargs=dl_kwargs
        )

        self.dls = dls
        return dls

    def create_test_dataloader(self, test_data=None):
        if not hasattr(self, 'dls'):
            raise ValueError("You must create training DataLoaders first by calling create_dataloaders()")

        test_data = test_data or self.datasets.get('test')
        if test_data is None:
            raise ValueError("No test data available.")

        text_field1, text_field2 = self.text_fields[self.task_name]
        test_texts = []
        for item in test_data:
            if text_field2 is not None:
                test_texts.append((item[text_field1], item[text_field2]))
            else:
                test_texts.append(item[text_field1])

        test_df = pd.DataFrame({'text': test_texts, 'label': [0] * len(test_texts)})
        test_dl = self.dls.test_dl(test_df)
        return test_dl

class TextGetter(ItemTransform):
    """ItemTransform for getting text fields from a sample"""
    def __init__(self, s1='text', s2=None):
        self.s1, self.s2 = s1, s2
    def encodes(self, sample):
        if self.s2 is None: return sample[self.s1]
        else: return sample[self.s1], sample[self.s2]
