<template>
  <div class="flex items-center gap-2">
    <button
      @click="refreshRuns"
      class="px-3 py-1.5 text-sm bg-green-700 hover:bg-green-600 rounded border border-green-600 transition-colors flex items-center gap-1"
      title="Refresh run list from API"
    >
      🔄 Refresh
    </button>
    <button
      @click="triggerNewRun"
      class="px-3 py-1.5 text-sm bg-blue-700 hover:bg-blue-600 rounded border border-blue-600 transition-colors flex items-center gap-1 opacity-50 cursor-not-allowed"
      title="Trigger a new pipeline run (coming soon)"
      disabled
    >
      ▶️ New Run
    </button>
  </div>
</template>

<script setup lang="ts">
const router = useRouter();
const route = useRoute();

function refreshRuns() {
  // If on the run list page, reload; otherwise navigate to it
  if (route.path === '/') {
    // Force re-fetch by navigating to the same page
    router.go(0);
  } else {
    router.push('/');
  }
}

function triggerNewRun() {
  // Reserved: will call POST /api/v1/runs/trigger when implemented
  // For now, this button is disabled (opacity-50 + cursor-not-allowed)
}
</script>
