// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2026-06-17',
  devtools: { enabled: true },
  modules: ['@nuxtjs/tailwindcss'],
  devServer: {
    port: 5173,
  },
  app: {
    head: {
      title: 'Games News Workbench',
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      ],
    },
  },
  runtimeConfig: {
    public: {
      // Default FastAPI base URL — override with NUXT_PUBLIC_API_BASE_URL env var
      apiBaseUrl: process.env.NUXT_PUBLIC_API_BASE_URL || 'http://localhost:8000',
    },
  },
  nitro: {
    // We do NOT use Nitro server routes — all API calls go to FastAPI directly
    // This keeps the frontend purely a presentation layer
  },
});
