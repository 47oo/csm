<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { getFoundationError, listFoundationClusters } from '../api/foundation'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import ListStates from '../components/ListStates.vue'

/**
 * F012 开发自检页（非产品页面）。
 *
 * 仅在 dev 构建下由 App.vue 渲染（生产构建渲染占位说明）。
 * 调用非产品端点 /_foundation/* 验证前端基座的 Loading / Empty / Error 三态：
 * - 列表三态：GET /_foundation/clusters（契约 §4.2，含 Empty：200 + items 为空）；
 * - Error 态：GET /_foundation/error（契约 §4.6，确定性 500 INTERNAL_ERROR）。
 */
const {
  data: clusterData,
  loading: listLoading,
  error: listError,
  run: runList,
} = useAsyncQuery(listFoundationClusters)

const clusters = computed(() => clusterData.value?.items ?? [])
const listEmpty = computed(
  () => clusterData.value !== null && clusterData.value.items.length === 0,
)

const {
  loading: probeLoading,
  error: probeError,
  run: runErrorProbe,
} = useAsyncQuery(getFoundationError)

onMounted(() => {
  void runList()
})

function refreshList(): void {
  void runList()
}

function triggerErrorProbe(): void {
  void runErrorProbe()
}
</script>

<template>
  <main class="self-check">
    <header class="self-check__header">
      <h1 class="self-check__title">F012 前端基座自检</h1>
      <el-tag type="warning" effect="dark">DEV ONLY</el-tag>
    </header>

    <el-alert
      class="self-check__notice"
      type="warning"
      :closable="false"
      show-icon
      title="本页面是非产品自检页，不是产品功能"
      description="页面调用的是非产品端点 /_foundation/*（仅 dev/test 环境由后端挂载，生产环境不可达），仅用于验证前端基座的 Loading / Empty / Error 三态渲染。clusters 在该端点仅作基座验证载体，不含领域规则。产品页面自 F001 起交付。"
    />

    <el-card class="self-check__card" shadow="never">
      <template #header>
        <div class="self-check__card-header">
          <span>
            <span class="self-check__endpoint">GET /_foundation/clusters</span>
            <span class="self-check__hint">列表三态：Loading → Empty / 数据</span>
          </span>
          <el-button :loading="listLoading" @click="refreshList">刷新</el-button>
        </div>
      </template>

      <ListStates
        :loading="listLoading"
        :error="listError"
        :empty="listEmpty"
        empty-description="暂无数据（Empty 态：接口返回 200，items 为空数组）"
      >
        <el-table :data="clusters">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="created_at" label="created_at" min-width="200" />
          <el-table-column prop="updated_at" label="updated_at" min-width="200" />
        </el-table>
      </ListStates>
    </el-card>

    <el-card class="self-check__card" shadow="never">
      <template #header>
        <div class="self-check__card-header">
          <span>
            <span class="self-check__endpoint">GET /_foundation/error</span>
            <span class="self-check__hint">确定性 500 INTERNAL_ERROR，驱动 Error 态</span>
          </span>
          <el-button
            type="danger"
            plain
            :loading="probeLoading"
            @click="triggerErrorProbe"
          >
            触发错误请求
          </el-button>
        </div>
      </template>

      <ListStates :loading="probeLoading" :error="probeError" :empty="false">
        <p class="self-check__idle">
          尚未触发请求。点击右上角「触发错误请求」按钮：接口将返回确定性
          500 INTERNAL_ERROR，此处将按 error.code 渲染 Error 态。
        </p>
      </ListStates>
    </el-card>

    <footer class="self-check__footer">
      状态判定优先级：Loading &gt; Error &gt; Empty &gt; 内容；Error 态按
      error.code 分支渲染（不解析 error.message）。
    </footer>
  </main>
</template>

<style scoped>
.self-check {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.self-check__header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.self-check__title {
  margin: 0;
  font-size: 20px;
}

.self-check__notice {
  margin-top: 16px;
}

.self-check__card {
  margin-top: 16px;
}

.self-check__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.self-check__endpoint {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600;
}

.self-check__hint {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.self-check__idle {
  margin: 12px 0;
  color: #909399;
}

.self-check__footer {
  margin-top: 24px;
  color: #909399;
  font-size: 12px;
}
</style>
