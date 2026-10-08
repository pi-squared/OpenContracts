"""Databricks text embeddings using the stock OpenAI-compatible implementation."""

import math
import os
from dataclasses import dataclass, field

from django.conf import settings

from opencontractserver.pipeline.base.settings_schema import (
    PipelineSetting,
    SettingType,
)
from opencontractserver.pipeline.embedders.openai_embedder import OpenAIEmbedder


class DatabricksEmbedder(OpenAIEmbedder):
    title = "Databricks text embeddings"
    description = "Configured Databricks serving endpoint through renewable app OAuth"
    api_batch_size = 32
    embed_max_concurrent_sub_batches = 1

    @dataclass
    class Settings(OpenAIEmbedder.Settings):
        openai_embedding_model: str = field(
            default_factory=lambda: os.environ["EMBEDDING_MODEL_ENDPOINT"],
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Bound Databricks embedding endpoint",
                    env_var="EMBEDDING_MODEL_ENDPOINT",
                )
            },
        )
        openai_embedding_dimensions: int = field(
            default_factory=lambda: int(os.environ["EMBEDDING_DIMENSIONS"]),
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Verified output dimension; changing it requires a compatible index",
                    env_var="EMBEDDING_DIMENSIONS",
                )
            },
        )

    @property
    def vector_size(self):
        return int(self._effective_settings.openai_embedding_dimensions)

    def _build_client(self, **kwargs):
        # The accounted stock path passes a literal public OpenAI URL. Both
        # ordinary and reserved calls must use this app's OAuth transport.
        kwargs["openai_api_base_url"] = settings.OPENAI_API_BASE_URL
        kwargs["openai_api_key"] = "app-oauth-loopback"
        return super()._build_client(**kwargs)

    def _validate_vectors(self, vectors):
        for vector in vectors:
            if vector is not None and (
                len(vector) != self.vector_size
                or any(not math.isfinite(value) for value in vector)
            ):
                raise ValueError("Databricks embedding dimension/value mismatch")

    def _embed_text_impl(self, text, **kwargs):
        vector = super()._embed_text_impl(text, **kwargs)
        self._validate_vectors([vector])
        return vector

    def embed_text_accounted(self, text):
        vector, tokens = super().embed_text_accounted(text)
        self._validate_vectors([vector])
        return vector, tokens

    def embed_texts_batch(self, texts, **kwargs):
        vectors = super().embed_texts_batch(texts, **kwargs)
        if vectors is not None:
            self._validate_vectors(vectors)
        return vectors
