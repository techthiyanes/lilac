"""Test for the concept scorer."""

import pathlib
from typing import Generator, Iterable, Type, cast

import numpy as np
import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from ..concepts.concept import ConceptColumnInfo, ConceptModel, ExampleIn
from ..concepts.db_concept import (
  ConceptDB,
  ConceptModelDB,
  ConceptUpdate,
  DiskConceptDB,
  DiskConceptModelDB,
)
from ..config import CONFIG
from ..data.dataset_duckdb import DatasetDuckDB
from ..data.dataset_test_utils import TestDataMaker
from ..data.dataset_utils import lilac_embedding
from ..db_manager import set_default_dataset_cls
from ..embeddings.vector_store_numpy import NumpyVectorStore
from ..schema import UUID_COLUMN, Item, RichData, SignalInputType
from .concept_scorer import ConceptScoreSignal
from .signal import TextEmbeddingSignal, clear_signal_registry, register_signal

ALL_CONCEPT_DBS = [DiskConceptDB]
ALL_CONCEPT_MODEL_DBS = [DiskConceptModelDB]


@pytest.fixture(autouse=True)
def set_data_path(tmp_path: pathlib.Path, mocker: MockerFixture) -> None:
  mocker.patch.dict(CONFIG, {'LILAC_DATA_PATH': str(tmp_path)})


EMBEDDING_MAP: dict[str, list[float]] = {
  'not in concept': [0.1, 0.9, 0.0],
  'in concept': [0.9, 0.1, 0.0],
  'a new data point': [0.1, 0.2, 0.3],
  'hello.': [0.1, 0.2, 0.3],
  'hello2.': [0.1, 0.2, 0.3],
}


class TestEmbedding(TextEmbeddingSignal):
  """A test embed function."""
  name = 'test_embedding'

  @override
  def compute(self, data: Iterable[RichData]) -> Iterable[Item]:
    """Embed the examples, use a hashmap to the vector for simplicity."""
    for example in data:
      if example not in EMBEDDING_MAP:
        raise ValueError(f'Example "{str(example)}" not in embedding map')
      yield [lilac_embedding(0, len(example), np.array(EMBEDDING_MAP[cast(str, example)]))]


@pytest.fixture(scope='module', autouse=True)
def setup_teardown() -> Generator:
  # Setup.
  set_default_dataset_cls(DatasetDuckDB)
  register_signal(TestEmbedding)

  # Unit test runs.
  yield

  # Teardown.
  clear_signal_registry()


@pytest.mark.parametrize('db_cls', ALL_CONCEPT_DBS)
def test_embedding_does_not_exist(db_cls: Type[ConceptDB]) -> None:
  db = db_cls()
  namespace = 'test'
  concept_name = 'test_concept'
  db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept')
  ]
  db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  with pytest.raises(ValueError, match='Signal "unknown_embedding" not found in the registry'):
    ConceptScoreSignal(namespace='test', concept_name='test_concept', embedding='unknown_embedding')


def test_concept_does_not_exist() -> None:
  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')
  with pytest.raises(ValueError, match='Concept "test/test_concept" does not exist'):
    signal.compute(['a new data point', 'not in concept'])


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
@pytest.mark.parametrize('model_db_cls', ALL_CONCEPT_MODEL_DBS)
def test_concept_model_score(concept_db_cls: Type[ConceptDB],
                             model_db_cls: Type[ConceptModelDB]) -> None:
  concept_db = concept_db_cls()
  model_db = model_db_cls(concept_db)
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept')
  ]
  concept_db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')

  # Explicitly sync the model with the concept.
  model = ConceptModel(
    namespace='test', concept_name='test_concept', embedding_name='test_embedding')
  model_db.sync(model)

  result_items = list(signal.compute(['a new data point', 'not in concept']))
  scores = [
    result_item['test_embedding'][0][f'{namespace}/{concept_name}']
    for result_item in result_items
    if result_item
  ]
  assert scores[0] > 0 and scores[0] < 1
  assert scores[1] < 0.5


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
@pytest.mark.parametrize('model_db_cls', ALL_CONCEPT_MODEL_DBS)
def test_concept_model_with_dataset_score(concept_db_cls: Type[ConceptDB],
                                          model_db_cls: Type[ConceptModelDB],
                                          make_test_data: TestDataMaker) -> None:
  dataset = make_test_data([{
    UUID_COLUMN: '1',
    'text': 'hello.',
  }, {
    UUID_COLUMN: '2',
    'text': 'hello2.',
  }])

  dataset.compute_signal(TestEmbedding(), 'text')

  concept_db = concept_db_cls()
  model_db = model_db_cls(concept_db)
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept')
  ]
  concept_db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  column_info = ConceptColumnInfo(
    namespace=dataset.namespace, name=dataset.dataset_name, path='text')
  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')
  signal.set_column_info(column_info)

  # Explicitly sync the model with the concept.
  model = ConceptModel(
    namespace='test', concept_name='test_concept', embedding_name='test_embedding')
  model_db.sync(model)

  result_items = list(signal.compute(['a new data point', 'in concept', 'not in concept']))
  scores = [
    result_item['test_embedding'][0][f'{namespace}/{concept_name}']
    for result_item in result_items
    if result_item
  ]
  assert scores[0] > 0 and scores[0] < 1  # 'a new data point' may or may not be in the concept.
  assert scores[1] > 0.5  # 'in concept' is in the concept.
  assert scores[2] < 0.5  # 'not in concept' is not in the concept.
  assert len(scores) == 3


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
@pytest.mark.parametrize('model_db_cls', ALL_CONCEPT_MODEL_DBS)
def test_concept_model_vector_score(concept_db_cls: Type[ConceptDB],
                                    model_db_cls: Type[ConceptModelDB]) -> None:
  concept_db = concept_db_cls()
  model_db = model_db_cls(concept_db)
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept')
  ]
  concept_db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')

  # Explicitly sync the model with the concept.
  model = ConceptModel(
    namespace='test', concept_name='test_concept', embedding_name='test_embedding')
  model_db.sync(model)

  vector_store = NumpyVectorStore()
  embeddings = np.array([
    EMBEDDING_MAP['in concept'], EMBEDDING_MAP['not in concept'], EMBEDDING_MAP['a new data point']
  ])
  vector_store.add([('1',), ('2',), ('3',)], embeddings)

  scores = cast(list[float], list(signal.vector_compute([('1',), ('2',), ('3',)], vector_store)))
  assert scores[0] > 0.5  # '1' is in the concept.
  assert scores[1] < 0.5  # '2' is not in the concept.
  assert scores[2] > 0 and scores[2] < 1  # '3' may or may not be in the concept.


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
@pytest.mark.parametrize('model_db_cls', ALL_CONCEPT_MODEL_DBS)
def test_concept_model_topk_score(concept_db_cls: Type[ConceptDB],
                                  model_db_cls: Type[ConceptModelDB]) -> None:
  concept_db = concept_db_cls()
  model_db = model_db_cls(concept_db)
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept')
  ]
  concept_db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')

  # Explicitly sync the model with the concept.
  model = ConceptModel(
    namespace='test', concept_name='test_concept', embedding_name='test_embedding')
  model_db.sync(model)
  vector_store = NumpyVectorStore()
  vector_store.add([('1',), ('2',), ('3',)],
                   np.array([[0.1, 0.2, 0.3], [0.1, 0.87, 0.0], [1.0, 0.0, 0.0]]))

  # Compute topk without id restriction.
  topk_result = signal.vector_compute_topk(3, vector_store)
  expected_result = [('3',), ('1',), ('2',)]
  for (id, _), expected_id in zip(topk_result, expected_result):
    assert id == expected_id

  # Compute top 1.
  topk_result = signal.vector_compute_topk(1, vector_store)
  expected_result = [('3',)]
  for (id, _), expected_id in zip(topk_result, expected_result):
    assert id == expected_id

  # Compute topk with id restriction.
  topk_result = signal.vector_compute_topk(3, vector_store, keys=[('1',), ('2',)])
  expected_result = [('1',), ('2',)]
  for (id, _), expected_id in zip(topk_result, expected_result):
    assert id == expected_id


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
@pytest.mark.parametrize('model_db_cls', ALL_CONCEPT_MODEL_DBS)
def test_concept_model_draft(concept_db_cls: Type[ConceptDB],
                             model_db_cls: Type[ConceptModelDB]) -> None:
  concept_db = concept_db_cls()
  model_db = model_db_cls(concept_db)
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  train_data = [
    ExampleIn(label=False, text='not in concept'),
    ExampleIn(label=True, text='in concept'),
    ExampleIn(label=False, text='a new data point', draft='test_draft'),
  ]
  concept_db.edit(namespace, concept_name, ConceptUpdate(insert=train_data))

  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding')
  draft_signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding='test_embedding', draft='test_draft')

  # Explicitly sync the model with the concept.
  model = ConceptModel(
    namespace='test', concept_name='test_concept', embedding_name='test_embedding')
  model_db.sync(model)

  vector_store = NumpyVectorStore()
  vector_store.add([('1',), ('2',), ('3',)],
                   np.array([[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.1, 0.9, 0.0]]))

  scores = cast(list[float], list(signal.vector_compute([('1',), ('2',), ('3',)], vector_store)))
  assert scores[0] > 0.5
  assert scores[1] > 0.5
  assert scores[2] < 0.5

  # Make sure the draft signal works. It has different values than the original signal.
  vector_store = NumpyVectorStore()
  vector_store.add([('1',), ('2',), ('3',)],
                   np.array([[1.0, 0.0, 0.0], [0.9, 0.1, 0.0], [0.1, 0.2, 0.3]]))

  draft_scores = draft_signal.vector_compute([('1',), ('2',), ('3',)], vector_store)
  assert draft_scores != scores


def test_concept_score_key() -> None:
  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding=TestEmbedding.name)
  assert signal.key() == 'test/test_concept'


@pytest.mark.parametrize('concept_db_cls', ALL_CONCEPT_DBS)
def test_concept_score_compute_signal_key(concept_db_cls: Type[ConceptDB]) -> None:
  concept_db = concept_db_cls()
  namespace = 'test'
  concept_name = 'test_concept'
  concept_db.create(namespace=namespace, name=concept_name, type=SignalInputType.TEXT)

  signal = ConceptScoreSignal(
    namespace='test', concept_name='test_concept', embedding=TestEmbedding.name)
  assert signal.key(is_computed_signal=True) == 'test/test_concept/v0'