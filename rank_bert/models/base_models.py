"""Implementation of BERT model variants for rank manipulation experiments"""

# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/02_models.ipynb.

# %% auto 0
__all__ = ['GLUE_NUM_LABELS', 'BERT_CONFIGS', 'get_pretrained_model', 'count_parameters', 'BertWrapper', 'get_wrapped_model']

# %% ../../nbs/02_models.ipynb 5
import torch
import torch.nn as nn
import numpy as np
from transformers import AutoConfig, AutoModelForSequenceClassification, BertConfig, BertForSequenceClassification
from fastai.text.all import *

# %% ../../nbs/02_models.ipynb 7
# GLUE task constants
GLUE_NUM_LABELS = {
    'sst2': 2,
    'mrpc': 2,
    'rte': 2
}

# %% ../../nbs/02_models.ipynb 8
# Model configuration constants
BERT_CONFIGS = {
    'prajjwal1/bert-tiny': {
        'hidden_size': 128,
        'num_hidden_layers': 2,
        'num_attention_heads': 2,
        'intermediate_size': 512
    },
    'prajjwal1/bert-mini': {
        'hidden_size': 256,
        'num_hidden_layers': 4,
        'num_attention_heads': 4,
        'intermediate_size': 1024
    },
    'prajjwal1/bert-small': {
        'hidden_size': 512,
        'num_hidden_layers': 4,
        'num_attention_heads': 8,
        'intermediate_size': 2048
    }
}

# %% ../../nbs/02_models.ipynb 9
def get_pretrained_model(model_name, task_name, num_labels=None):
    """
    Initialize a pretrained model for a specific task.

    Args:
        model_name (str): HuggingFace model name or path (e.g., 'prajjwal1/bert-tiny', 'bert-mini')
        task_name (str): GLUE task name ('sst2', 'mrpc', 'rte')
        num_labels (int, optional): Number of output labels

    Returns:
        PreTrainedModel: Initialized model
    """
    # Get the number of labels for the task
    num_labels = num_labels or GLUE_NUM_LABELS.get(task_name, 2)

    # Check if the model name is a known configuration or a HuggingFace model
    if model_name in BERT_CONFIGS:
        # Create a new model with the specified configuration
        config = BertConfig(
            **BERT_CONFIGS[model_name],
            num_labels=num_labels,
            hidden_dropout_prob=0.1,
            attention_probs_dropout_prob=0.1
        )
        model = BertForSequenceClassification(config)
    else:
        # Load a pretrained model from HuggingFace
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=num_labels
        )

    return model

# %% ../../nbs/02_models.ipynb 10
def count_parameters(model):
    """
    Count number of trainable parameters in a model.

    Args:
        model: PyTorch model

    Returns:
        Number of trainable parameters
    """
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

# %% ../../nbs/02_models.ipynb 11
class BertWrapper(Module):
    """
    Wrapper around BERT model for fastai integration.
    Handles input formatting and output processing.

    This class serves as a base for rank-constrained models,
    making it easier to modify and monitor model behavior.
    """

    def __init__(self, model):
        """
        Initialize the BERT wrapper.

        Args:
            model: Pretrained BERT model
        """
        self.model = model

    def forward(self, x):
        """
        Forward pass through the model.

        Args:
            x: Dictionary of inputs from tokenizer

        Returns:
            Model outputs
        """
        # Handle either dict or tuple input
        if isinstance(x, tuple):
            x = x[0]

        # Extract and ensure inputs are on the correct device
        input_ids = x['input_ids']
        attention_mask = x['attention_mask']
        token_type_ids = x.get('token_type_ids', None)

        # Forward pass through BERT
        if token_type_ids is not None:
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids
            )
        else:
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask
            )

        return outputs.logits

# %% ../../nbs/02_models.ipynb 12
def get_wrapped_model(model_name, task_name, num_labels=None):
    """
    Get a wrapped BERT model for fastai integration.

    Args:
        model_name (str): HuggingFace model name or path
        task_name (str): GLUE task name
        num_labels (int, optional): Number of output labels

    Returns:
        BertWrapper: Wrapped model
    """
    model = get_pretrained_model(model_name, task_name, num_labels)
    return BertWrapper(model)
