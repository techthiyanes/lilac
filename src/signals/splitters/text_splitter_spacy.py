"""Text splitters using spaCy."""
from typing import Any, Iterable, Optional

from spacy import Language
from typing_extensions import override

from ...embeddings.embedding_index import GetEmbeddingIndexFn
from ...schema import EnrichmentType, Field, ItemValue, RichData
from ...signals.signal import Signal
from .spacy_utils import load_spacy
from .splitter import SpanFields, SpanItem


class SentenceSplitterSpacy(Signal):
  """Splits documents into sentences."""
  name = 'sentences_spacy'
  enrichment_type = EnrichmentType.TEXT

  spacy_pipeline: str

  _tokenizer: Language

  def __init__(self, spacy_pipeline: str = 'en_core_web_sm', **kwargs: dict[Any, Any]):
    super().__init__(spacy_pipeline=spacy_pipeline, **kwargs)
    self._tokenizer = load_spacy(spacy_pipeline)

  @override
  def fields(self) -> Field:
    return Field(repeated_field=Field(fields=SpanFields({})))

  @override
  def compute(self,
              data: Optional[Iterable[RichData]] = None,
              keys: Optional[Iterable[bytes]] = None,
              get_embedding_index: Optional[GetEmbeddingIndexFn] = None) -> Iterable[ItemValue]:
    if data is None:
      raise ValueError('Sentence splitter requires text data.')

    for text in data:
      if not isinstance(text, str):
        raise ValueError('Sentence splitter requires text data.')
      sentences = self._tokenizer(text).sents
      yield [SpanItem(span=(token.start_char, token.end_char)) for token in sentences]
