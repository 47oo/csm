<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { SERVICE_OPTIONAL_FIELDS, getService } from '../api/services'
import type { ServiceOptionalField, ServiceRead } from '../api/services'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useServiceDelete } from '../composables/useServiceDelete'
import ErrorState from '../components/ErrorState.vue'
import ServiceFormDialog from '../components/ServiceFormDialog.vue'

/**
 * Service 详情页（F008 产品页）。
 *
 * - 调用 GET /api/services/{id}（契约 §4.3，规范路径），展示全部 11 字段
 *   （契约 §2 封闭集合）：6 个可选字段 null 渲染为「—」（与契约「返回
 *   null 而非省略」一致）；载体绑定以 carriers 列表展示（每项 = 载体类型 +
 *   载体 ID，按契约 §2 稳定顺序原样展示，AC-16：全部绑定、无遗漏）；
 *   时间为不透明字符串原样展示；name 原样展示（契约 §8）；无状态字段
 *   展示 / 编辑（Q-002=B，AC-28）、无 Cluster 归属字段（R-SVC-004/006，
 *   AC-20/21：归属仅由载体推导，本页不推导、不展示）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §4.3）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同
 *   状态（R-QUERY-004 / AC-30）；
 * - 登记表单入口（ServiceFormDialog，POST 契约 §4.1）：多载体选择（三种
 *   载体类型 + 载体 ID，至少一项）；登记成功后跳转到新服务的详情
 *   （openDetail）；
 * - 可选字段修改入口（ServiceFormDialog，PATCH 契约 §4.4）：6 个可选字段
 *   可编辑；name 与载体绑定不在 PATCH 可变集内（NQ-01/NQ-02，登记后不可变），
 *   不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/services/{id}（契约 §4.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按 error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message。
 */
const props = defineProps<{ serviceId: number }>()

const emit = defineEmits<{
  back: []
  /** 登记成功后跳转到新服务的详情（携带新 id）。 */
  openDetail: [serviceId: number]
}>()

const { data, loading, error, run } = useAsyncQuery(() => getService(props.serviceId))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useServiceDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

// App 视图切换可能在复用本组件的情况下只改变 serviceId（如详情页登记成功后
// 跳转到新服务详情）：重新读取新目标。
watch(
  () => props.serviceId,
  () => {
    void run()
  },
)

/** 6 个可选字段展示标签。 */
const OPTIONAL_LABELS: Record<ServiceOptionalField, string> = {
  service_type: '服务类型',
  url: 'URL',
  port: '端口',
  protocol: '协议',
  owner: '负责人',
  description: '描述',
}

interface DetailItem {
  key: string
  label: string
  /** 展示值：可选字段 null → 「—」；其余为契约原样值。 */
  value: string
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const service = data.value
  if (service === null) return []
  return [
    { key: 'id', label: 'ID', value: String(service.id) },
    { key: 'name', label: '名称', value: service.name },
    ...SERVICE_OPTIONAL_FIELDS.map((field) => ({
      key: field,
      label: OPTIONAL_LABELS[field],
      value: service[field] ?? '—',
    })),
    { key: 'created_at', label: '登记时间', value: service.created_at },
    { key: 'updated_at', label: '更新时间', value: service.updated_at },
  ]
})

/** 载体绑定列表（契约 §2 稳定顺序原样展示；AC-16：全部绑定，无截断）。 */
const carriers = computed(() => data.value?.carriers ?? [])

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-54 / R-QUERY-004）；
 * - 首次请求尚未返回（data 与 error 均为空）按 Loading 处理，避免闪现空内容。
 */
const state = computed<'loading' | 'not-found' | 'error' | 'content'>(() => {
  if (loading.value) return 'loading'
  if (error.value !== null) {
    return error.value.code === 'NOT_FOUND' ? 'not-found' : 'error'
  }
  return data.value !== null ? 'content' : 'loading'
})

/** 登记表单预选载体：当前服务的全部载体（可增删改；存在性仍由服务端裁决）。 */
const presetCarriers = computed(() => data.value?.carriers ?? null)

function backToList(): void {
  emit('back')
}

/** 二次确认通过后删除当前服务；状态管理与错误渲染见 useServiceDelete。 */
function confirmDelete(): void {
  void requestDelete(props.serviceId)
}

// ---- 登记入口（POST）与可选字段修改入口（PATCH） ----

const createDialogVisible = ref(false)
const editDialogVisible = ref(false)

/** 登记成功 → 跳转到新服务的详情（展示服务端返回的登记结果）。 */
function handleCreated(service: ServiceRead): void {
  emit('openDetail', service.id)
}

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="service-detail" :data-state="state">
    <header class="service-detail__header">
      <div class="service-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="service-detail__title">服务详情</h1>
      </div>
      <!-- 登记入口（多载体选择）、可选字段修改入口与删除入口：仅内容态出现；
           name / 载体绑定不可变（契约 §4.4 / NQ-01），编辑表单不提供其输入；
           删除守卫由后端 409 裁决（§21）。 -->
      <div v-if="state === 'content'" class="service-detail__actions">
        <el-button plain data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记服务
        </el-button>
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该服务吗？删除后不可恢复。"
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

    <section class="service-detail__body">
      <div v-if="state === 'loading'" class="service-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="service-detail__delete-error"
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
          <!-- 载体绑定（AC-16）：全部绑定逐项展示（类型 + ID，契约 §2 稳定顺序）。 -->
          <el-descriptions-item label="运行载体">
            <div v-if="carriers.length > 0" class="service-detail__carriers">
              <el-tag
                v-for="carrier in carriers"
                :key="`${carrier.carrier_type}:${carrier.carrier_id}`"
                class="service-detail__carrier"
                data-testid="service-carrier"
              >
                {{ carrier.carrier_type }} #{{ carrier.carrier_id }}
              </el-tag>
              <span class="service-detail__carrier-count">
                （共 {{ carriers.length }} 项）
              </span>
            </div>
            <span v-else>—</span>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>

    <!-- 登记表单（POST）：多载体选择（三种类型 + 载体 ID）；预选当前服务的载体。 -->
    <ServiceFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-carriers="presetCarriers"
      @success="handleCreated"
    />
    <!-- 编辑表单（PATCH）：仅 6 个可选字段；name / 载体绑定不在其中。 -->
    <ServiceFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :service="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.service-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.service-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.service-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.service-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.service-detail__title {
  margin: 0;
  font-size: 20px;
}

.service-detail__body {
  margin-top: 16px;
}

.service-detail__loading {
  padding: 8px 0;
}

.service-detail__delete-error {
  margin-bottom: 16px;
}

.service-detail__carriers {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.service-detail__carrier-count {
  color: #909399;
  font-size: 12px;
}
</style>
