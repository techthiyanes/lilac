<script lang="ts">
  import {querySelectRowsSchema, querySettings} from '$lib/queries/datasetQueries';
  import {getDatasetViewContext, getSelectRowsSchemaOptions} from '$lib/stores/datasetViewStore';
  import {getHighlightedFields, getMediaFields} from '$lib/view_utils';
  import {L, ROWID, type SelectRowsResponse} from '$lilac';
  import FilterPanel from './FilterPanel.svelte';
  import PrefetchRowItem from './PrefetchRowItem.svelte';
  import RowItem from './RowItem.svelte';
  import SingleItemSelectRows from './SingleItemSelectRows.svelte';

  // True when the settings modal is open. Used to disable keyboard shortcuts.
  export let settingsOpen = false;

  const store = getDatasetViewContext();
  const DEFAULT_LIMIT_SELECT_ROW_IDS = 5;

  let limit = DEFAULT_LIMIT_SELECT_ROW_IDS;
  let rowsResponse: SelectRowsResponse | undefined;
  let nextRowResponse: SelectRowsResponse | undefined;

  $: selectRowsSchema = querySelectRowsSchema(
    $store.namespace,
    $store.datasetName,
    getSelectRowsSchemaOptions($store)
  );

  $: rows = rowsResponse?.rows;

  $: firstRowId = rows && rows.length > 0 ? L.value(rows[0][ROWID], 'string') : undefined;
  $: rowId = $store.rowId || firstRowId;

  // Find the index if the row id is known.
  $: index =
    rowId != null && rows != null
      ? rows.findIndex(row => L.value(row[ROWID], 'string') === rowId)
      : undefined;

  // Compute the next row id for the next button.
  let nextRowId: string;
  $: {
    if (index != null && rows != null) {
      let nextIndex = index + 1;
      if (nextIndex >= rows.length) {
        nextIndex = 0;
      }
      nextRowId = L.value(rows[nextIndex][ROWID], 'string') as string;
    }
  }

  // Double the limit of select rows if the row id was not found.
  $: rowIdWasNotFound = rows != null && index != null && (index === -1 || index >= rows.length);
  $: limit =
    rowIdWasNotFound && rowsResponse?.total_num_rows
      ? Math.min(limit * 2, rowsResponse.total_num_rows)
      : limit;

  $: settings = querySettings($store.namespace, $store.datasetName);
  $: mediaFields = $settings.data
    ? getMediaFields($selectRowsSchema?.data?.schema, $settings.data)
    : [];
  $: highlightedFields = getHighlightedFields($store.query, $selectRowsSchema?.data);

  function updateSequentialRowId(direction: 'previous' | 'next') {
    if (index == null) {
      return;
    }
    if (rows == null) {
      return;
    }
    let newIndex = direction === 'next' ? index + 1 : Math.max(index - 1, 0);
    let newRowId: string | null;
    if (newIndex >= rows.length) {
      newRowId = L.value(nextRowResponse?.rows?.[0]?.[ROWID], 'string');
    } else {
      newRowId = L.value(rows[newIndex]?.[ROWID], 'string');
    }
    if (newRowId) {
      store.setRowId(newRowId);
    }
  }

  function onKeyDown(key: KeyboardEvent) {
    if (key.code === 'ArrowLeft') {
      updateSequentialRowId('previous');
    } else if (key.code === 'ArrowRight') {
      updateSequentialRowId('next');
    }
  }
</script>

<FilterPanel numRowsInQuery={rowsResponse?.total_num_rows} />

<SingleItemSelectRows {limit} bind:rowsResponse />
{#if rows != null}
  <SingleItemSelectRows limit={1} offset={rows.length} bind:rowsResponse={nextRowResponse} />
{/if}

<!-- Prefetch the previous and next item to minimize perceived lag. -->
{#if index != null && rows != null}
  {#if index > 0}
    <PrefetchRowItem rowId={L.value(rows[index - 1]?.[ROWID], 'string')} />
  {/if}

  {#if index < rows.length - 1}
    <PrefetchRowItem rowId={L.value(rows[index + 1]?.[ROWID], 'string')} />
  {/if}
{/if}

<div class="flex h-full w-full flex-col overflow-y-scroll pb-32">
  <RowItem
    {index}
    totalNumRows={rowsResponse?.total_num_rows}
    {rowId}
    {nextRowId}
    {mediaFields}
    {highlightedFields}
    {updateSequentialRowId}
    {settingsOpen}
  />
</div>
<svelte:window on:keydown={onKeyDown} />
