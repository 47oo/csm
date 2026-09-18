<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { CONTAINER_OPTIONAL_FIELDS, getContainer } from '../api/containers'
import type { ContainerOptionalField, ContainerRead } from '../api/containers'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useContainerDelete } from '../composables/useContainerDelete'
import ErrorState from '../components/ErrorState.vue'
import ContainerFormDialog from '../components/ContainerFormDialog.vue'

/**
 * 容器详情页（F007 产品页）。
 *
 * - 调用 GET /api/containers/{id}（契约 §4.3，规范路径），展示全部 10 字段
 *   （契约 §2 封闭集合）：R-CONTAINER-004 四字段 null 渲染为「—」（与契约
 *   「返回 null 而非省略」一致）；载体绑定以载体类型 + 载体 ID 表达（AC-22）；
 *   时间为不透明字符串原样展示；name 原样展示（契约 §8）；无状态字段展示 /
 *   编辑（Q-002=B）、无 Cluster 归属字段（R-CONTAINER-002，AC-21/AC-23）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §4.3）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态
 *   （R-QUERY-004 / AC-25）；
 * - 登记表单入口（ContainerFormDialog，POST 契约 §4.1）：含载体类型选择器
 *   （BARE_METAL / VIRTUAL_MACHINE）与载体 ID 输入；登记成功后跳转到新容器的
 *   详情（openDetail）；
 * - 可选字段修改入口（ContainerFormDialog，PATCH 契约 §4.4）：R-CONTAINER-004
 *   四字段可编辑；name / 载体绑定不在 PATCH 可变集内（NQ-1，登记后不可变），
 *   不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/containers/{id}（契约 §4.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按 error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message。
 */
const props = defineProps<{ containerId: number }>()

const emit = defineEmits<{
  back: []
  /** 登记成功后跳转到新容器的详情（携带新 id）。 */
  openDetail: [containerId: number]
}>()

const { data, loading, error, run } = useAsyncQuery(() => getContainer(props.containerId))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useContainerDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

// App 视图切换可能在复用本组件的情况下只改变 containerId（如详情页登记成功后
// 跳转到新容器详情）：重新读取新目标。
watch(
  () => props.containerId,
  () => {
    void run()
  },
)

/** R-CONTAINER-004 可选字段展示标签。 */
const OPTIONAL_LABELS: Record<ContainerOptionalField, string> = {
  image: 'Image',
  cpu: 'CPU',
  memory: '内存',
  owner: '负责人',
}

interface DetailItem {
  key: string
  label: string
  /** 展示值：可选字段 null → 「—」；其余为契约原样值。 */
  value: string
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const container = data.value
  if (container === null) return []
  return [
    { key: 'id', label: 'ID', value: String(container.id) },
    { key: 'carrier_type', label: '载体类型', value: container.carrier_type },
    { key: 'carrier_id', label: '载体 ID', value: String(container.carrier_id) },
    { key: 'name', label: '名称', value: container.name },
    ...CONTAINER_OPTIONAL_FIELDS.map((field) => ({
      key: field,
      label: OPTIONAL_LABELS[field],
      value: container[field] ?? '—',
    })),
    { key: 'created_at', label: '登记时间', value: container.created_at },
    { key: 'updated_at', label: '更新时间', value: container.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-44 / R-QUERY-004）；
 * - 首次请求尚未返回（data 与 error 均为空）按 Loading 处理，避免闪现空内容。
 */
const state = computed<'loading' | 'not-found' | 'error' | 'content'>(() => {
  if (loading.value) return 'loading'
  if (error.value !== null) {
    return error.value.code === 'NOT_FOUND' ? 'not-found' : 'error'
  }
  return data.value !== null ? 'content' : 'loading'
})

/** 登记表单预选载体：当前容器的载体（可改选；存在性仍由服务端裁决）。 */
const presetCarrier = computed(() => {
  const container = data.value
  if (container === null) return null
  return { carrier_type: container.carrier_type, carrier_id: container.carrier_id }
})

function backToList(): void {
  emit('back')
}

/** 二次确认通过后删除当前容器；状态管理与错误渲染见 useContainerDelete。 */
function confirmDelete(): void {
  void requestDelete(props.containerId)
}

// ---- 登记入口（POST）与可选字段修改入口（PATCH） ----

const createDialogVisible = ref(false)
const editDialogVisible = ref(false)

/** 登记成功 → 跳转到新容器的详情（展示服务端返回的登记结果）。 */
function handleCreated(container: ContainerRead): void {
  emit('openDetail', container.id)
}

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="container-detail" :data-state="state">
    <header class="container-detail__header">
      <div class="container-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="container-detail__title">容器详情</h1>
      </div>
      <!-- 登记入口（含载体类型选择器与载体 ID）、可选字段修改入口与删除入口：
           仅内容态出现；name / 载体绑定不可变（契约 §4.4 / NQ-1），编辑表单
           不提供其输入；删除守卫由后端 409 裁决（§21）。 -->
      <div v-if="state === 'content'" class="container-detail__actions">
        <el-button plain data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记容器
        </el-button>
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该容器吗？删除后不可恢复。"
          confirm-button-text="删除"
          cancel-button-text="取消"
          confirm-button-type="danger"
          :width="200"
          @confirm="confirmDelete"
        >
          <template #reference>
            <el-button type="danger" plain :loading="deletingId !== null">删除</el-button>
          </template>
        </el-popconfirm>
      </div>
    </header>

    <section class="container-detail__body">
      <div v-if="state === 'loading'" class="container-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="container-detail__delete-error"
          :data-delete-error-code="deleteErrorView.code"
        >
          <el-alert
            type="error"
            :title="deleteErrorView.title"
            :description="deleteErrorView.description"
            show-icon
            closable
            @close="clearDeleteError"
          />
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item
            v-for="item in detailItems"
            :key="item.key"
            :label="item.label"
          >
            {{ item.value }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>

    <!-- 登记表单（POST）：载体类型选择器 + 载体 ID 输入；预选当前容体的载体。 -->
    <ContainerFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-carrier="presetCarrier"
      @success="handleCreated"
    />
    <!-- 编辑表单（PATCH）：R-CONTAINER-004 四字段；name / 载体绑定不在其中。 -->
    <ContainerFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :container="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.container-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.container-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.container-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.container-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.container-detail__title {
  margin: 0;
  font-size: 20px;
}

.container-detail__body {
  margin-top: 16px;
}

.container-detail__loading {
  padding: 8px 0;
}

.container-detail__delete-error {
  margin-bottom: 16px;
}
</style>
