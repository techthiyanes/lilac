<script context="module" lang="ts">
  import {writable} from 'svelte/store';

  export type ClusterOptions = {
    namespace: string;
    datasetName: string;
    input: Path;
    output_path?: Path;
    remote?: boolean;
    overwrite?: boolean;
  };

  export function openClusterModal(options: ClusterOptions) {
    store.set(options);
  }

  let store = writable<ClusterOptions | null>(null);
</script>

<script lang="ts">
  import {clusterMutation} from '$lib/queries/datasetQueries';
  import {queryAuthInfo} from '$lib/queries/serverQueries';
  import type {Path} from '$lilac';
  import {
    ComposedModal,
    ModalBody,
    ModalFooter,
    ModalHeader,
    Toggle
  } from 'carbon-components-svelte';
  import FieldSelect from './commands/selectors/FieldSelect.svelte';
  import {hoverTooltip} from './common/HoverTooltip';
  $: options = $store;

  const clusterQuery = clusterMutation();
  const authInfo = queryAuthInfo();

  $: canComputeRemotely = $authInfo.data?.access.dataset.execute_remotely;

  function close() {
    store.set(null);
  }
  function submit() {
    if (!options) return;
    $clusterQuery.mutate([
      options.namespace,
      options.datasetName,
      {
        input: options.input,
        remote: options.remote,
        output_path: options.output_path,
        overwrite: options.overwrite
      }
    ]);
    close();
  }
</script>

{#if options}
  <ComposedModal open on:submit={submit} on:close={close}>
    <ModalHeader title="Compute clusters" />
    <ModalBody hasForm>
      <div class="max-w-2xl">
        <FieldSelect
          filter={f => f.dtype?.type === 'string'}
          defaultPath={options.input}
          bind:path={options.input}
          labelText="Field"
        />
      </div>
      <div class="mt-8">
        <div class="label text-s mb-2 font-medium text-gray-700">Remote</div>
        <div
          class="w-20"
          use:hoverTooltip={{
            text: !canComputeRemotely ? 'Sign up for Lilac Garden to enable this feature.' : ''
          }}
        >
          <Toggle
            disabled={!canComputeRemotely}
            labelA={'False'}
            labelB={'True'}
            bind:toggled={options.remote}
            hideLabel
          />
        </div>
        <div class="text-sm text-gray-600">Accelerated computation on Lilac Garden.</div>
      </div>
      <div class="mt-8">
        <div class="label text-s mb-2 font-medium text-gray-700">Overwrite</div>
        <Toggle labelA={'False'} labelB={'True'} bind:toggled={options.overwrite} hideLabel />
      </div>
    </ModalBody>
    <ModalFooter
      primaryButtonText="Cluster"
      secondaryButtonText="Cancel"
      on:click:button--secondary={close}
    />
  </ComposedModal>
{/if}
