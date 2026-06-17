<template>
  <div>
    <!-- Breadcrumb -->
    <div class="flex items-center gap-2 text-sm text-gray-400 mb-6">
      <NuxtLink to="/" class="hover:text-blue-400 transition-colors">Runs</NuxtLink>
      <span>/</span>
      <NuxtLink :to="`/runs/${runId}`" class="hover:text-blue-400 transition-colors font-mono">{{ runId }}</NuxtLink>
      <span>/</span>
      <span class="text-gray-200">Stories</span>
    </div>

    <!-- Controls -->
    <div class="flex items-center gap-3 mb-6">
      <h1 class="text-xl font-bold">Stories</h1>
      <select
        v-model="filterTheme"
        @change="fetchStories"
        class="bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200"
      >
        <option value="">All Sections</option>
        <option value="sony">Sony / PlayStation</option>
        <option value="nintendo">Nintendo</option>
        <option value="microsoft">Microsoft / Xbox</option>
        <option value="pc">PC Gaming</option>
        <option value="supplemental">Supplemental</option>
      </select>
      <span v-if="!loading" class="text-sm text-gray-500">{{ stories.length }} stories</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12 text-gray-400">
      <div class="animate-spin inline-block w-6 h-6 border-2 border-gray-600 border-t-blue-500 rounded-full mb-2" />
      <p>Loading stories...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="bg-red-900/30 border border-red-800 rounded-lg p-4">
      <p class="text-red-400">{{ error }}</p>
    </div>

    <!-- Empty -->
    <div v-else-if="stories.length === 0" class="text-center py-12 text-gray-400">
      <p>No stories found for this run.</p>
    </div>

    <!-- Story cards -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div
        v-for="story in stories"
        :key="story.story_id"
        class="bg-gray-900 border border-gray-800 hover:border-gray-700 rounded-lg p-4 transition-colors"
      >
        <div class="flex items-start justify-between mb-2">
          <span class="text-xs px-2 py-0.5 bg-gray-800 text-gray-400 rounded font-mono">
            {{ story.theme_section }}
          </span>
          <span class="text-xs px-2 py-0.5 rounded font-medium" :class="selectionBadge(story.selection_status)">
            {{ story.selection_status }}
          </span>
        </div>
        <h3 class="font-medium text-gray-200 mb-2">{{ story.title }}</h3>
        <div class="flex items-center justify-between text-sm">
          <span class="text-gray-500">Score: {{ (story.story_score * 100).toFixed(0) }}%</span>
          <span class="text-gray-500 font-mono text-xs">{{ story.story_id }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface Story {
  story_id: string;
  title: string;
  theme_section: string;
  status: string;
  selection_status: string;
  story_score: number;
}

const route = useRoute();
const runId = computed(() => route.params.id as string);

const { settings, getApiBase } = useSettings();
const stories = ref<Story[]>([]);
const loading = ref(true);
const error = ref('');
const filterTheme = ref(settings.value.themeSection || '');

async function fetchStories() {
  loading.value = true;
  error.value = '';
  try {
    const apiBase = getApiBase();
    const params = new URLSearchParams({ limit: '100' });
    if (filterTheme.value) params.set('theme_section', filterTheme.value);
    const response = await $fetch<{ rows: Story[] }>(
      `${apiBase}/api/v1/runs/${runId.value}/stories?${params}`
    );
    stories.value = response.rows || [];
  } catch (e: any) {
    error.value = e.message || 'Failed to fetch stories.';
  } finally {
    loading.value = false;
  }
}

function selectionBadge(status: string): string {
  switch (status) {
    case 'selected': return 'bg-green-900/50 text-green-400';
    case 'backup': return 'bg-yellow-900/50 text-yellow-400';
    case 'rejected': return 'bg-red-900/50 text-red-400';
    default: return 'bg-gray-800 text-gray-400';
  }
}

onMounted(fetchStories);
</script>
