<template>
  <div class="relative">
    <button
      @click="open = !open"
      class="px-3 py-1.5 text-sm bg-gray-800 hover:bg-gray-700 rounded border border-gray-700 transition-colors"
      title="Settings"
    >
      ⚙️ Settings
    </button>

    <!-- Settings panel dropdown -->
    <div
      v-if="open"
      class="absolute right-0 top-full mt-2 w-80 bg-gray-900 border border-gray-700 rounded-lg shadow-xl p-4 z-50"
    >
      <h3 class="text-sm font-semibold text-gray-300 mb-3">Workbench Settings</h3>

      <div class="space-y-3">
        <div>
          <label class="block text-xs text-gray-400 mb-1">FastAPI Base URL</label>
          <input
            v-model="settings.apiBaseUrl"
            type="text"
            class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
            placeholder="http://localhost:8000"
          />
        </div>

        <div>
          <label class="block text-xs text-gray-400 mb-1">DB Path (for CLI use)</label>
          <input
            v-model="settings.dbPath"
            type="text"
            class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
            placeholder="outputs/langgraph/mirror/games_news.db"
          />
        </div>

        <div>
          <label class="block text-xs text-gray-400 mb-1">Default Theme Section</label>
          <select
            v-model="settings.themeSection"
            class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
          >
            <option value="">All Sections</option>
            <option value="sony">Sony / PlayStation</option>
            <option value="nintendo">Nintendo</option>
            <option value="microsoft">Microsoft / Xbox</option>
            <option value="pc">PC Gaming</option>
            <option value="supplemental">Supplemental</option>
          </select>
        </div>

        <div>
          <label class="block text-xs text-gray-400 mb-1">Page Size</label>
          <input
            v-model.number="settings.limit"
            type="number"
            min="1"
            max="500"
            class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200"
          />
        </div>
      </div>

      <div class="flex gap-2 mt-4">
        <button
          @click="applySettings"
          class="flex-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors"
        >
          Apply
        </button>
        <button
          @click="resetDefaults"
          class="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm transition-colors"
        >
          Reset
        </button>
      </div>
    </div>

    <!-- Backdrop to close -->
    <div v-if="open" class="fixed inset-0 z-40" @click="open = false" />
  </div>
</template>

<script setup lang="ts">
const { settings, save, reset } = useSettings();
const open = ref(false);

function applySettings() {
  save();
  open.value = false;
}

function resetDefaults() {
  reset();
  open.value = false;
}
</script>
