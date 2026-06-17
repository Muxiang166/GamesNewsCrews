<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold">Run List</h1>
      <span v-if="settings" class="text-sm text-gray-400">
        API: {{ settings.apiBaseUrl }}
      </span>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="text-center py-12 text-gray-400">
      <div class="animate-spin inline-block w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full mb-2" />
      <p>Loading runs...</p>
    </div>

    <!-- Error state -->
    <div v-else-if="error" class="bg-red-900/30 border border-red-800 rounded-lg p-4 mb-4">
      <p class="text-red-400 font-medium">Failed to load runs</p>
      <p class="text-red-300 text-sm mt-1">{{ error }}</p>
      <button @click="fetchRuns" class="mt-2 px-3 py-1 bg-red-800 hover:bg-red-700 rounded text-sm transition-colors">
        Retry
      </button>
    </div>

    <!-- Empty state -->
    <div v-else-if="runs.length === 0" class="text-center py-12 text-gray-400">
      <p class="text-lg">No runs found</p>
      <p class="text-sm mt-1">Run the pipeline first to generate data, or check your API connection.</p>
    </div>

    <!-- Run table -->
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-gray-800 text-left text-gray-400">
            <th class="py-3 px-4 font-medium">Run ID</th>
            <th class="py-3 px-4 font-medium">Status</th>
            <th class="py-3 px-4 font-medium">Started</th>
            <th class="py-3 px-4 font-medium">Ended</th>
            <th class="py-3 px-4 font-medium">Notifications</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="run in runs"
            :key="run.run_id"
            @click="navigateTo(`/runs/${run.run_id}`)"
            class="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors"
          >
            <td class="py-3 px-4 font-mono text-blue-400">{{ run.run_id }}</td>
            <td class="py-3 px-4">
              <span
                :class="statusBadge(run.status)"
                class="px-2 py-0.5 rounded-full text-xs font-medium"
              >
                {{ run.status }}
              </span>
            </td>
            <td class="py-3 px-4 text-gray-400">{{ formatTime(run.started_at) }}</td>
            <td class="py-3 px-4 text-gray-400">{{ formatTime(run.ended_at) }}</td>
            <td class="py-3 px-4">
              <span
                v-if="run.open_notification_count > 0"
                class="px-2 py-0.5 bg-yellow-900/50 text-yellow-400 rounded-full text-xs font-medium"
              >
                {{ run.open_notification_count }} open
              </span>
              <span v-else class="text-gray-500">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Run {
  run_id: string;
  status: string;
  started_at: string;
  ended_at: string;
  open_notification_count: number;
}

const { settings, getApiBase } = useSettings();
const runs = ref<Run[]>([]);
const loading = ref(true);
const error = ref('');

async function fetchRuns() {
  loading.value = true;
  error.value = '';
  try {
    const apiBase = getApiBase();
    const limit = settings.value.limit || 20;
    const response = await $fetch<{ rows: Run[] }>(`${apiBase}/api/v1/runs?limit=${limit}`);
    runs.value = response.rows || [];
  } catch (e: any) {
    error.value = e.message || 'Unknown error fetching runs.';
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
    const d = new Date(iso);
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

onMounted(fetchRuns);
</script>
