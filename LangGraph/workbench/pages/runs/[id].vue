<template>
  <div>
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-gray-400 mb-6">
      <NuxtLink to="/" class="hover:text-blue-400 transition-colors">← Runs</NuxtLink>
      <span>/</span>
      <span class="text-gray-200 font-mono">{{ runId }}</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-gray-400">
      <div class="animate-spin inline-block w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full mb-2" />
      <p>Loading run summary...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bg-red-900/30 border border-red-800 rounded-lg p-4">
      <p class="text-red-400">{{ error }}</p>
    </div>

    <!-- Summary -->
    <template v-else-if="summary">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <!-- Run Info -->
        <div class="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 class="text-sm font-semibold text-gray-300 mb-3">Run Info</h2>
          <dl class="space-y-2 text-sm">
            <div class="flex justify-between">
              <dt class="text-gray-400">Status</dt>
              <dd>
                <span :class="statusBadge(summary.run?.status)" class="px-2 py-0.5 rounded-full text-xs font-medium">
                  {{ summary.run?.status || 'unknown' }}
                </span>
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-400">Output</dt>
              <dd class="text-gray-200 font-mono text-xs">{{ summary.run?.output_dir || '—' }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-400">Started</dt>
              <dd class="text-gray-200">{{ formatTime(summary.run?.started_at) }}</dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-400">Ended</dt>
              <dd class="text-gray-200">{{ formatTime(summary.run?.ended_at) }}</dd>
            </div>
          </dl>
        </div>

        <!-- Table Counts -->
        <div class="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 class="text-sm font-semibold text-gray-300 mb-3">Table Counts</h2>
          <div class="grid grid-cols-2 gap-2 text-sm">
            <div
              v-for="(count, table) in summary.table_counts"
              :key="table"
              class="flex justify-between bg-gray-800/50 rounded px-2 py-1"
            >
              <span class="text-gray-400">{{ table }}</span>
              <span class="text-gray-200 font-mono">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- Notifications -->
        <div class="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h2 class="text-sm font-semibold text-gray-300 mb-3">
            Notifications
            <span v-if="summary.open_notifications > 0" class="ml-1 px-1.5 py-0.5 bg-yellow-900/50 text-yellow-400 rounded text-xs">
              {{ summary.open_notifications }} open
            </span>
          </h2>
          <NuxtLink
            :to="`/runs/${runId}/stories`"
            class="block text-sm text-blue-400 hover:text-blue-300 transition-colors mb-1"
          >
            📋 Stories →
          </NuxtLink>
          <NuxtLink
            :to="`/runs/${runId}/artifacts`"
            class="block text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            📁 Artifacts →
          </NuxtLink>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
const route = useRoute();
const runId = computed(() => route.params.id as string);

const { settings, getApiBase } = useSettings();
const summary = ref<any>(null);
const loading = ref(true);
const error = ref('');

async function fetchSummary() {
  loading.value = true;
  error.value = '';
  try {
    const apiBase = getApiBase();
    const response = await $fetch<any>(`${apiBase}/api/v1/runs/${runId.value}`);
    summary.value = response.summary || response;
  } catch (e: any) {
    error.value = e.message || 'Failed to fetch run summary.';
  } finally {
    loading.value = false;
  }
}

function statusBadge(status: string): string {
  switch (status) {
    case 'completed': return 'bg-green-900/50 text-green-400';
    case 'running': return 'bg-blue-900/50 text-blue-400';
    case 'failed': return 'bg-red-900/50 text-red-400';
    default: return 'bg-gray-800 text-gray-400';
  }
}

function formatTime(iso: string): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN');
  } catch {
    return iso;
  }
}

onMounted(fetchSummary);
</script>
