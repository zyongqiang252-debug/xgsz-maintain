import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    // 单包过大会让首屏一直在解析 JS；按库拆成多个 vendor chunk，浏览器可并行加载+长期缓存
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@element-plus/icons-vue')) return 'vendor-element-icons'
          if (id.includes('element-plus')) return 'vendor-element'
          if (id.includes('vue-router') || id.includes('@vue/') || /node_modules[\\/]vue[\\/]/.test(id)) return 'vendor-vue'
          if (id.includes('axios')) return 'vendor-axios'
          if (id.includes('dayjs')) return 'vendor-dayjs'
          if (id.includes('qrcode.vue')) return 'vendor-qrcode'
          return 'vendor'
        }
      }
    }
  },
  server: {
    host: '127.0.0.1',
    port: 4173,   // Hyper-V/WSL2 保留区间每次重启随机变动（曾占 5173/3000），4173 当前安全；长期方案见 start_all.ps1
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: true
      },
      '/dingtalk': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: true
      }
    }
  }
})
