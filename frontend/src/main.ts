import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import App from './App.vue'
import { createAppRouter } from './router'
import { installApiHandlers } from './api/handlers'

const app = createApp(App)
const pinia = createPinia()
const router = createAppRouter()

app.use(pinia)
app.use(router)
app.use(ElementPlus, { locale: zhCn })

// 装配 axios 全局 401/403 处理器（需在 pinia 激活后）
installApiHandlers(router)

app.mount('#app')
