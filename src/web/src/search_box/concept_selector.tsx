import * as React from 'react';
import {useParams} from 'react-router-dom';
import {ConceptInfo} from '../../fastapi_client';
import {useGetConceptsQuery} from '../store/api_concept';
import {renderQuery} from '../utils';
import {Item} from './item_selector';

export function ConceptSelector({onSelect}: {onSelect: (concept: ConceptInfo) => void}) {
  const {namespace, datasetName} = useParams<{namespace: string; datasetName: string}>();
  if (namespace == null || datasetName == null) {
    throw new Error('Invalid route');
  }
  const query = useGetConceptsQuery();
  return renderQuery(query, (concepts) => {
    return (
      <>
        {concepts.map((concept) => {
          return (
            <Item key={concept.name} onSelect={() => onSelect(concept)}>
              <div className="flex w-full justify-between">
                <div className="truncate">
                  {concept.namespace}/{concept.name}
                </div>
                <div className="truncate">{/* Future description here */}</div>
              </div>
            </Item>
          );
        })}
      </>
    );
  });
}