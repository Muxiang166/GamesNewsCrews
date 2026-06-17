<template>
  <div class="min-h-screen bg-gray-950 text-gray-100">
    <header class="border-b border-gray-800 bg-gray-900 px-6 py-3">
      <div class="flex items-center justify-between max-w-7xl mx-auto">
        <NuxtLink to="/" class="text-xl font-bold text-white hover:text-blue-400 transition-colors">
          🎮 Games News Workbench
        </NuxtLink>
        <div class="flex items-center gap-4">
          <ActionButtons />
          <ParamSettings />
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-6">
      <NuxtPage />
    </main>

    <footer class="border-t border-gray-800 bg-gray-900 px-6 py-3 mt-auto">
      <div class="max-w-7xl mx-auto text-sm text-gray-500">
        Games News Crew — Internal Workbench v0.1.0
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
// App root — provides layout shell with header, main content area, and footer.
// ParamSettings and ActionButtons are always visible in the header.
</script>
