<template>
  <div>
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-gray-400 mb-6">
      <NuxtLink to="/" class="hover:text-blue-400 transition-colors">Runs</NuxtLink>
      <span>/</span>
      <NuxtLink :to="`/runs/${runId}`" class="hover:text-blue-400 transition-colors font-mono">{{ runId }}</NuxtLink>
      <span>/</span>
      <span class="text-gray-200">Artifacts</span>
    </div>

    <h1 class="text-xl font-bold mb-6">Artifact Stage Browser</h1>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-gray-400">
      <div class="animate-spin inline-block w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full mb-2" />
      <p>Loading artifacts...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bg-red-900/30 border border-red-800 rounded-lg p-4">
      <p class="text-red-400">{{ error }}</p>
    </div>

    <!-- Browser layout -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Left: Stage tree -->
      <div class="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h2 class="text-sm font-semibold text-gray-300 mb-3">Stages</h2>

        <div
          v-for="(items, stage) in stages"
          :key="stage"
          class="mb-3"
        >
          <button
            @click="toggleStage(stage)"
            class="flex items-center gap-2 w-full text-left py-1.5 hover:text-white transition-colors"
            :class="expandedStage === stage ? 'text-blue-400' : 'text-gray-400'"
          >
            <span class="text-xs">{{ expandedStage === stage ? '▼' : '▶' }}</span>
            <span class="text-sm font-medium">{{ stage }}</span>
            <span class="text-xs text-gray-600 ml-auto">{{ items.length }}</span>
          </button>

          <!-- Artifact files in stage -->
          <div v-if="expandedStage === stage" class="ml-4 mt-1 space-y-1">
            <button
              v-for="artifact in items"
              :key="artifact.artifact_key"
              @click="selectArtifact(artifact)"
              class="block w-full text-left px-2 py-1 rounded text-xs transition-colors"
              :class="selectedArtifact?.artifact_key === artifact.artifact_key
                ? 'bg-blue-900/40 text-blue-300'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'"
            >
              📄 {{ artifact.artifact_key }}
            </button>
          </div>
        </div>

        <!-- No stages -->
        <div v-if="Object.keys(stages).length === 0" class="text-sm text-gray-500 text-center py-4">
          No artifacts indexed for this run.
        </div>
      </div>

      <!-- Right: Content preview -->
      <div class="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-lg p-4">
        <template v-if="selectedArtifact">
          <div class="flex items-center justify-between mb-3">
            <div>
              <h3 class="text-sm font-semibold text-gray-200">
                {{ selectedArtifact.artifact_key }}
              </h3>
              <p class="text-xs text-gray-500 mt-0.5">
                Stage: {{ selectedArtifact.stage }} &middot;
                Size: {{ formatSize(selectedArtifact.size_bytes) }} &middot;
                Exists: {{ selectedArtifact.exists_flag ? '✅' : '❌' }}
              </p>
            </div>
            <span
              v-if="previewError"
              class="text-xs text-red-400"
            >
              {{ previewError }}
            </span>
          </div>

          <!-- Loading preview -->
          <div v-if="previewLoading" class="text-center py-12 text-gray-400">
            <div class="animate-spin inline-block w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full mb-2" />
            <p class="text-sm">Loading content...</p>
          </div>

          <!-- Preview content -->
          <div v-else-if="previewContent" class="relative">
            <!-- JSON: syntax highlighted -->
            <pre
              v-if="isJson(selectedArtifact.artifact_key)"
              class="bg-gray-950 border border-gray-800 rounded p-4 text-xs text-green-400 overflow-auto max-h-[60vh]"
            ><code>{{ formatJson(previewContent) }}</code></pre>

            <!-- Markdown/Text -->
            <pre
              v-else
              class="bg-gray-950 border border-gray-800 rounded p-4 text-sm text-gray-300 overflow-auto max-h-[60vh] whitespace-pre-wrap"
            ><code>{{ previewContent }}</code></pre>
          </div>

          <!-- No content / file missing -->
          <div v-else-if="!previewLoading && !previewError" class="text-center py-12 text-gray-500">
            <p>File not found on disk.</p>
            <p class="text-xs mt-1">{{ selectedArtifact.path }}</p>
          </div>
        </template>

        <!-- No artifact selected -->
        <div v-else class="text-center py-16 text-gray-500">
          <p class="text-lg mb-1">← Select an artifact from the stage tree</p>
          <p class="text-sm">Artifact content will appear here.</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Artifact {
  artifact_key: string;
  path: string;
  stage: string;
  exists_flag: number;
  size_bytes: number;
  sha256: string;
}

const route = useRoute();
const runId = computed(() => route.params.id as string);

const { settings, getApiBase } = useSettings();

const stages = ref<Record<string, Artifact[]>>({});
const loading = ref(true);
const error = ref('');

const expandedStage = ref<string | null>(null);
const selectedArtifact = ref<Artifact | null>(null);
const previewContent = ref('');
const previewLoading = ref(false);
const previewError = ref('');

async function fetchArtifacts() {
  loading.value = true;
  error.value = '';
  try {
    const apiBase = getApiBase();
    const response = await $fetch<{ rows: Artifact[] }>(
      `${apiBase}/api/v1/runs/${runId.value}/artifacts?limit=500`
    );
    const artifacts = response.rows || [];

    // Group by stage
    const grouped: Record<string, Artifact[]> = {};
    for (const a of artifacts) {
      const stage = a.stage || 'unknown';
      if (!grouped[stage]) grouped[stage] = [];
      grouped[stage].push(a);
    }
    stages.value = grouped;
  } catch (e: any) {
    error.value = e.message || 'Failed to fetch artifacts.';
  } finally {
    loading.value = false;
  }
}

function toggleStage(stage: string) {
  expandedStage.value = expandedStage.value === stage ? null : stage;
}

async function selectArtifact(artifact: Artifact) {
  selectedArtifact.value = artifact;
  previewLoading.value = true;
  previewError.value = '';
  previewContent.value = '';

  try {
    const apiBase = getApiBase();
    const response = await $fetch<string>(
      `${apiBase}/api/v1/runs/${runId.value}/artifacts/${artifact.artifact_key}`,
      { responseType: 'text' }
    );
    previewContent.value = response;
  } catch (e: any) {
    previewError.value = e.data?.detail || e.message || 'Failed to load content.';
  } finally {
    previewLoading.value = false;
  }
}

function isJson(key: string): boolean {
  return key.endsWith('.json') || key.includes('.json') || key.includes('_json');
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

onMounted(fetchArtifacts);
</script>
