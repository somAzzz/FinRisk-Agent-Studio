import pytest
from src.llm.client import EdgarLLMClient


def test_complete_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "complete")
    assert callable(client.complete)


def test_compute_embedding_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "compute_embedding")
    assert callable(client.compute_embedding)
